#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡金资金流量策略 (Chaikin Money Flow Strategy)
====================================================

策略逻辑：
    - 使用蔡金资金流量（CMF）指标判断资金流向方向
    - CMF 上穿 +0.05（多头阈值）：资金净流入确认，目标仓位设为 +VOLUME（做多）
    - CMF 下穿 -0.05（空头阈值）：资金净流出确认，目标仓位设为 -VOLUME（做空）
    - CMF 由正转负（跌破0）：多方资金优势消失，平多仓
    - CMF 由负转正（升破0）：空方资金优势消失，平空仓
    - 使用 TargetPosTask 管理持仓，无需手动处理追单、撤单、部分成交等细节

适用品种：
    有稳定成交量的主力合约，如沪铜（CU）、豆粕（M）、螺纹钢（RB）、黄金（AU）

风险提示：
    - CMF 策略在成交量不活跃的品种或时段信号可靠性降低
    - CMF 本身存在一定滞后性（窗口期 N 越大，滞后越明显）
    - 纯粹的 CMF 信号在震荡市中容易发出连续假信号
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from tqsdk import TqApi, TargetPosTask
import pandas as pd


class ChaikinMoneyFlowStrategy:
    """
    蔡金资金流量策略类

    使用方式：
        strategy = ChaikinMoneyFlowStrategy(api, logger, symbol="SHFE.cu2506", cmf_n=20)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "SHFE.cu2606"
    DEFAULT_CMF_N = 20
    DEFAULT_KLINE_DUR = 86400
    DEFAULT_VOLUME = 1
    DEFAULT_BULL_TH = 0.05
    DEFAULT_BEAR_TH = -0.05

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        cmf_n: int = None,
        kline_dur: int = None,
        volume: int = None,
        bull_th: float = None,
        bear_th: float = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.cmf_n = cmf_n or self.DEFAULT_CMF_N
        self.kline_dur = kline_dur or self.DEFAULT_KLINE_DUR
        self.volume = volume or self.DEFAULT_VOLUME
        self.bull_th = bull_th if bull_th is not None else self.DEFAULT_BULL_TH
        self.bear_th = bear_th if bear_th is not None else self.DEFAULT_BEAR_TH
        self.use_continuous = use_continuous
        self.initial_balance = initial_balance
        self.margin_ratio = margin_ratio

        self.klines = api.get_kline_serial(
            self.symbol, self.kline_dur, data_length=self.cmf_n + 10
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
        self.prev_cmf = None

        self._use_insert_order = False
        self._current_position = 0
        self._UNSUPPORTED_TARGETPOS_PREFIXES = {
            'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
            'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
        }

        self.logger.info(
            f"[策略初始化] 蔡金资金流量策略 | 合约: {self.symbol} | "
            f"CMF窗口: {self.cmf_n} | 阈值: {self.bear_th}/{self.bull_th} | "
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

    @staticmethod
    def calc_cmf(klines: pd.DataFrame, n: int) -> pd.Series:
        """
        计算蔡金资金流量指标（Chaikin Money Flow）

        参数：
          klines : TqSdk 返回的 K 线 DataFrame
          n      : 滚动窗口大小

        返回：
          cmf : pd.Series，与 klines 等长
        """
        high = klines["high"]
        low = klines["low"]
        close = klines["close"]
        volume = klines["volume"]

        hl_range = high - low
        hl_range = hl_range.replace(0, float("nan"))

        mfm = (2 * close - high - low) / hl_range
        mfv = mfm * volume
        cmf = mfv.rolling(n).sum() / volume.rolling(n).sum()

        return cmf

    def on_kline_update(self) -> int:
        """
        K线更新时的回调函数

        计算CMF指标，判断是否出现穿越信号，并返回相应的目标仓位

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        cmf_series = self.calc_cmf(self.klines, self.cmf_n)

        current_cmf = cmf_series.iloc[-2]

        if pd.isna(current_cmf):
            self.prev_cmf = current_cmf
            return 0

        target_volume = 0

        if self.prev_cmf is not None and not pd.isna(self.prev_cmf):
            if self.prev_cmf <= self.bull_th and current_cmf > self.bull_th:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(f">>> CMF 上穿 {self.bull_th}，资金净流入！开多 +{dynamic_vol}")
                target_volume = dynamic_vol
                self.last_signal = "bull_cross"

            elif self.prev_cmf >= self.bear_th and current_cmf < self.bear_th:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(f">>> CMF 下穿 {self.bear_th}，资金净流出！开空 -{dynamic_vol}")
                target_volume = -dynamic_vol
                self.last_signal = "bear_cross"

            elif self.prev_cmf >= 0 and current_cmf < 0:
                self.logger.info(">>> CMF 跌破 0，多方资金优势消失，平多")
                target_volume = 0
                self.last_signal = "close_long"

            elif self.prev_cmf <= 0 and current_cmf > 0:
                self.logger.info(">>> CMF 升破 0，空方资金优势消失，平空")
                target_volume = 0
                self.last_signal = "close_short"

        self.prev_cmf = current_cmf
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

            if self.use_continuous:
                if self.current_trading_symbol is None:
                    underlying_symbol = self.quote.underlying_symbol
                    if underlying_symbol and underlying_symbol != "":
                        self.current_trading_symbol = underlying_symbol
                        self.target_pos = TargetPosTask(self.api, underlying_symbol)
                        self._adapt_volume_to_min(underlying_symbol)
                        self.logger.info(f"[连续合约] 底层合约: {underlying_symbol}")
                    continue

                if self.api.is_changing(self.quote, "underlying_symbol"):
                    new_symbol = self.quote.underlying_symbol
                    if new_symbol and new_symbol != self.current_trading_symbol:
                        self._switch_contract(new_symbol)
                        self.klines = self.api.get_kline_serial(
                            self.symbol, self.kline_dur, data_length=self.cmf_n + 10
                        )
                        self.prev_cmf = None

            if not self.api.is_changing(self.klines):
                continue

            current_kline_id = self.klines.datetime.iloc[-1]
            if current_kline_id == last_kline_id:
                continue
            last_kline_id = current_kline_id

            try:
                account = self.api.get_account()
                self._last_account_snapshot = {
                    "static_balance": account.static_balance,
                    "balance": account.balance,
                    "available": account.available,
                    "float_profit": account.float_profit,
                    "position_profit": account.position_profit,
                    "close_profit": account.close_profit,
                    "margin": account.margin,
                    "commission": account.commission,
                    "initial_balance": self._initial_balance,
                }
                if self._initial_balance is None:
                    self._initial_balance = account.static_balance
                    self._last_account_snapshot["initial_balance"] = self._initial_balance
            except Exception:
                pass

            target_volume = self.on_kline_update()

            if target_volume != 0 or (target_volume == 0 and self.current_target_volume != 0):
                self.current_target_volume = target_volume
                if self.target_pos:
                    self.target_pos.set_target_volume(target_volume)

            if iteration % 100 == 0 and self._last_account_snapshot:
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
    symbol: str = "SHFE.cu2606",
    cmf_n: int = 20,
    kline_dur: int = 86400,
    volume: int = 1,
    bull_th: float = 0.05,
    bear_th: float = -0.05,
) -> ChaikinMoneyFlowStrategy:
    """
    创建蔡金资金流量策略实例的工厂函数

    Args:
        api: TqApi 实例
        logger: 日志记录器
        symbol: 交易合约代码
        cmf_n: CMF 计算窗口期
        kline_dur: K线周期（秒）
        volume: 持仓手数
        bull_th: CMF 多头阈值
        bear_th: CMF 空头阈值

    Returns:
        ChaikinMoneyFlowStrategy: 策略实例
    """
    return ChaikinMoneyFlowStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        cmf_n=cmf_n,
        kline_dur=kline_dur,
        volume=volume,
        bull_th=bull_th,
        bear_th=bear_th,
    )
