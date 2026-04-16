#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDJ随机指标策略 (KDJ Signal Strategy)
====================================================

策略逻辑：
    - 使用KDJ指标（K、D、J线）的金叉/死叉信号判断趋势方向
    - 金叉（K线上穿D线）且处于中低位（K<50）：目标仓位设为 +VOLUME（做多）
    - 死叉（K线下穿D线）且处于中高位（K>50）：目标仓位设为 -VOLUME（做空）
    - 超买区（K>80）平多仓止损，超卖区（K<20）平空仓止损
    - 使用 TargetPosTask 管理持仓，无需手动处理追单、撤单、部分成交等细节

适用品种：
    波动性适中的品种，如股指期货（CFFEX.IF/IC）、农产品期货（DCE.m、CZCE.CF）等

风险提示：
    - KDJ在强趋势行情中可能长期处于超买/超卖，导致过早平仓亏损
    - 建议结合趋势指标（如MA）过滤假信号
    - 本代码仅供学习参考，不构成任何投资建议

参数说明：
    SYMBOL        : 交易合约代码，格式为 "交易所.合约代码"
    KDJ_N         : RSV计算周期（K线根数），标准参数9
    KDJ_M1        : K值平滑参数，标准参数3
    KDJ_M2        : D值平滑参数，标准参数3
    OVERBUY       : 超买阈值，默认80
    OVERSELL      : 超卖阈值，默认20
    KLINE_DUR     : K线周期（秒），60=1分钟K线，3600=1小时K线
    VOLUME        : 持仓手数（目标仓位的绝对值）

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
      https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.api.html#tqsdk.api.TqApi.TargetPosTask
"""

from tqsdk import TqApi, TargetPosTask
from tqsdk.tafunc import hhv, llv
import numpy as np
import pandas as pd


class KDJSignalStrategy:
    """
    KDJ信号策略类

    使用方式：
        strategy = KDJSignalStrategy(api, logger, symbol="DCE.m2506", kdj_n=9, kdj_m1=3, kdj_m2=3)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "DCE.m2607"
    DEFAULT_KDJ_N = 9
    DEFAULT_KDJ_M1 = 3
    DEFAULT_KDJ_M2 = 3
    DEFAULT_OVERBUY = 80
    DEFAULT_OVERSELL = 20
    DEFAULT_KLINE_DUR = 60 * 30
    DEFAULT_VOLUME = 1

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        kdj_n: int = None,
        kdj_m1: int = None,
        kdj_m2: int = None,
        overbuy: int = None,
        oversell: int = None,
        kline_dur: int = None,
        volume: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        """
        初始化KDJ信号策略

        Args:
            api: TqApi 实例，用于与期货交易系统交互
            logger: 日志记录器，用于记录策略运行信息
            symbol: 交易合约代码，格式为 "交易所.合约代码"，或连续合约如 "KQ.m@DCE.m"
            kdj_n: RSV计算周期（K线根数）
            kdj_m1: K值平滑参数
            kdj_m2: D值平滑参数
            overbuy: 超买阈值
            oversell: 超卖阈值
            kline_dur: K线周期（秒），60=1分钟K线，3600=1小时K线
            volume: 固定持仓手数（目标仓位的绝对值）。当使用动态仓位时此值作为保底参考
            use_continuous: 是否使用连续主力合约
            initial_balance: 初始资金（元），用于动态仓位计算
            margin_ratio: 保证金比例（0~1），每次开仓用总资产的该比例作为保证金
        """
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.kdj_n = kdj_n or self.DEFAULT_KDJ_N
        self.kdj_m1 = kdj_m1 or self.DEFAULT_KDJ_M1
        self.kdj_m2 = kdj_m2 or self.DEFAULT_KDJ_M2
        self.overbuy = overbuy or self.DEFAULT_OVERBUY
        self.oversell = oversell or self.DEFAULT_OVERSELL
        self.kline_dur = kline_dur or self.DEFAULT_KLINE_DUR
        self.volume = volume or self.DEFAULT_VOLUME
        self.use_continuous = use_continuous
        self.initial_balance = initial_balance
        self.margin_ratio = margin_ratio

        data_length = max(self.kdj_n + 50, 300)
        self.klines = api.get_kline_serial(
            self.symbol, self.kline_dur, data_length=data_length
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
            f"[策略初始化] KDJ信号策略 | 合约: {self.symbol} | "
            f"N: {self.kdj_n} | M1: {self.kdj_m1} | M2: {self.kdj_m2} | "
            f"超买: {self.overbuy} | 超卖: {self.oversell} | "
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

    def _calc_kdj(self):
        """
        计算KDJ指标

        使用指数平滑迭代法计算K、D、J值

        Returns:
            tuple: (k_series, d_series, j_series) 三个pandas Series
        """
        high = self.klines["high"]
        low = self.klines["low"]
        close = self.klines["close"]

        hh = hhv(high, self.kdj_n)
        ll = llv(low, self.kdj_n)

        denominator = hh - ll
        denominator = denominator.replace(0, 1)
        rsv = (close - ll) / denominator * 100

        k_values = []
        k_prev = 50.0
        for rsv_val in rsv:
            if np.isnan(rsv_val):
                k_values.append(np.nan)
            else:
                k_cur = k_prev * (1 - 1.0 / self.kdj_m1) + rsv_val * (1.0 / self.kdj_m1)
                k_values.append(k_cur)
                k_prev = k_cur

        k_series = pd.Series(k_values, index=close.index)

        d_values = []
        d_prev = 50.0
        for k_val in k_series:
            if np.isnan(k_val):
                d_values.append(np.nan)
            else:
                d_cur = d_prev * (1 - 1.0 / self.kdj_m2) + k_val * (1.0 / self.kdj_m2)
                d_values.append(d_cur)
                d_prev = d_cur

        d_series = pd.Series(d_values, index=close.index)
        j_series = 3 * k_series - 2 * d_series

        return k_series, d_series, j_series

    def on_kline_update(self) -> int:
        """
        K线更新时的回调函数

        计算KDJ指标（K、D、J），判断是否出现金叉或死叉信号，并返回相应的目标仓位

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        k, d, j = self._calc_kdj()

        k_cur = k.iloc[-2]
        d_cur = d.iloc[-2]
        j_cur = j.iloc[-2]
        k_prev = k.iloc[-3]
        d_prev = d.iloc[-3]

        golden_cross = (k_prev < d_prev) and (k_cur > d_cur)
        death_cross = (k_prev > d_prev) and (k_cur < d_cur)

        target_volume = 0

        if golden_cross and k_cur < 50:
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(
                f">>> 金叉！K上穿D | K={k_cur:.2f} D={d_cur:.2f} J={j_cur:.2f} | "
                f"目标仓位: +{dynamic_vol}（做多）"
            )
            target_volume = dynamic_vol
            self.last_signal = "golden"

        elif death_cross and k_cur > 50:
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(
                f">>> 死叉！K下穿D | K={k_cur:.2f} D={d_cur:.2f} J={j_cur:.2f} | "
                f"目标仓位: -{dynamic_vol}（做空）"
            )
            target_volume = -dynamic_vol
            self.last_signal = "death"

        if self.current_target_volume > 0 and k_cur > self.overbuy:
            self.logger.info(
                f">>> 超买止盈平多！K={k_cur:.2f}>{self.overbuy} | 目标仓位: 0"
            )
            target_volume = 0
            self.last_signal = "overbuy_exit"

        elif self.current_target_volume < 0 and k_cur < self.oversell:
            self.logger.info(
                f">>> 超卖止盈平空！K={k_cur:.2f}<{self.oversell} | 目标仓位: 0"
            )
            target_volume = 0
            self.last_signal = "oversell_exit"

        return target_volume

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

            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                self.logger.info(f"[策略结束] 达到最大迭代次数: {max_iterations}")
                break

    def get_account_snapshot(self) -> dict:
        return self._last_account_snapshot

    def set_target_volume(self, volume: int) -> None:
        self.target_pos.set_target_volume(volume)


def create_strategy(
    api: TqApi,
    logger,
    symbol: str = "DCE.m2506",
    kdj_n: int = 9,
    kdj_m1: int = 3,
    kdj_m2: int = 3,
    overbuy: int = 80,
    oversell: int = 20,
    kline_dur: int = 60 * 30,
    volume: int = 1,
) -> KDJSignalStrategy:
    """
    创建KDJ信号策略实例的工厂函数

    Args:
        api: TqApi 实例
        logger: 日志记录器
        symbol: 交易合约代码
        kdj_n: RSV计算周期
        kdj_m1: K值平滑参数
        kdj_m2: D值平滑参数
        overbuy: 超买阈值
        oversell: 超卖阈值
        kline_dur: K线周期（秒）
        volume: 持仓手数

    Returns:
        KDJSignalStrategy: 策略实例
    """
    return KDJSignalStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        kdj_n=kdj_n,
        kdj_m1=kdj_m1,
        kdj_m2=kdj_m2,
        overbuy=overbuy,
        oversell=oversell,
        kline_dur=kline_dur,
        volume=volume,
    )
