#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
唐奇安通道策略 (Donchian Channel Strategy)
==========================================

策略逻辑：
    - 使用入场通道（N_ENTER周期）和出场通道（N_EXIT周期）的突破信号判断趋势方向
    - 价格突破入场通道上轨：目标仓位设为 +VOLUME（做多）
    - 价格跌破入场通道下轨：目标仓位设为 -VOLUME（做空）
    - 多头持仓时价格跌破出场通道下轨：平多离场
    - 空头持仓时价格突破出场通道上轨：平空离场
    - 使用 TargetPosTask 管理持仓，无需手动处理追单、撤单、部分成交等细节

适用品种：
    趋势性强的品种，如原油（INE.sc）、铜（SHFE.cu）、螺纹钢（SHFE.rb）、股指（CFFEX.IF）

风险提示：
    - 通道策略在震荡行情中容易产生频繁的假突破信号（亏损）
    - 建议结合ATR、成交量等过滤器使用
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from tqsdk import TqApi, TargetPosTask


class DonchianChannelStrategy:
    """
    唐奇安通道策略类

    使用方式：
        strategy = DonchianChannelStrategy(api, logger, symbol="SHFE.rb2605", n_enter=20, n_exit=10)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "SHFE.rb2605"
    DEFAULT_N_ENTER = 20
    DEFAULT_N_EXIT = 10
    DEFAULT_KLINE_DUR = 60 * 60
    DEFAULT_VOLUME = 1
    DEFAULT_ATR_PERIOD = 14
    DEFAULT_ATR_FILTER = True

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        n_enter: int = None,
        n_exit: int = None,
        kline_dur: int = None,
        volume: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
        atr_period: int = None,
        atr_filter: bool = None,
    ):
        """
        初始化唐奇安通道策略

        Args:
            api: TqApi 实例，用于与期货交易系统交互
            logger: 日志记录器，用于记录策略运行信息
            symbol: 交易合约代码，格式为 "交易所.合约代码"，或连续合约如 "KQ.m@SHFE.rb"
            n_enter: 入场通道周期（K线根数），价格突破N_ENTER期最高/最低时入场
            n_exit: 出场通道周期（K线根数），价格突破N_EXIT期最高/最低时出场
            kline_dur: K线周期（秒），60=1分钟K线，3600=1小时K线
            volume: 固定持仓手数（目标仓位的绝对值）。当使用动态仓位时此值作为保底参考
            use_continuous: 是否使用连续主力合约
            initial_balance: 初始资金（元），用于动态仓位计算
            margin_ratio: 保证金比例（0~1），每次开仓用总资产的该比例作为保证金
            atr_period: ATR计算周期，默认14
            atr_filter: 是否启用ATR波动率过滤，默认True。仅在ATR高于近期均值时入场，减少假突破
        """
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.n_enter = n_enter or self.DEFAULT_N_ENTER
        self.n_exit = n_exit or self.DEFAULT_N_EXIT
        self.kline_dur = kline_dur or self.DEFAULT_KLINE_DUR
        self.volume = volume or self.DEFAULT_VOLUME
        self.use_continuous = use_continuous
        self.initial_balance = initial_balance
        self.margin_ratio = margin_ratio
        self.atr_period = atr_period or self.DEFAULT_ATR_PERIOD
        self.atr_filter = atr_filter if atr_filter is not None else self.DEFAULT_ATR_FILTER

        self.klines = api.get_kline_serial(
            self.symbol, self.kline_dur, data_length=max(self.n_enter, 14) + 10
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

        self._use_insert_order = False
        self._current_position = 0
        self._UNSUPPORTED_TARGETPOS_PREFIXES = {
            'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
            'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
        }

        self.logger.info(
            f"[策略初始化] 唐奇安通道策略 | 合约: {self.symbol} | "
            f"入场N: {self.n_enter} | 出场N: {self.n_exit} | "
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

    def _calc_atr(self) -> float:
        try:
            highs = self.klines.high.iloc[-(self.atr_period + 2):-2]
            lows = self.klines.low.iloc[-(self.atr_period + 2):-2]
            closes = self.klines.close.iloc[-(self.atr_period + 3):-3]

            if len(highs) < self.atr_period or len(closes) < self.atr_period:
                return 0.0

            tr_values = []
            for i in range(self.atr_period):
                idx = -(self.atr_period + 2) + i
                h = self.klines.high.iloc[idx]
                l = self.klines.low.iloc[idx]
                prev_close = self.klines.close.iloc[idx - 1]
                tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
                tr_values.append(tr)

            return sum(tr_values) / len(tr_values) if tr_values else 0.0
        except Exception:
            return 0.0

    def _is_atr_above_average(self, current_atr: float) -> bool:
        try:
            lookback = min(self.atr_period * 2, len(self.klines) - 5)
            if lookback < self.atr_period:
                return True

            atr_values = []
            for offset in range(lookback):
                end_idx = -(3 + offset)
                start_idx = end_idx - self.atr_period
                if start_idx < 0:
                    break

                tr_sum = 0.0
                valid_count = 0
                for j in range(self.atr_period):
                    idx = start_idx + j
                    if idx <= 0 or idx >= len(self.klines) - 2:
                        continue
                    h = self.klines.high.iloc[idx]
                    l = self.klines.low.iloc[idx]
                    prev_close = self.klines.close.iloc[idx - 1]
                    if prev_close > 0:
                        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
                        tr_sum += tr
                        valid_count += 1

                if valid_count > 0:
                    atr_values.append(tr_sum / valid_count)

            if not atr_values:
                return True

            avg_atr = sum(atr_values) / len(atr_values)
            return current_atr >= avg_atr * 0.8
        except Exception:
            return True

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

    def on_kline_update(self) -> int:
        """
        K线更新时的回调函数

        计算唐奇安通道的入场和出场轨道，判断是否出现突破信号，并返回相应的目标仓位

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        high_enter = self.klines.high.iloc[-(self.n_enter + 2):-2].max()
        low_enter = self.klines.low.iloc[-(self.n_enter + 2):-2].min()
        high_exit = self.klines.high.iloc[-(self.n_exit + 2):-2].max()
        low_exit = self.klines.low.iloc[-(self.n_exit + 2):-2].min()

        last_close = self.klines.close.iloc[-2]

        atr_value = self._calc_atr()

        self.logger.info(
            f"收盘: {last_close:.2f} | "
            f"入场通道: [{low_enter:.2f}, {high_enter:.2f}] | "
            f"出场通道: [{low_exit:.2f}, {high_exit:.2f}] | "
            f"ATR: {atr_value:.2f}"
        )

        target_volume = 0

        if last_close > high_enter:
            if self.atr_filter and not self._is_atr_above_average(atr_value):
                self.logger.info(f">>> 突破入场上轨 {high_enter:.2f}，但ATR偏低({atr_value:.2f})，跳过入场")
            else:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(f">>> 突破入场上轨 {high_enter:.2f}，做多 | 目标仓位: +{dynamic_vol}")
                target_volume = dynamic_vol
                self.last_signal = "long"

        elif last_close < low_enter:
            if self.atr_filter and not self._is_atr_above_average(atr_value):
                self.logger.info(f">>> 跌破入场下轨 {low_enter:.2f}，但ATR偏低({atr_value:.2f})，跳过入场")
            else:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(f">>> 跌破入场下轨 {low_enter:.2f}，做空 | 目标仓位: -{dynamic_vol}")
                target_volume = -dynamic_vol
                self.last_signal = "short"

        elif self.current_target_volume > 0 and last_close < low_exit:
            self.logger.info(f">>> 多头跌破出场下轨 {low_exit:.2f}，平多")
            target_volume = 0
            self.last_signal = "exit_long"

        elif self.current_target_volume < 0 and last_close > high_exit:
            self.logger.info(f">>> 空头突破出场上轨 {high_exit:.2f}，平空")
            target_volume = 0
            self.last_signal = "exit_short"

        return target_volume

    def run(self, max_iterations: int = None) -> None:
        """
        运行策略主循环

        Args:
            max_iterations: 最大迭代次数（用于回测），None 表示无限循环
        """
        iteration = 0
        last_kline_id = None

        if self.use_continuous:
            self.logger.info("[初始化] 等待连续合约数据就绪...")
            while self.target_pos is None:
                self.api.wait_update()
                if hasattr(self.quote, 'underlying_symbol') and self.quote.underlying_symbol:
                    self._switch_contract(self.quote.underlying_symbol)
            self.logger.info(f"[初始化] 连续合约就绪，交易合约: {self.current_trading_symbol}")

        while True:
            self.api.wait_update()

            if self.use_continuous and self.api.is_changing(self.quote, "underlying_symbol"):
                new_symbol = self.quote.underlying_symbol
                if new_symbol:
                    self._switch_contract(new_symbol)

            if not self.api.is_changing(self.klines):
                continue

            current_kline_id = self.klines.id.iloc[-1]
            if current_kline_id == last_kline_id:
                continue
            last_kline_id = current_kline_id

            target_volume = self.on_kline_update()

            if target_volume != 0 or self.last_signal in ("exit_long", "exit_short"):
                if self.last_signal in ("exit_long", "exit_short"):
                    self.current_target_volume = 0
                else:
                    self.current_target_volume = target_volume

                self.last_signal = None

                current_time_t = self.klines.datetime.iloc[-1]
                from datetime import datetime
                trade_date = datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")

                if self._use_insert_order:
                    try:
                        if target_volume > 0:
                            direction = "BUY"
                            offset = "OPEN"
                            vol = abs(target_volume)
                        elif target_volume < 0:
                            direction = "SELL"
                            offset = "OPEN"
                            vol = abs(target_volume)
                        else:
                            direction = "SELL" if self._current_position > 0 else "BUY"
                            offset = "CLOSE"
                            vol = abs(self._current_position)

                        order = self.api.insert_order(
                            symbol=self.current_trading_symbol,
                            direction=direction,
                            offset=offset,
                            volume=vol,
                        )
                        self.logger.info(f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{vol}")
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
                            if target_volume > 0:
                                direction = "BUY"
                                offset = "OPEN"
                                vol = abs(target_volume)
                            elif target_volume < 0:
                                direction = "SELL"
                                offset = "OPEN"
                                vol = abs(target_volume)
                            else:
                                direction = "SELL" if self._current_position > 0 else "BUY"
                                offset = "CLOSE"
                                vol = abs(self._current_position)

                            order = self.api.insert_order(
                                symbol=self.current_trading_symbol,
                                direction=direction,
                                offset=offset,
                                volume=vol,
                            )
                            self.logger.info(f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{vol}")
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
    symbol: str = "SHFE.rb2605",
    n_enter: int = 20,
    n_exit: int = 10,
    kline_dur: int = 60 * 60,
    volume: int = 1,
) -> DonchianChannelStrategy:
    """
    创建唐奇安通道策略实例的工厂函数

    Args:
        api: TqApi 实例
        logger: 日志记录器
        symbol: 交易合约代码
        n_enter: 入场通道周期
        n_exit: 出场通道周期
        kline_dur: K线周期（秒）
        volume: 持仓手数

    Returns:
        DonchianChannelStrategy: 策略实例
    """
    return DonchianChannelStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        n_enter=n_enter,
        n_exit=n_exit,
        kline_dur=kline_dur,
        volume=volume,
    )
