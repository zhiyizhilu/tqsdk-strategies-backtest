#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATR动态止损策略 (ATR Trailing Stop Strategy)
====================================================

策略逻辑：
    - 使用两条均线（MA_FAST 和 MA_SLOW）判断趋势方向
    - 金叉（快线上穿慢线）：开多仓
    - 死叉（快线下穿慢线）：开空仓
    - 持仓期间使用ATR追踪止损动态调整止损线
    - 多仓止损线只上移不下移，空仓止损线只下移不上移
    - 价格触及止损线时平仓
    - 使用 TargetPosTask 管理持仓

适用品种：
    波动性较大的趋势性品种，如原油（INE.sc）、黄金（SHFE.au）、铜（SHFE.cu）、橡胶（SHFE.ru）

风险提示：
    - 均线策略在震荡行情中容易产生频繁的假信号
    - ATR倍数设置对结果影响很大，需要仔细调参
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from tqsdk import TqApi, TargetPosTask
from tqsdk.tafunc import ma, ema, crossup, crossdown
import pandas as pd


class ATRStopLossStrategy:
    """
    ATR动态止损策略类

    使用方式：
        strategy = ATRStopLossStrategy(api, logger, symbol="SHFE.au2506", ma_fast=10, ma_slow=30, atr_n=14, atr_multiplier=2.0)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "SHFE.au2606"
    DEFAULT_MA_FAST = 10
    DEFAULT_MA_SLOW = 30
    DEFAULT_ATR_N = 14
    DEFAULT_ATR_MULTIPLIER = 2.0
    DEFAULT_KLINE_DUR = 60 * 60
    DEFAULT_VOLUME = 1
    DEFAULT_DATA_LENGTH = 300

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        ma_fast: int = None,
        ma_slow: int = None,
        atr_n: int = None,
        atr_multiplier: float = None,
        kline_dur: int = None,
        volume: int = None,
        data_length: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.ma_fast = ma_fast or self.DEFAULT_MA_FAST
        self.ma_slow = ma_slow or self.DEFAULT_MA_SLOW
        self.atr_n = atr_n or self.DEFAULT_ATR_N
        self.atr_multiplier = atr_multiplier or self.DEFAULT_ATR_MULTIPLIER
        self.kline_dur = kline_dur or self.DEFAULT_KLINE_DUR
        self.volume = volume or self.DEFAULT_VOLUME
        self.data_length = data_length or self.DEFAULT_DATA_LENGTH
        self.use_continuous = use_continuous
        self.initial_balance = initial_balance
        self.margin_ratio = margin_ratio

        self.klines = api.get_kline_serial(
            self.symbol, self.kline_dur, data_length=self.data_length
        )

        if self.use_continuous:
            self.quote = api.get_quote(self.symbol)
            self.current_trading_symbol = None
            self.target_pos = None
        else:
            self.current_trading_symbol = self.symbol
            self.target_pos = TargetPosTask(api, self.symbol)
            self._adapt_volume_to_min(self.symbol)

        self.last_signal = None
        self.current_target_volume = 0
        self._last_account_snapshot = None
        self._initial_balance = None
        self._pending_signal = None

        self.long_stop_price = 0.0
        self.short_stop_price = float('inf')

        self._use_insert_order = False
        self._current_position = 0
        self._UNSUPPORTED_TARGETPOS_PREFIXES = {
            'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
            'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
        }

        self.logger.info(
            f"[策略初始化] ATR止损策略 | 合约: {self.symbol} | "
            f"MA快: {self.ma_fast} | MA慢: {self.ma_slow} | "
            f"ATR周期: {self.atr_n} | ATR倍数: {self.atr_multiplier} | "
            f"连续合约: {self.use_continuous} | "
            f"初始资金: {self.initial_balance} | 保证金比例: {self.margin_ratio}"
        )

    CONTRACT_MULTIPLIER_MAP = {
        'DCE.l': 5,   'DCE.v': 5,   'DCE.pp': 5,
        'DCE.eg': 10, 'DCE.i': 100,  'DCE.j': 100,
        'DCE.a': 10,  'DCE.b': 10,   'DCE.c': 10,
        'DCE.m': 10,  'DCE.p': 10,   'DCE.y': 10,
        'DCE.eb': 5,  'DCE.jd': 10,  'DCE.lh': 16,
        'DCE.cs': 10, 'DCE.pg': 10,  'DCE.rr': 10,
        'CZCE.TA': 5,'CZCE.MA': 10,'CZCE.SR': 10,
        'CZCE.CF': 5,'CZCE.OI': 10,'CZCE.FG': 20,
        'CZCE.RM': 10,'CZCE.SF': 5,'CZCE.UR': 20,
        'CZCE.SM': 5,'CZCE.CJ': 5,'CZCE.PK': 5,
        'CZCE.SA': 20,'CZCE.AP': 10,'CZCE.PF': 5,
        'SHFE.rb': 10,'SHFE.au': 1000,'SHFE.cu': 5,
        'SHFE.al': 5,'SHFE.zn': 5,'SHFE.ni': 1,
        'SHFE.sn': 1,'SHFE.ss': 10,'SHFE.ag': 15,
        'SHFE.bu': 10,'SHFE.ru': 10,'SHFE.hc': 10,
        'SHFE.sp': 10,'SHFE.fu': 10,'SHFE.wr': 10,
        'INE.sc': 1000,'INE.lu': 10,
        'CFFEX.IF': 300,'CFFEX.IC': 200,'CFFEX.IH': 300,
        'CFFEX.IM': 200,'CFFEX.T': 10000,'CFFEX.TF': 10000,'CFFEX.TS': 20000,
    }

    MARGIN_RATE_MAP = {
        'DCE.l': 0.12,  'DCE.v': 0.12,  'DCE.pp': 0.12,
        'DCE.eg': 0.12, 'DCE.i': 0.15,  'DCE.j': 0.15,
        'DCE.a': 0.12,  'DCE.b': 0.12,  'DCE.c': 0.12,
        'DCE.m': 0.12,  'DCE.p': 0.12,  'DCE.y': 0.12,
        'DCE.eb': 0.12, 'DCE.jd': 0.12, 'DCE.lh': 0.12,
        'DCE.cs': 0.12, 'DCE.pg': 0.12, 'DCE.rr': 0.12,
        'CZCE.TA': 0.12,'CZCE.MA': 0.12,'CZCE.SR': 0.10,
        'CZCE.CF': 0.12,'CZCE.OI': 0.12,'CZCE.FG': 0.12,
        'CZCE.RM': 0.12,'CZCE.SF': 0.12,'CZCE.UR': 0.12,
        'CZCE.SM': 0.12,'CZCE.CJ': 0.15,'CZCE.PK': 0.15,
        'CZCE.SA': 0.15,'CZCE.AP': 0.12,'CZCE.PF': 0.12,
        'SHFE.rb': 0.13,'SHFE.au': 0.12,'SHFE.cu': 0.12,
        'SHFE.al': 0.11,'SHFE.zn': 0.12,'SHFE.ni': 0.16,
        'SHFE.sn': 0.14,'SHFE.ss': 0.12,'SHFE.ag': 0.12,
        'SHFE.bu': 0.12,'SHFE.ru': 0.13,'SHFE.hc': 0.14,
        'SHFE.sp': 0.12,'SHFE.fu': 0.12,'SHFE.wr': 0.12,
        'INE.sc': 0.15,'INE.lu': 0.12,
        'CFFEX.IF': 0.14,'CFFEX.IC': 0.14,'CFFEX.IH': 0.14,
        'CFFEX.IM': 0.14,'CFFEX.T': 0.02,'CFFEX.TF': 0.03,'CFFEX.TS': 0.02,
    }

    MIN_VOLUME_MAP = {
        'DCE.l': 8,   'DCE.v': 8,   'DCE.pp': 8,
        'DCE.eg': 8,  'DCE.i': 1,   'DCE.j': 1,
        'DCE.a': 1,   'DCE.b': 1,   'DCE.c': 1,
        'DCE.m': 1,   'DCE.p': 1,   'DCE.y': 1,
        'DCE.eb': 1,  'DCE.jd': 1,  'DCE.lh': 1,
        'DCE.cs': 1,  'DCE.pg': 1,  'DCE.rr': 1,
        'CZCE.TA': 8,'CZCE.MA': 8,'CZCE.SR': 1,
        'CZCE.CF': 1,'CZCE.OI': 1,'CZCE.FG': 1,
        'CZCE.RM': 1,'CZCE.SF': 1,'CZCE.UR': 1,
        'CZCE.SM': 1,'CZCE.CJ': 1,'CZCE.PK': 1,
        'CZCE.SA': 1,'CZCE.AP': 2,'CZCE.PF': 1,
        'SHFE.rb': 1,'SHFE.au': 1,'SHFE.cu': 1,
        'SHFE.al': 1,'SHFE.zn': 1,'SHFE.ni': 1,
        'SHFE.sn': 1,'SHFE.ss': 1,'SHFE.ag': 1,
        'SHFE.bu': 1,'SHFE.ru': 1,'SHFE.hc': 1,
        'SHFE.sp': 1,'SHFE.fu': 1,'SHFE.wr': 1,
        'INE.sc': 1,'INE.lu': 1,
        'CFFEX.IF': 1,'CFFEX.IC': 1,'CFFEX.IH': 1,
        'CFFEX.IM': 1,'CFFEX.T': 1,'CFFEX.TF': 1,'CFFEX.TS': 1,
    }

    def _get_symbol_prefix(self, trading_symbol: str):
        import re
        parts = trading_symbol.split('.')
        if len(parts) >= 2:
            exchange = parts[0]
            product = parts[1]
            match = re.match(r'([a-zA-Z]+)', product)
            if match:
                return f"{exchange}.{match.group(1)}"
        return None

    def _get_min_volume(self, trading_symbol: str) -> int:
        prefix = self._get_symbol_prefix(trading_symbol)
        if prefix and prefix in self.MIN_VOLUME_MAP:
            return self.MIN_VOLUME_MAP[prefix]
        return 1

    def _calc_dynamic_volume(self) -> int:
        if self.initial_balance is None or self.margin_ratio is None:
            return self.volume

        try:
            account = self.api.get_account()
            current_balance = account.balance

            current_price = self.klines.close.iloc[-1]
            if current_price <= 0:
                self.logger.warning(f"[动态仓位] 价格异常 {current_price}，使用固定volume")
                return self.volume

            trading_symbol = self.current_trading_symbol or self.symbol
            prefix = self._get_symbol_prefix(trading_symbol)
            multiplier = self.CONTRACT_MULTIPLIER_MAP.get(prefix, 10)
            margin_rate = self.MARGIN_RATE_MAP.get(prefix, 0.12)
            min_vol = self._get_min_volume(trading_symbol)

            available_margin = current_balance * self.margin_ratio
            margin_per_lot = current_price * multiplier * margin_rate

            if margin_per_lot <= 0:
                self.logger.warning(f"[动态仓位] 每手保证金异常 {margin_per_lot}，使用固定volume")
                return self.volume

            calc_volume = int(available_margin / margin_per_lot)
            final_volume = max(calc_volume, min_vol)

            self.logger.info(
                f"[动态仓位] 权益:{current_balance:.0f}×{self.margin_ratio:.0%}="
                f"{available_margin:.0f} | 价:{current_price:.1f}×"
                f"{multiplier}×{margin_rate:.0%}={margin_per_lot:.0f}/手 | "
                f"计算:{calc_volume}手 | 最小:{min_vol}手 | 实际开仓:{final_volume}手"
            )

            return final_volume

        except Exception as e:
            self.logger.warning(f"[动态仓位] 计算失败: {e}，使用固定volume={self.volume}")
            return self.volume

    def _switch_contract(self, new_symbol: str):
        if new_symbol == self.current_trading_symbol:
            return

        self.logger.info(f"[换月] 从 {self.current_trading_symbol} 切换到 {new_symbol}")

        if self.target_pos and self.current_trading_symbol:
            try:
                self.target_pos.set_target_volume(0)
                self.api.wait_update()
                self.logger.info(f"[换月] 已平掉旧合约 {self.current_trading_symbol} 的仓位")
            except Exception as e:
                self.logger.warning(f"[换月] 平仓旧合约时异常: {e}")

        if self.target_pos:
            try:
                self.target_pos.cancel()
            except Exception as e:
                self.logger.info(f"[换月] cancel 旧 TargetPosTask 时异常（可忽略）: {e}")

        self.current_trading_symbol = new_symbol

        import re
        parts = new_symbol.split('.')
        prefix = None
        if len(parts) >= 2:
            match = re.match(r'([a-zA-Z]+)', parts[1])
            if match:
                prefix = f"{parts[0]}.{match.group(1)}"

        if prefix in self._UNSUPPORTED_TARGETPOS_PREFIXES:
            self._use_insert_order = True
            if self.target_pos:
                try: self.target_pos.cancel()
                except Exception: pass
            self.target_pos = None
            self._current_position = 0
            self.logger.info(f"[换月] {new_symbol} 不支持TargetPosTask，使用insert_order模式")
        else:
            self._use_insert_order = False
            try:
                self.target_pos = TargetPosTask(self.api, new_symbol)
                self.logger.info(f"[换月] TargetPosTask 创建成功: {new_symbol}")
            except Exception as e:
                self._use_insert_order = True
                self.target_pos = None
                self._current_position = 0
                self.logger.info(f"[换月] TargetPosTask 创建失败 {new_symbol}: {e}，切换为 insert_order")

        self._adapt_volume_to_min(new_symbol)

        if self.current_target_volume != 0:
            self.target_pos.set_target_volume(self.current_target_volume)
            self.logger.info(f"[换月] 在新合约 {new_symbol} 上设置仓位: {self.current_target_volume}")

    def _adapt_volume_to_min(self, trading_symbol: str):
        prefix = self._get_symbol_prefix(trading_symbol)
        if prefix and prefix in self.MIN_VOLUME_MAP:
            min_vol = self.MIN_VOLUME_MAP[prefix]
            if self.volume < min_vol:
                old_vol = self.volume
                self.volume = min_vol
                self.logger.info(
                    f"[最小下单量适配] {trading_symbol}: "
                    f"volume {old_vol} -> {min_vol} ({prefix} 最小下单量={min_vol})"
                )

    def calc_atr(self):
        """
        计算ATR（平均真实波幅）

        True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
        ATR = EMA(TR, N)

        Returns:
            ATR pandas Series
        """
        high = self.klines["high"]
        low = self.klines["low"]
        close = self.klines["close"]

        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = ema(tr, self.atr_n)

        return atr

    def on_kline_update(self) -> int:
        """
        K线更新时的回调函数

        计算均线和ATR，判断金叉/死叉信号，更新追踪止损线，返回目标仓位

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        close = self.klines["close"]
        ma_fast_series = ma(close, self.ma_fast)
        ma_slow_series = ma(close, self.ma_slow)

        atr_series = self.calc_atr()

        close_cur = close.iloc[-2]
        atr_cur = atr_series.iloc[-2]
        ma_fast_cur = ma_fast_series.iloc[-2]
        ma_slow_cur = ma_slow_series.iloc[-2]

        is_golden = bool(crossup(ma_fast_series, ma_slow_series).iloc[-2])
        is_death = bool(crossdown(ma_fast_series, ma_slow_series).iloc[-2])

        atr_stop_dist = self.atr_multiplier * atr_cur

        position = self.api.get_position(self.current_trading_symbol or self.symbol)

        if position.volume_long > 0:
            new_long_stop = close_cur - atr_stop_dist
            self.long_stop_price = max(self.long_stop_price, new_long_stop)
            self.logger.info(
                f"[ATR止损策略] 多仓止损线更新：{self.long_stop_price:.2f}"
                f"（ATR={atr_cur:.2f}，距离={atr_stop_dist:.2f}）"
            )

        if position.volume_short > 0:
            new_short_stop = close_cur + atr_stop_dist
            self.short_stop_price = min(self.short_stop_price, new_short_stop)
            self.logger.info(
                f"[ATR止损策略] 空仓止损线更新：{self.short_stop_price:.2f}"
                f"（ATR={atr_cur:.2f}，距离={atr_stop_dist:.2f}）"
            )

        self.logger.info(
            f"[{self.klines['datetime'].iloc[-2]}] "
            f"MA快={ma_fast_cur:.2f}，MA慢={ma_slow_cur:.2f}，"
            f"ATR={atr_cur:.2f}，金叉={is_golden}，死叉={is_death}"
        )

        target_volume = 0

        if is_golden:
            dynamic_vol = self._calc_dynamic_volume()
            if position.volume_short > 0:
                self.logger.info(f"[ATR止损策略] 金叉平空：{position.volume_short}手")
                self.short_stop_price = float('inf')
            if position.volume_long == 0:
                self.long_stop_price = close_cur - atr_stop_dist
                self.logger.info(f"[ATR止损策略] 金叉开多：{dynamic_vol}手，初始止损={self.long_stop_price:.2f}")
            self.logger.info(f">>> 金叉！目标仓位: +{dynamic_vol}（做多）")
            target_volume = dynamic_vol
            self.last_signal = "golden"

        elif is_death:
            dynamic_vol = self._calc_dynamic_volume()
            if position.volume_long > 0:
                self.logger.info(f"[ATR止损策略] 死叉平多：{position.volume_long}手")
                self.long_stop_price = 0.0
            if position.volume_short == 0:
                self.short_stop_price = close_cur + atr_stop_dist
                self.logger.info(f"[ATR止损策略] 死叉开空：{dynamic_vol}手，初始止损={self.short_stop_price:.2f}")
            self.logger.info(f">>> 死叉！目标仓位: -{dynamic_vol}（做空）")
            target_volume = -dynamic_vol
            self.last_signal = "death"

        return target_volume

    def check_stop_loss(self) -> int:
        """
        实时止损检查

        检查当前价格是否触及追踪止损线，如果触及则返回平仓目标仓位0

        Returns:
            int: 0 表示需要平仓，-1 表示无需操作
        """
        position = self.api.get_position(self.current_trading_symbol or self.symbol)
        quote = self.api.get_quote(self.current_trading_symbol or self.symbol)
        current_price = quote.last_price

        if position.volume_long > 0 and self.long_stop_price > 0:
            if current_price < self.long_stop_price:
                self.logger.info(f"[ATR止损策略] 多仓止损触发：价格={current_price:.2f}，止损线={self.long_stop_price:.2f}")
                self.long_stop_price = 0.0
                return 0

        if position.volume_short > 0 and self.short_stop_price < float('inf'):
            if current_price > self.short_stop_price:
                self.logger.info(f"[ATR止损策略] 空仓止损触发：价格={current_price:.2f}，止损线={self.short_stop_price:.2f}")
                self.short_stop_price = float('inf')
                return 0

        return -1

    def run(self, max_iterations: int = None) -> None:
        """
        运行策略主循环

        Args:
            max_iterations: 最大迭代次数（用于回测），None 表示无限循环
        """
        iteration = 0
        last_kline_id = None

        while True:
            self.api.wait_update()

            if self.use_continuous and self.target_pos is None:
                if hasattr(self.quote, 'underlying_symbol') and self.quote.underlying_symbol:
                    self._switch_contract(self.quote.underlying_symbol)

            if self.use_continuous and self.api.is_changing(self.quote, "underlying_symbol"):
                new_symbol = self.quote.underlying_symbol
                if new_symbol:
                    self._switch_contract(new_symbol)

            trading_symbol = self.current_trading_symbol or self.symbol

            if self.api.is_changing(self.api.get_quote(trading_symbol)):
                stop_result = self.check_stop_loss()
                if stop_result == 0:
                    self.current_target_volume = 0
                    if self._use_insert_order:
                        try:
                            position = self.api.get_position(trading_symbol)
                            if position.volume_long > 0:
                                self.api.insert_order(
                                    symbol=trading_symbol,
                                    direction="SELL",
                                    offset="CLOSE",
                                    volume=position.volume_long,
                                )
                            elif position.volume_short > 0:
                                self.api.insert_order(
                                    symbol=trading_symbol,
                                    direction="BUY",
                                    offset="CLOSE",
                                    volume=position.volume_short,
                                )
                            self._current_position = 0
                        except Exception as e:
                            self.logger.info(f"[止损-交易失败] {e}")
                    elif self.target_pos is not None:
                        try:
                            self.target_pos.set_target_volume(0)
                        except Exception as tp_err:
                            self._use_insert_order = True
                            self.logger.info(f"[止损] TargetPosTask 执行失败，切换为 insert_order 模式")
                            try:
                                self.target_pos.cancel()
                            except Exception:
                                pass
                            self.target_pos = None

            if not self.api.is_changing(self.klines):
                continue

            current_kline_id = self.klines.id.iloc[-1]
            if current_kline_id == last_kline_id:
                continue
            last_kline_id = current_kline_id

            target_volume = self.on_kline_update()

            if target_volume != 0:
                self.current_target_volume = target_volume
                current_time_t = self.klines.datetime.iloc[-1]
                from datetime import datetime
                trade_date = datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")

                if self._use_insert_order:
                    try:
                        direction = "BUY" if target_volume > 0 else "SELL"
                        offset = "OPEN"
                        order = self.api.insert_order(
                            symbol=self.current_trading_symbol,
                            direction=direction,
                            offset=offset,
                            volume=abs(target_volume),
                        )
                        self.logger.info(f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{abs(target_volume)}")
                        self._current_position = target_volume
                        self._pending_signal = None
                    except Exception as e:
                        self.logger.info(f"[交易-失败] {e}")

                elif self.target_pos is None:
                    self._pending_signal = target_volume
                    self.logger.info(f"[交易-暂存] 日期: {trade_date} | 目标仓位: {target_volume} (等待target_pos初始化)")
                elif self.target_pos is not None:
                    try:
                        self.logger.info(f"[交易] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 目标仓位: {target_volume}")
                        self.target_pos.set_target_volume(target_volume)
                        self._pending_signal = None
                    except Exception as tp_err:
                        self._use_insert_order = True
                        self.logger.info(f"[交易] TargetPosTask 执行失败，切换为 insert_order 模式")
                        try:
                            self.target_pos.cancel()
                        except Exception:
                            pass
                        self.target_pos = None
                        try:
                            direction = "BUY" if target_volume > 0 else "SELL"
                            offset = "OPEN"
                            order = self.api.insert_order(
                                symbol=self.current_trading_symbol,
                                direction=direction,
                                offset=offset,
                                volume=abs(target_volume),
                            )
                            self.logger.info(f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{abs(target_volume)}")
                            self._current_position = target_volume
                        except Exception as e2:
                            self.logger.info(f"[交易-insert失败] {e2}")
                    self._pending_signal = None

            if self._pending_signal is not None and self.target_pos is not None and not self._use_insert_order:
                current_time_t = self.klines.datetime.iloc[-1]
                from datetime import datetime
                trade_date = datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")
                self.logger.info(f"[交易-执行暂存] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 目标仓位: {self._pending_signal}")
                self.target_pos.set_target_volume(self._pending_signal)
                self._pending_signal = None

            try:
                account = self.api.get_account()
                if account:
                    if self._initial_balance is None:
                        self._initial_balance = account.static_balance
                    self._last_account_snapshot = {
                        "static_balance": self._initial_balance,
                        "balance": account.balance,
                        "available": account.available,
                        "float_profit": account.float_profit,
                        "position_profit": account.position_profit,
                        "close_profit": account.close_profit,
                        "margin": account.margin,
                        "commission": account.commission,
                    }
            except Exception:
                pass

            if iteration % 10 == 0 and self._last_account_snapshot:
                current_time = self.klines.datetime.iloc[-1]
                from datetime import datetime
                check_date = datetime.fromtimestamp(current_time / 1000000000).strftime("%Y-%m-%d %H:%M:%S")
                snap = self._last_account_snapshot
                self.logger.info(f"[账户检查] 日期: {check_date} | 账户权益: {snap['balance']:.2f} | 可用资金: {snap['available']:.2f} | 持仓盈亏: {snap['position_profit']:.2f} | 平仓盈亏: {snap['close_profit']:.2f} | 手续费: {snap['commission']:.2f}")

            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                self.logger.info(f"[策略结束] 达到最大迭代次数: {max_iterations}")
                break

    def get_current_position(self) -> int:
        return self.target_pos

    def get_account_snapshot(self) -> dict:
        return self._last_account_snapshot

    def set_target_volume(self, volume: int) -> None:
        self.target_pos.set_target_volume(volume)


def create_strategy(
    api: TqApi,
    logger,
    symbol: str = "SHFE.au2606",
    ma_fast: int = 10,
    ma_slow: int = 30,
    atr_n: int = 14,
    atr_multiplier: float = 2.0,
    kline_dur: int = 3600,
    volume: int = 1,
) -> "ATRStopLossStrategy":
    """
    工厂函数：创建ATR止损策略实例

    Args:
        api: TqApi 实例
        logger: 日志记录器
        symbol: 交易合约代码
        ma_fast: 快速均线周期
        ma_slow: 慢速均线周期
        atr_n: ATR计算周期
        atr_multiplier: ATR倍数
        kline_dur: K线周期（秒）
        volume: 持仓手数

    Returns:
        ATRStopLossStrategy: 策略实例
    """
    return ATRStopLossStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        ma_fast=ma_fast,
        ma_slow=ma_slow,
        atr_n=atr_n,
        atr_multiplier=atr_multiplier,
        kline_dur=kline_dur,
        volume=volume,
    )
