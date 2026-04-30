#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一目均衡图趋势策略 (Ichimoku Cloud Strategy)
====================================================

策略逻辑（状态驱动）：
    - 每根K线基于一目均衡图当前状态判断目标仓位，而非仅在交叉瞬间触发
    - 做多条件：转换线 > 基准线 且 价格 > 云顶
    - 做空条件：转换线 < 基准线 且 价格 < 云底
    - 平仓条件：价格进入云区 / 转换线与基准线反向交叉
    - 金叉/死叉作为信号加强，但不再作为唯一入场条件
    - 使用 TargetPosTask 管理持仓，无需手动处理追单、撤单、部分成交等细节

适用品种：
    趋势性较强的品种，如螺纹钢（SHFE.rb）、原油（INE.sc）、铜（SHFE.cu）等

风险提示：
    - Ichimoku云图滞后性较大，在震荡行情中容易产生假信号
    - 建议结合成交量、波动率等过滤器使用
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from tqsdk import TqApi, TargetPosTask
from tqsdk.tafunc import hhv, llv
import numpy as np


class IchimokuCloudStrategy:
    """
    一目均衡图策略类
    
    使用方式：
        strategy = IchimokuCloudStrategy(api, logger, symbol="SHFE.rb2605", tenkan_period=9, kijun_period=26, senkou_period=52)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "SHFE.rb2605"
    DEFAULT_TENKAN_PERIOD = 9
    DEFAULT_KIJUN_PERIOD = 26
    DEFAULT_SENKOU_PERIOD = 52
    DEFAULT_KLINE_DUR = 60 * 60
    DEFAULT_VOLUME = 1

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        tenkan_period: int = None,
        kijun_period: int = None,
        senkou_period: int = None,
        kline_dur: int = None,
        volume: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.tenkan_period = tenkan_period or self.DEFAULT_TENKAN_PERIOD
        self.kijun_period = kijun_period or self.DEFAULT_KIJUN_PERIOD
        self.senkou_period = senkou_period or self.DEFAULT_SENKOU_PERIOD
        self.kline_dur = kline_dur or self.DEFAULT_KLINE_DUR
        self.volume = volume or self.DEFAULT_VOLUME
        self.use_continuous = use_continuous
        self.initial_balance = initial_balance
        self.margin_ratio = margin_ratio

        max_period = max(self.tenkan_period, self.kijun_period, self.senkou_period)
        data_length = max_period * 3 + 50
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
        self._prev_tenkan = None
        self._prev_kijun = None

        self._use_insert_order = False
        self._current_position = 0
        self._on_kline_iteration = 0
        self._UNSUPPORTED_TARGETPOS_PREFIXES = {
            'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
            'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
        }

        self.logger.info(
            f"[策略初始化] 一目均衡图策略 | 合约: {self.symbol} | "
            f"转换线: {self.tenkan_period} | 基准线: {self.kijun_period} | "
            f"先行线: {self.senkou_period} | "
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
            if self.target_pos is not None and not self._use_insert_order:
                try:
                    self.target_pos.set_target_volume(self.current_target_volume)
                    self.logger.info(f"[换月] 在新合约 {new_symbol} 上设置仓位: {self.current_target_volume}")
                except Exception as e:
                    self.logger.warning(f"[换月] 设置仓位失败: {e}")
            elif self._pending_signal is not None:
                self.logger.info(f"[换月] 有暂存信号 {self._pending_signal}，将在下次K线更新时执行")

        if self._pending_signal is not None and self.target_pos is not None and not self._use_insert_order:
            try:
                self.target_pos.set_target_volume(self._pending_signal)
                self.logger.info(f"[换月] 执行暂存信号: {self._pending_signal}")
                self._pending_signal = None
            except Exception as e:
                self.logger.warning(f"[换月] 执行暂存信号失败: {e}")

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

    def _calculate_ichimoku(self):
        """
        计算Ichimoku云图指标

        Returns:
            tuple: (tenkan, kijun, senkou_a, senkou_b) 或 (None, None, None, None)
        """
        high = self.klines.high
        low = self.klines.low
        close = self.klines.close

        if len(high) < self.senkou_period + 10:
            return None, None, None, None

        tenkan = (hhv(high, self.tenkan_period).iloc[-1] + llv(low, self.tenkan_period).iloc[-1]) / 2
        kijun = (hhv(high, self.kijun_period).iloc[-1] + llv(low, self.kijun_period).iloc[-1]) / 2
        senkou_a = (tenkan + kijun) / 2
        senkou_b = (hhv(high, self.senkou_period).iloc[-1] + llv(low, self.senkou_period).iloc[-1]) / 2

        if np.isnan(tenkan) or np.isnan(kijun) or np.isnan(senkou_a) or np.isnan(senkou_b):
            return None, None, None, None

        return tenkan, kijun, senkou_a, senkou_b

    def on_kline_update(self) -> int:
        """
        K线更新时的回调函数（状态驱动）

        基于当前一目均衡图的状态判断目标仓位，而非仅在交叉瞬间触发：
          - 做多条件：转换线 > 基准线 且 价格 > 云顶
          - 做空条件：转换线 < 基准线 且 价格 < 云底
          - 平多条件：转换线跌破基准线 或 价格跌破云底
          - 平空条件：转换线升破基准线 或 价格升破云顶
          - 价格在云区内：视为震荡，平仓观望

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        tenkan, kijun, senkou_a, senkou_b = self._calculate_ichimoku()

        if tenkan is None or kijun is None:
            return self.current_target_volume

        current_price = self.klines.close.iloc[-1]

        if np.isnan(current_price) or current_price <= 0:
            return self.current_target_volume

        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)

        price_above_cloud = current_price > cloud_top
        price_below_cloud = current_price < cloud_bottom
        price_in_cloud = not price_above_cloud and not price_below_cloud

        tenkan_above_kijun = tenkan > kijun
        tenkan_below_kijun = tenkan < kijun

        is_golden_cross = (
            self._prev_tenkan is not None
            and self._prev_kijun is not None
            and self._prev_tenkan <= self._prev_kijun
            and tenkan > kijun
        )
        is_death_cross = (
            self._prev_tenkan is not None
            and self._prev_kijun is not None
            and self._prev_tenkan >= self._prev_kijun
            and tenkan < kijun
        )

        target_volume = self.current_target_volume

        if self._on_kline_iteration % 20 == 0:
            self.logger.info(
                f"[指标] 价格:{current_price:.2f} | T:{tenkan:.2f} K:{kijun:.2f} | "
                f"云区:[{cloud_bottom:.2f},{cloud_top:.2f}] | "
                f"价格{'在云上' if price_above_cloud else '在云下' if price_below_cloud else '在云中'} | "
                f"{'T>K' if tenkan_above_kijun else 'T<K' if tenkan_below_kijun else 'T=K'} | "
                f"当前仓位:{self.current_target_volume}"
            )
        self._on_kline_iteration += 1

        if price_in_cloud:
            if self.current_target_volume != 0:
                self.logger.info(
                    f">>> 价格进入云区，平仓观望 | "
                    f"价格:{current_price:.2f} 云区:[{cloud_bottom:.2f},{cloud_top:.2f}]"
                )
            target_volume = 0
            self.last_signal = "neutral_cloud"

        elif price_above_cloud and tenkan_above_kijun:
            dynamic_vol = self._calc_dynamic_volume()
            if is_golden_cross:
                self.logger.info(
                    f">>> 金叉+云上确认！目标仓位: +{dynamic_vol}（做多）| "
                    f"价格:{current_price:.2f} 云顶:{cloud_top:.2f}"
                )
            elif self.current_target_volume <= 0:
                self.logger.info(
                    f">>> 趋势做多（转换线>基准线+价格在云上）| 目标仓位: +{dynamic_vol} | "
                    f"价格:{current_price:.2f} T:{tenkan:.2f} K:{kijun:.2f} 云顶:{cloud_top:.2f}"
                )
            target_volume = dynamic_vol
            self.last_signal = "long"

        elif price_below_cloud and tenkan_below_kijun:
            dynamic_vol = self._calc_dynamic_volume()
            if is_death_cross:
                self.logger.info(
                    f">>> 死叉+云下确认！目标仓位: -{dynamic_vol}（做空）| "
                    f"价格:{current_price:.2f} 云底:{cloud_bottom:.2f}"
                )
            elif self.current_target_volume >= 0:
                self.logger.info(
                    f">>> 趋势做空（转换线<基准线+价格在云下）| 目标仓位: -{dynamic_vol} | "
                    f"价格:{current_price:.2f} T:{tenkan:.2f} K:{kijun:.2f} 云底:{cloud_bottom:.2f}"
                )
            target_volume = -dynamic_vol
            self.last_signal = "short"

        elif price_above_cloud and tenkan_below_kijun:
            if self.current_target_volume > 0:
                self.logger.info(
                    f">>> 转换线跌破基准线（云上），平多 | "
                    f"价格:{current_price:.2f} T:{tenkan:.2f} K:{kijun:.2f}"
                )
                target_volume = 0
                self.last_signal = "close_long_tk_cross"
            elif self.current_target_volume == 0:
                if is_death_cross:
                    self.logger.info(
                        f">>> 死叉但价格仍在云上，观望 | "
                        f"价格:{current_price:.2f} T:{tenkan:.2f} K:{kijun:.2f}"
                    )
                target_volume = 0
                self.last_signal = "neutral_above_cloud"

        elif price_below_cloud and tenkan_above_kijun:
            if self.current_target_volume < 0:
                self.logger.info(
                    f">>> 转换线升破基准线（云下），平空 | "
                    f"价格:{current_price:.2f} T:{tenkan:.2f} K:{kijun:.2f}"
                )
                target_volume = 0
                self.last_signal = "close_short_tk_cross"
            elif self.current_target_volume == 0:
                if is_golden_cross:
                    self.logger.info(
                        f">>> 金叉但价格仍在云下，观望 | "
                        f"价格:{current_price:.2f} T:{tenkan:.2f} K:{kijun:.2f}"
                    )
                target_volume = 0
                self.last_signal = "neutral_below_cloud"

        self._prev_tenkan = tenkan
        self._prev_kijun = kijun

        return target_volume

    def run(self, max_iterations: int = None) -> None:
        """
        运行策略主循环

        Args:
            max_iterations: 最大迭代次数（用于回测），None 表示无限循环
        """
        iteration = 0
        last_kline_id = None
        _contract_init_logged = False

        while True:
            self.api.wait_update()

            if self.use_continuous and self.target_pos is None:
                if hasattr(self.quote, 'underlying_symbol') and self.quote.underlying_symbol:
                    self._switch_contract(self.quote.underlying_symbol)
                    _contract_init_logged = False
                else:
                    if not _contract_init_logged:
                        self.logger.info(
                            f"[连续合约] 等待 {self.symbol} 的 underlying_symbol 解析... "
                            f"当前值: {getattr(self.quote, 'underlying_symbol', 'N/A')}"
                        )
                        _contract_init_logged = True

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

            if target_volume != self.current_target_volume:
                if self.use_continuous and self.current_trading_symbol is None:
                    if target_volume != 0:
                        self._pending_signal = target_volume
                        self.logger.info(
                            f"[交易-等待合约] 目标仓位: {target_volume} | "
                            f"等待 underlying_symbol 解析后执行"
                        )
                    self.current_target_volume = target_volume
                    iteration += 1
                    continue

                self.current_target_volume = target_volume
                current_time_t = self.klines.datetime.iloc[-1]
                from datetime import datetime
                trade_date = datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")

                if self._use_insert_order:
                    try:
                        if target_volume == 0:
                            if self._current_position > 0:
                                direction = "SELL"
                                offset = "CLOSE"
                                vol = abs(self._current_position)
                            elif self._current_position < 0:
                                direction = "BUY"
                                offset = "CLOSE"
                                vol = abs(self._current_position)
                            else:
                                self.logger.info(f"[交易-insert] 日期: {trade_date} | 已无持仓，跳过平仓")
                                self._pending_signal = None
                                iteration += 1
                                continue
                        else:
                            if self._current_position > 0 and target_volume < 0:
                                direction = "SELL"
                                offset = "CLOSE"
                                vol = abs(self._current_position)
                                self.api.insert_order(
                                    symbol=self.current_trading_symbol,
                                    direction=direction,
                                    offset=offset,
                                    volume=vol,
                                )
                                self.logger.info(f"[交易-insert平仓] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{vol}")
                                direction = "SELL"
                                offset = "OPEN"
                                vol = abs(target_volume)
                            elif self._current_position < 0 and target_volume > 0:
                                direction = "BUY"
                                offset = "CLOSE"
                                vol = abs(self._current_position)
                                self.api.insert_order(
                                    symbol=self.current_trading_symbol,
                                    direction=direction,
                                    offset=offset,
                                    volume=vol,
                                )
                                self.logger.info(f"[交易-insert平仓] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{vol}")
                                direction = "BUY"
                                offset = "OPEN"
                                vol = abs(target_volume)
                            else:
                                direction = "BUY" if target_volume > 0 else "SELL"
                                offset = "OPEN"
                                vol = abs(target_volume)
                        order = self.api.insert_order(
                            symbol=self.current_trading_symbol,
                            direction=direction,
                            offset=offset,
                            volume=vol,
                        )
                        self.logger.info(f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | offset:{offset} | 手数:{vol}")
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
    symbol: str = "SHFE.rb2501",
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_period: int = 52,
    kline_dur: int = 60 * 60,
    volume: int = 1,
) -> IchimokuCloudStrategy:
    """
    创建一目均衡图策略实例的工厂函数

    Args:
        api: TqApi 实例
        logger: 日志记录器
        symbol: 交易合约代码
        tenkan_period: 转换线周期
        kijun_period: 基准线周期
        senkou_period: 先行线周期
        kline_dur: K线周期（秒）
        volume: 持仓手数

    Returns:
        IchimokuCloudStrategy: 策略实例
    """
    return IchimokuCloudStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        tenkan_period=tenkan_period,
        kijun_period=kijun_period,
        senkou_period=senkou_period,
        kline_dur=kline_dur,
        volume=volume,
    )
