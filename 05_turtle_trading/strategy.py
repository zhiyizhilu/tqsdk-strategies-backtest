#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
海龟交易策略 (Turtle Trading Strategy)
====================================================

策略逻辑：
    基于唐奇安通道（Donchian Channel）的经典趋势跟踪策略：
        入场：价格创 N1 日新高 → 做多；创 N1 日新低 → 做空
        出场：价格回落至 N2 日新低（多头）或 N2 日新高（空头）→ 平仓

    仓位管理（ATR 波动率）：
        每手风险额 = ATR × 合约乘数
        开仓手数   = (账户净值 × RISK_RATIO) / 每手风险额

适用品种：
    趋势性较强的品种，如原油（INE.sc）、螺纹钢（SHFE.rb）、铜（SHFE.cu）等

风险提示：
    - 趋势跟踪策略在震荡行情中容易产生频繁的假信号（亏损）
    - 建议结合成交量、波动率等过滤器使用
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

import pandas as pd
from tqsdk import TqApi, TargetPosTask


class TurtleTradingStrategy:
    """
    海龟交易策略类

    使用方式：
        strategy = TurtleTradingStrategy(api, logger, symbol="INE.sc2501", n1=20, n2=10)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "KQ.m@SHFE.au"
    DEFAULT_N1 = 20
    DEFAULT_N2 = 10
    DEFAULT_ATR_PERIOD = 20
    DEFAULT_RISK_RATIO = 0.01
    DEFAULT_CONTRACT_MULTIPLIER = None
    DEFAULT_MAX_VOLUME = 10
    DEFAULT_KLINE_DUR = 86400

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

    _UNSUPPORTED_TARGETPOS_PREFIXES = {
        'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
        'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
    }

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        n1: int = None,
        n2: int = None,
        atr_period: int = None,
        risk_ratio: float = None,
        contract_multiplier: int = None,
        max_volume: int = None,
        kline_dur: int = None,
        volume: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.n1 = n1 or self.DEFAULT_N1
        self.n2 = n2 or self.DEFAULT_N2
        self.atr_period = atr_period or self.DEFAULT_ATR_PERIOD
        self.risk_ratio = risk_ratio or self.DEFAULT_RISK_RATIO
        self.contract_multiplier = contract_multiplier or self.DEFAULT_CONTRACT_MULTIPLIER
        self.max_volume = max_volume or self.DEFAULT_MAX_VOLUME
        self.kline_dur = kline_dur or self.DEFAULT_KLINE_DUR
        self.volume = volume or 1
        self.use_continuous = use_continuous
        self.initial_balance = initial_balance
        self.margin_ratio = margin_ratio

        self.klines = api.get_kline_serial(
            self.symbol, self.kline_dur, data_length=max(self.n1, self.atr_period) + 10
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

        self.logger.info(
            f"[策略初始化] 海龟策略 | 合约: {self.symbol} | "
            f"N1: {self.n1} | N2: {self.n2} | ATR: {self.atr_period} | "
            f"风险比: {self.risk_ratio} | 最大手数: {self.max_volume} | "
            f"连续合约: {self.use_continuous} | "
            f"初始资金: {self.initial_balance} | 保证金比例: {self.margin_ratio}"
        )

    @staticmethod
    def calc_atr(klines: pd.DataFrame, period: int) -> pd.Series:
        high, low, close = klines.high, klines.low, klines.close
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        return tr.ewm(alpha=1.0 / period, adjust=False).mean()

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

    def _get_contract_multiplier(self, trading_symbol: str) -> int:
        if self.contract_multiplier is not None:
            return self.contract_multiplier
        prefix = self._get_symbol_prefix(trading_symbol)
        if prefix and prefix in self.CONTRACT_MULTIPLIER_MAP:
            return self.CONTRACT_MULTIPLIER_MAP[prefix]
        return 10

    def _calc_atr_volume(self) -> int:
        try:
            account = self.api.get_account()
            atr_val = self.calc_atr(self.klines, self.atr_period).iloc[-1]
            if pd.isna(atr_val) or atr_val <= 0:
                return self.volume

            trading_symbol = self.current_trading_symbol or self.symbol
            multiplier = self._get_contract_multiplier(trading_symbol)

            vol = int(account.balance * self.risk_ratio / (atr_val * multiplier))
            min_vol = self._get_min_volume(trading_symbol)
            vol = max(min_vol, min(vol, self.max_volume))

            self.logger.info(
                f"[ATR仓位] 权益:{account.balance:.0f}×{self.risk_ratio}="
                f"{account.balance * self.risk_ratio:.0f} | ATR:{atr_val:.2f}×"
                f"{multiplier}={atr_val * multiplier:.0f}/手 | "
                f"计算:{vol}手 | 最大:{self.max_volume}手"
            )
            return vol
        except Exception as e:
            self.logger.warning(f"[ATR仓位] 计算失败: {e}，使用固定volume={self.volume}")
            return self.volume

    def _calc_dynamic_volume(self) -> int:
        if self.initial_balance is None or self.margin_ratio is None:
            return self._calc_atr_volume()

        try:
            account = self.api.get_account()
            current_balance = account.balance
            current_price = self.klines.close.iloc[-1]
            if current_price <= 0:
                return self._calc_atr_volume()

            trading_symbol = self.current_trading_symbol or self.symbol
            prefix = self._get_symbol_prefix(trading_symbol)
            multiplier = self._get_contract_multiplier(trading_symbol)
            margin_rate = self.MARGIN_RATE_MAP.get(prefix, 0.12)
            min_vol = self._get_min_volume(trading_symbol)

            available_margin = current_balance * self.margin_ratio
            margin_per_lot = current_price * multiplier * margin_rate

            if margin_per_lot <= 0:
                return self._calc_atr_volume()

            calc_volume = int(available_margin / margin_per_lot)
            atr_vol = self._calc_atr_volume()
            final_volume = min(max(calc_volume, min_vol), atr_vol)

            self.logger.info(
                f"[动态仓位] 权益:{current_balance:.0f}×{self.margin_ratio:.0%}="
                f"{available_margin:.0f} | 价:{current_price:.1f}×"
                f"{multiplier}×{margin_rate:.0%}={margin_per_lot:.0f}/手 | "
                f"计算:{calc_volume}手 | ATR限制:{atr_vol}手 | 实际:{final_volume}手"
            )
            return final_volume
        except Exception as e:
            self.logger.warning(f"[动态仓位] 计算失败: {e}，使用ATR仓位")
            return self._calc_atr_volume()

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
        atr_series = self.calc_atr(self.klines, self.atr_period)
        atr_val = atr_series.iloc[-1]
        if pd.isna(atr_val) or atr_val <= 0:
            return 0

        high_n1 = self.klines.high.iloc[-(self.n1 + 1):-1].max()
        low_n1 = self.klines.low.iloc[-(self.n1 + 1):-1].min()
        high_n2 = self.klines.high.iloc[-(self.n2 + 1):-1].max()
        low_n2 = self.klines.low.iloc[-(self.n2 + 1):-1].min()
        last_close = self.klines.close.iloc[-1]

        vol = self._calc_dynamic_volume()

        self.logger.info(
            f"收盘:{last_close:.2f} ATR:{atr_val:.2f} "
            f"N1:[{low_n1:.2f},{high_n1:.2f}] N2:[{low_n2:.2f},{high_n2:.2f}] 建议:{vol}手"
        )

        target_volume = 0

        if last_close >= high_n1:
            self.logger.info(f">>> 突破{self.n1}日新高，做多{vol}手")
            target_volume = vol
            self.last_signal = "long"

        elif last_close <= low_n1:
            self.logger.info(f">>> 跌破{self.n1}日新低，做空{vol}手")
            target_volume = -vol
            self.last_signal = "short"

        elif last_close <= low_n2:
            self.logger.info(f">>> 跌破{self.n2}日新低，平多")
            target_volume = 0
            self.last_signal = "exit_long"

        elif last_close >= high_n2:
            self.logger.info(f">>> 突破{self.n2}日新高，平空")
            target_volume = 0
            self.last_signal = "exit_short"

        return target_volume

    def run(self, max_iterations: int = None) -> None:
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

                from datetime import datetime
                current_time_t = self.klines.datetime.iloc[-1]
                trade_date = datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")

                if self._use_insert_order:
                    try:
                        actual_vol = self.current_target_volume
                        if actual_vol == 0:
                            direction = "SELL" if self._current_position > 0 else "BUY"
                            offset = "CLOSE"
                            order = self.api.insert_order(
                                symbol=self.current_trading_symbol,
                                direction=direction,
                                offset=offset,
                                volume=abs(self._current_position),
                            )
                            self.logger.info(f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 平仓 | 手数:{abs(self._current_position)}")
                        else:
                            direction = "BUY" if actual_vol > 0 else "SELL"
                            offset = "OPEN"
                            order = self.api.insert_order(
                                symbol=self.current_trading_symbol,
                                direction=direction,
                                offset=offset,
                                volume=abs(actual_vol),
                            )
                            self.logger.info(f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{abs(actual_vol)}")
                        self._current_position = self.current_target_volume
                        self._pending_signal = None
                    except Exception as e:
                        self.logger.info(f"[交易-失败] {e}")

                elif self.target_pos is None:
                    self._pending_signal = self.current_target_volume
                    self.logger.info(f"[交易-暂存] 日期: {trade_date} | 目标仓位: {self.current_target_volume} (等待target_pos初始化)")
                elif self.target_pos is not None:
                    try:
                        self.logger.info(f"[交易] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 目标仓位: {self.current_target_volume}")
                        self.target_pos.set_target_volume(self.current_target_volume)
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
                            actual_vol = self.current_target_volume
                            if actual_vol != 0:
                                direction = "BUY" if actual_vol > 0 else "SELL"
                                offset = "OPEN"
                                order = self.api.insert_order(
                                    symbol=self.current_trading_symbol,
                                    direction=direction,
                                    offset=offset,
                                    volume=abs(actual_vol),
                                )
                                self.logger.info(f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{abs(actual_vol)}")
                            self._current_position = self.current_target_volume
                        except Exception as e2:
                            self.logger.info(f"[交易-insert失败] {e2}")
                    self._pending_signal = None

            if self._pending_signal is not None and self.target_pos is not None and not self._use_insert_order:
                from datetime import datetime
                current_time_t = self.klines.datetime.iloc[-1]
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
                from datetime import datetime
                current_time = self.klines.datetime.iloc[-1]
                check_date = datetime.fromtimestamp(current_time / 1000000000).strftime("%Y-%m-%d %H:%M:%S")
                snap = self._last_account_snapshot
                self.logger.info(f"[账户检查] 日期: {check_date} | 账户权益: {snap['balance']:.2f} | 可用资金: {snap['available']:.2f} | 持仓盈亏: {snap['position_profit']:.2f} | 平仓盈亏: {snap['close_profit']:.2f} | 手续费: {snap['commission']:.2f}")

            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                self.logger.info(f"[策略结束] 达到最大迭代次数: {max_iterations}")
                break

    def get_current_position(self):
        return self.target_pos

    def get_account_snapshot(self) -> dict:
        return self._last_account_snapshot

    def set_target_volume(self, volume: int) -> None:
        self.target_pos.set_target_volume(volume)


def create_strategy(
    api: TqApi,
    logger,
    symbol: str = "KQ.m@SHFE.au",
    n1: int = 20,
    n2: int = 10,
    atr_period: int = 20,
    risk_ratio: float = 0.01,
    contract_multiplier: int = None,
    max_volume: int = 10,
    kline_dur: int = 86400,
    volume: int = 1,
) -> TurtleTradingStrategy:
    return TurtleTradingStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        n1=n1,
        n2=n2,
        atr_period=atr_period,
        risk_ratio=risk_ratio,
        contract_multiplier=contract_multiplier,
        max_volume=max_volume,
        kline_dur=kline_dur,
        volume=volume,
    )
