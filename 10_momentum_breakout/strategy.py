#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
价格动量突破策略 (Momentum Breakout Strategy)
====================================================

策略逻辑：
    - 计算过去N根K线的价格涨跌幅（动量值）衡量动量强度
    - 动量超过正阈值（THRESHOLD）且价格在均线之上 → 做多
    - 动量低于负阈值（-THRESHOLD）且价格在均线之下 → 做空
    - 动量回归至平仓阈值以下 → 平仓
    - 使用 TargetPosTask 管理持仓，无需手动处理追单、撤单、部分成交等细节

适用品种：
    趋势性强、动量持续性好的品种，如螺纹钢（SHFE.rb）、原油（INE.sc）、铜（SHFE.cu）等

风险提示：
    - 动量策略在震荡行情中容易产生频繁的假信号
    - 动量阈值的设置对结果影响极大，需要历史数据调参
    - 建议结合ATR标准化动量、止损等风控手段使用
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from tqsdk import TqApi, TargetPosTask
from tqsdk.tafunc import ma


class MomentumBreakoutStrategy:
    """
    动量突破策略类

    使用方式：
        strategy = MomentumBreakoutStrategy(api, logger, symbol="SHFE.rb2506", momentum_n=20, threshold=2.0)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "SHFE.rb2605"
    DEFAULT_MOMENTUM_N = 20
    DEFAULT_THRESHOLD = 2.0
    DEFAULT_EXIT_THRESHOLD = 0.5
    DEFAULT_FILTER_N = 60
    DEFAULT_USE_MA_FILTER = True
    DEFAULT_KLINE_DUR = 60 * 60
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

    _UNSUPPORTED_TARGETPOS_PREFIXES = {
        'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
        'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
    }

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        momentum_n: int = None,
        threshold: float = None,
        exit_threshold: float = None,
        filter_n: int = None,
        use_ma_filter: bool = None,
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
        self.momentum_n = momentum_n or self.DEFAULT_MOMENTUM_N
        self.threshold = threshold or self.DEFAULT_THRESHOLD
        self.exit_threshold = exit_threshold or self.DEFAULT_EXIT_THRESHOLD
        self.filter_n = filter_n or self.DEFAULT_FILTER_N
        self.use_ma_filter = use_ma_filter if use_ma_filter is not None else self.DEFAULT_USE_MA_FILTER
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

        self._use_insert_order = False
        self._current_position = 0

        self.logger.info(
            f"[策略初始化] 动量突破策略 | 合约: {self.symbol} | "
            f"动量周期: {self.momentum_n} | 开仓阈值: {self.threshold}% | "
            f"平仓阈值: {self.exit_threshold}% | 均线过滤: {self.use_ma_filter} | "
            f"连续合约: {self.use_continuous} | "
            f"初始资金: {self.initial_balance} | 保证金比例: {self.margin_ratio}"
        )

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
                try:
                    self.target_pos.cancel()
                except Exception:
                    pass
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

    def _get_position_info(self):
        """获取当前持仓信息"""
        volume_long = 0
        volume_short = 0
        try:
            trading_symbol = self.current_trading_symbol or self.symbol
            position = self.api.get_position(trading_symbol)
            volume_long = position.pos_long
            volume_short = position.pos_short
        except Exception:
            pass
        return volume_long, volume_short

    def on_kline_update(self) -> int:
        """
        K线更新时的回调函数

        计算动量值和均线过滤，判断是否出现开仓/平仓信号，并返回相应的目标仓位

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        close = self.klines.close

        close_cur = close.iloc[-2]
        close_n_ago = close.iloc[-2 - self.momentum_n]

        if close_n_ago == 0:
            return self.current_target_volume

        momentum = (close_cur - close_n_ago) / close_n_ago * 100.0

        ma_filter = ma(close, self.filter_n)
        ma_cur = ma_filter.iloc[-2]

        price_above_ma = close_cur > ma_cur
        price_below_ma = close_cur < ma_cur

        volume_long, volume_short = self._get_position_info()

        if volume_long > 0:
            if momentum < self.exit_threshold:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(
                    f">>> 多仓平仓：动量回落至{momentum:.2f}%，平多{volume_long}手"
                )
                self.last_signal = "close_long"
                return 0

        if volume_short > 0:
            if momentum > -self.exit_threshold:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(
                    f">>> 空仓平仓：动量回升至{momentum:.2f}%，平空{volume_short}手"
                )
                self.last_signal = "close_short"
                return 0

        can_go_long = (not self.use_ma_filter) or price_above_ma
        can_go_short = (not self.use_ma_filter) or price_below_ma

        if momentum > self.threshold and can_go_long and volume_long == 0:
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(
                f">>> 开多：动量={momentum:.2f}%>{self.threshold}%，"
                f"价格={close_cur:.2f}，均线={ma_cur:.2f}，开{dynamic_vol}手"
            )
            self.last_signal = "long"
            return dynamic_vol

        elif momentum < -self.threshold and can_go_short and volume_short == 0:
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(
                f">>> 开空：动量={momentum:.2f}%<-{self.threshold}%，"
                f"价格={close_cur:.2f}，均线={ma_cur:.2f}，开{dynamic_vol}手"
            )
            self.last_signal = "short"
            return -dynamic_vol

        return self.current_target_volume

    def save_account_snapshot(self):
        """保存当前账户快照"""
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
            }
        except Exception as e:
            self.logger.warning(f"[账户快照] 保存失败: {e}")

    def get_account_snapshot(self):
        """获取最后一次保存的账户快照"""
        return self._last_account_snapshot

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
                        import re
                        parts = underlying_symbol.split('.')
                        prefix = None
                        if len(parts) >= 2:
                            match = re.match(r'([a-zA-Z]+)', parts[1])
                            if match:
                                prefix = f"{parts[0]}.{match.group(1)}"

                        if prefix in self._UNSUPPORTED_TARGETPOS_PREFIXES:
                            self._use_insert_order = True
                            self.target_pos = None
                            self._current_position = 0
                            self.logger.info(f"[连续合约] {underlying_symbol} 不支持TargetPosTask，使用insert_order模式")
                        else:
                            try:
                                self.target_pos = TargetPosTask(self.api, underlying_symbol)
                                self.logger.info(f"[连续合约] TargetPosTask 创建成功: {underlying_symbol}")
                            except Exception as e:
                                self._use_insert_order = True
                                self.target_pos = None
                                self._current_position = 0
                                self.logger.info(f"[连续合约] TargetPosTask 创建失败: {e}，切换为 insert_order")

                        self._adapt_volume_to_min(underlying_symbol)
                        self.logger.info(f"[连续合约] 底层合约: {underlying_symbol}")

                        if self._pending_signal is not None:
                            self._set_position(self._pending_signal)
                            self._pending_signal = None

                elif self.api.is_changing(self.quote, "underlying_symbol"):
                    new_symbol = self.quote.underlying_symbol
                    if new_symbol and new_symbol != self.current_trading_symbol:
                        self._switch_contract(new_symbol)

            if not self.api.is_changing(self.klines):
                continue

            current_kline_id = self.klines.datetime.iloc[-1]
            if current_kline_id == last_kline_id:
                continue
            last_kline_id = current_kline_id

            target_volume = self.on_kline_update()

            if target_volume != self.current_target_volume:
                self.current_target_volume = target_volume
                if self.target_pos is not None:
                    self.target_pos.set_target_volume(target_volume)
                else:
                    self._pending_signal = target_volume

            self.save_account_snapshot()

            iteration += 1
            if iteration % 100 == 0:
                try:
                    account = self.api.get_account()
                    self.logger.info(
                        f"[账户] 权益:{account.balance:,.0f} | "
                        f"可用:{account.available:,.0f} | "
                        f"浮盈:{account.float_profit:+,.0f} | "
                        f"持仓盈亏:{account.position_profit:+,.0f}"
                    )
                except Exception:
                    pass

            if max_iterations is not None and iteration >= max_iterations:
                self.logger.info(f"[策略] 达到最大迭代次数 {max_iterations}，退出")
                break

    def _set_position(self, target_volume: int):
        """设置目标仓位"""
        if self.target_pos is not None:
            self.target_pos.set_target_volume(target_volume)
        else:
            self._pending_signal = target_volume
