#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
随机RSI策略 (Stochastic RSI Strategy)
======================================

策略逻辑：
    - 计算RSI（相对强弱指数）
    - 对RSI做随机化处理，得到StochRSI的K线和D线
    - K线从下方上穿D线（且在超卖区域附近）→ 做多
    - K线从上方下穿D线（且在超买区域附近）→ 做空
    - K线进入超买区→ 平多仓
    - K线进入超卖区→ 平空仓
    - 使用 TargetPosTask 管理持仓，无需手动处理追单、撤单、部分成交等细节

适用品种：
    波动较活跃的期货，如黄金AU、白银AG、铜CU、原油SC、股指IF

风险提示：
    - 信号频率高，虚假信号多，容易在趋势市场中逆势做单
    - 对参数敏感，N和M的选择对结果影响较大
    - 本质是二阶振荡器，在强趋势时会长期处于超买/超卖状态
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

import numpy as np
import pandas as pd
from tqsdk import TqApi, TargetPosTask
from tqsdk.tafunc import crossup, crossdown


class StochasticRSIStrategy:
    """
    随机RSI策略类

    使用方式：
        strategy = StochasticRSIStrategy(api, logger, symbol="SHFE.au2406", rsi_period=14, stoch_period=14)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "SHFE.au2606"
    DEFAULT_RSI_PERIOD = 14
    DEFAULT_STOCH_PERIOD = 14
    DEFAULT_SMOOTH_K = 3
    DEFAULT_SMOOTH_D = 3
    DEFAULT_OVERBOUGHT = 0.8
    DEFAULT_OVERSOLD = 0.2
    DEFAULT_KLINE_DUR = 5 * 60
    DEFAULT_VOLUME = 1
    DEFAULT_DATA_LENGTH = 300

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

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        rsi_period: int = None,
        stoch_period: int = None,
        smooth_k: int = None,
        smooth_d: int = None,
        overbought: float = None,
        oversold: float = None,
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
        self.rsi_period = rsi_period or self.DEFAULT_RSI_PERIOD
        self.stoch_period = stoch_period or self.DEFAULT_STOCH_PERIOD
        self.smooth_k = smooth_k or self.DEFAULT_SMOOTH_K
        self.smooth_d = smooth_d or self.DEFAULT_SMOOTH_D
        self.overbought = overbought if overbought is not None else self.DEFAULT_OVERBOUGHT
        self.oversold = oversold if oversold is not None else self.DEFAULT_OVERSOLD
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
        self.signal_stats = {
            "cross_up_count": 0,
            "cross_down_count": 0,
            "long_signals": 0,
            "short_signals": 0,
            "close_long_signals": 0,
            "close_short_signals": 0,
            "total_klines": 0,
        }

        self._use_insert_order = False
        self._current_position = 0
        self._UNSUPPORTED_TARGETPOS_PREFIXES = {
            'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
            'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
        }

        self.logger.info(
            f"[策略初始化] 随机RSI策略 | 合约: {self.symbol} | "
            f"RSI周期: {self.rsi_period} | Stoch周期: {self.stoch_period} | "
            f"K平滑: {self.smooth_k} | D平滑: {self.smooth_d} | "
            f"超买: {self.overbought} | 超卖: {self.oversold} | "
            f"连续合约: {self.use_continuous} | "
            f"初始资金: {self.initial_balance} | 保证金比例: {self.margin_ratio}"
        )

    @staticmethod
    def calc_rsi(close_series, period):
        """
        计算RSI相对强弱指数

        使用Wilder平滑方法（指数平均）

        参数：
            close_series: 收盘价序列（pandas Series）
            period: RSI周期
        返回：
            rsi: RSI值序列（pandas Series，取值0-100）
        """
        delta = close_series.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)

        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calc_stoch_rsi(rsi_series, stoch_period, smooth_k, smooth_d):
        """
        对RSI序列做随机化处理，计算StochRSI的K线和D线

        参数：
            rsi_series:   RSI值序列（pandas Series）
            stoch_period: 随机化处理周期
            smooth_k:     K线平滑周期
            smooth_d:     D线平滑周期
        返回：
            stoch_k: K线序列（pandas Series，取值0~1）
            stoch_d: D线序列（pandas Series，取值0~1）
        """
        rsi_max = rsi_series.rolling(window=stoch_period).max()
        rsi_min = rsi_series.rolling(window=stoch_period).min()

        denom = rsi_max - rsi_min
        stoch_raw = (rsi_series - rsi_min) / (denom.replace(0, np.nan))

        stoch_k = stoch_raw.rolling(window=smooth_k).mean()
        stoch_d = stoch_k.rolling(window=smooth_d).mean()

        return stoch_k, stoch_d

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

    def on_kline_update(self) -> int:
        """
        K线更新时的回调函数

        计算RSI、StochRSI的K/D线，判断交叉信号，返回目标仓位

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        self.signal_stats["total_klines"] += 1

        close = self.klines.close

        rsi = self.calc_rsi(close, self.rsi_period)
        stoch_k, stoch_d = self.calc_stoch_rsi(rsi, self.stoch_period, self.smooth_k, self.smooth_d)

        k_now = stoch_k.iloc[-1]
        d_now = stoch_d.iloc[-1]
        rsi_now = rsi.iloc[-1]

        cross_up_sig = crossup(stoch_k, stoch_d)
        cross_down_sig = crossdown(stoch_k, stoch_d)

        last_cross_up = bool(cross_up_sig.iloc[-1])
        last_cross_down = bool(cross_down_sig.iloc[-1])

        if last_cross_up:
            self.signal_stats["cross_up_count"] += 1
        if last_cross_down:
            self.signal_stats["cross_down_count"] += 1

        self.logger.info(
            f"RSI={rsi_now:.2f}, K={k_now:.3f}, D={d_now:.3f}"
        )

        target_volume = self.current_target_volume

        if last_cross_up and rsi_now < 70:
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(f">>> K上穿D（RSI={rsi_now:.1f}）！目标仓位: +{dynamic_vol}（做多）")
            target_volume = dynamic_vol
            self.last_signal = "long"
            self.signal_stats["long_signals"] += 1

        elif last_cross_down and rsi_now > 30:
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(f">>> K下穿D（RSI={rsi_now:.1f}）！目标仓位: -{dynamic_vol}（做空）")
            target_volume = -dynamic_vol
            self.last_signal = "short"
            self.signal_stats["short_signals"] += 1

        elif self.current_target_volume > 0 and (last_cross_down or k_now > self.overbought):
            self.logger.info(f">>> 平多信号（反向交叉或K={k_now:.3f}>超买线）")
            target_volume = 0
            self.last_signal = "close_long"
            self.signal_stats["close_long_signals"] += 1

        elif self.current_target_volume < 0 and (last_cross_up or k_now < self.oversold):
            self.logger.info(f">>> 平空信号（反向交叉或K={k_now:.3f}<超卖线）")
            target_volume = 0
            self.last_signal = "close_short"
            self.signal_stats["close_short_signals"] += 1

        return target_volume

    def get_account_snapshot(self) -> dict:
        return self._last_account_snapshot

    def get_signal_stats(self) -> dict:
        return self.signal_stats.copy()

    def _save_account_snapshot(self):
        try:
            acc = self.api.get_account()
            self._last_account_snapshot = {
                "static_balance": acc.static_balance,
                "balance": acc.balance,
                "available": acc.available,
                "float_profit": acc.float_profit,
                "position_profit": acc.position_profit,
                "close_profit": acc.close_profit,
                "margin": acc.margin,
                "commission": acc.commission,
            }
        except Exception:
            pass

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

            iteration += 1

            if self.use_continuous:
                if self.current_trading_symbol is None:
                    if hasattr(self.quote, 'underlying_symbol'):
                        underlying = self.quote.underlying_symbol
                        if underlying and underlying != "":
                            self.current_trading_symbol = underlying
                            self.target_pos = TargetPosTask(self.api, underlying)
                            self._adapt_volume_to_min(underlying)
                            self.logger.info(f"[连续合约] 底层合约确定: {underlying}")
                    continue

                if hasattr(self.quote, 'underlying_symbol') and self.quote.underlying_symbol:
                    if self.current_trading_symbol and self.quote.underlying_symbol != self.current_trading_symbol:
                        self._switch_contract(self.quote.underlying_symbol)

            if not self.api.is_changing(self.klines):
                continue

            current_kline_id = self.klines.iloc[-1]["datetime"]
            if current_kline_id == last_kline_id:
                continue
            last_kline_id = current_kline_id

            target_volume = self.on_kline_update()

            if target_volume != 0 or self.last_signal in ("close_long", "close_short"):
                self.current_target_volume = target_volume

                if self.target_pos:
                    self.target_pos.set_target_volume(target_volume)

            self._save_account_snapshot()

            if iteration % 100 == 0:
                try:
                    acc = self.api.get_account()
                    self.logger.info(
                        f"[账户] 权益: {acc.balance:,.2f} | "
                        f"可用: {acc.available:,.2f} | "
                        f"浮盈: {acc.float_profit:,.2f} | "
                        f"持仓盈亏: {acc.position_profit:,.2f}"
                    )
                except Exception:
                    pass

            if max_iterations is not None and iteration >= max_iterations:
                self.logger.info(f"[策略] 达到最大迭代次数 {max_iterations}，退出")
                break
