#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量价趋势策略 (Volume Price Trend Strategy)
====================================================

策略逻辑：
    - 使用N期价格通道（hhv/llv）判断价格是否创新高/新低（突破信号）
    - 使用M期平均成交量判断当前成交量是否放大（放量确认）
    - 价格突破 AND 成交量放大 → 双重确认开仓
    - 价格回归通道内部 → 平仓
    - 使用 TargetPosTask 管理持仓，无需手动处理追单、撤单、部分成交等细节

适用品种：
    流动性好、成交量数据可靠的品种，如沪铜（SHFE.cu）、螺纹钢（SHFE.rb）、股指（CFFEX.IF）

风险提示：
    - 成交量放大的阈值（VOL_MULTIPLIER）需要根据品种特性调整
    - 在流动性不佳时段，成交量数据噪声大
    - 期货连续合约换月时成交量会出现异常跳变
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from tqsdk import TqApi, TargetPosTask
from tqsdk.tafunc import hhv, llv, ma


class VolumePriceTrendStrategy:
    """
    量价趋势策略类

    使用方式：
        strategy = VolumePriceTrendStrategy(api, logger, symbol="SHFE.cu2606", breakout_n=20, exit_n=10, vol_ma_n=20, vol_multiplier=1.5)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "SHFE.cu2606"
    DEFAULT_BREAKOUT_N = 10
    DEFAULT_EXIT_N = 5
    DEFAULT_VOL_MA_N = 10
    DEFAULT_VOL_MULTIPLIER = 1.2
    DEFAULT_KLINE_DUR = 86400
    DEFAULT_VOLUME = 1
    DEFAULT_DATA_LENGTH = 150

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        breakout_n: int = None,
        exit_n: int = None,
        vol_ma_n: int = None,
        vol_multiplier: float = None,
        kline_dur: int = None,
        volume: int = None,
        data_length: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        """
        初始化量价趋势策略

        Args:
            api: TqApi 实例，用于与期货交易系统交互
            logger: 日志记录器，用于记录策略运行信息
            symbol: 交易合约代码，格式为 "交易所.合约代码"，或连续合约如 "KQ.m@SHFE.cu"
            breakout_n: 突破通道周期（K线根数）
            exit_n: 平仓通道周期（K线根数）
            vol_ma_n: 成交量均线周期（K线根数）
            vol_multiplier: 放量倍数阈值
            kline_dur: K线周期（秒），86400=日线，3600=1小时K线
            volume: 固定持仓手数（目标仓位的绝对值）。当使用动态仓位时此值作为保底参考
            data_length: 获取K线数量
            use_continuous: 是否使用连续主力合约
            initial_balance: 初始资金（元），用于动态仓位计算
            margin_ratio: 保证金比例（0~1），每次开仓用总资产的该比例作为保证金
        """
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.breakout_n = breakout_n or self.DEFAULT_BREAKOUT_N
        self.exit_n = exit_n or self.DEFAULT_EXIT_N
        self.vol_ma_n = vol_ma_n or self.DEFAULT_VOL_MA_N
        self.vol_multiplier = vol_multiplier or self.DEFAULT_VOL_MULTIPLIER
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
        self._UNSUPPORTED_TARGETPOS_PREFIXES = {
            'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
            'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
        }

        self.logger.info(
            f"[策略初始化] 量价趋势策略 | 合约: {self.symbol} | "
            f"突破周期: {self.breakout_n} | 平仓周期: {self.exit_n} | "
            f"量线周期: {self.vol_ma_n} | 放量倍数: {self.vol_multiplier} | "
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

    def on_kline_update(self) -> int:
        """
        K线更新时的回调函数

        计算价格通道和成交量指标，判断是否出现量价确认信号，并返回相应的目标仓位

        信号优先级：
            1. 反转信号（持多时出现空头突破 / 持空时出现多头突破）→ 直接反手
            2. 止损平仓信号（持多时跌破exit低点 / 持空时突破exit高点）→ 平仓
            3. 开仓信号（价格突破+放量确认）→ 开仓
            4. 无信号 → 维持当前仓位

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        close = self.klines.close
        volume = self.klines.volume
        high = self.klines.high
        low = self.klines.low

        channel_high_n = hhv(close, self.breakout_n)
        channel_low_n = llv(close, self.breakout_n)

        channel_high_exit = hhv(high, self.exit_n)
        channel_low_exit = llv(low, self.exit_n)

        vol_ma = ma(volume, self.vol_ma_n)

        close_cur = close.iloc[-2]
        prev_channel_high = channel_high_n.iloc[-3]
        prev_channel_low = channel_low_n.iloc[-3]

        vol_cur = volume.iloc[-2]
        vol_ma_cur = vol_ma.iloc[-2]

        if vol_ma_cur > 0:
            vol_ratio = vol_cur / vol_ma_cur
        else:
            vol_ratio = 0

        exit_high = channel_high_exit.iloc[-2]
        exit_low = channel_low_exit.iloc[-2]

        is_big_volume = vol_ratio >= self.vol_multiplier

        is_breakout_up = close_cur > prev_channel_high
        is_breakout_down = close_cur < prev_channel_low

        target_volume = self.current_target_volume

        if self.current_target_volume > 0:
            if is_breakout_down and is_big_volume:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(
                    f">>> 反转：多→空！"
                    f"价格={close_cur:.2f}<{prev_channel_low:.2f}，"
                    f"量比={vol_ratio:.2f}x，目标{-dynamic_vol}手"
                )
                target_volume = -dynamic_vol
                self.last_signal = "reverse_to_short"
            elif close_cur < exit_low:
                self.logger.info(
                    f">>> 平多仓：价格{close_cur:.2f} < "
                    f"{self.exit_n}期低点{exit_low:.2f}，平仓"
                )
                target_volume = 0
                self.last_signal = "close_long"

        elif self.current_target_volume < 0:
            if is_breakout_up and is_big_volume:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(
                    f">>> 反转：空→多！"
                    f"价格={close_cur:.2f}>{prev_channel_high:.2f}，"
                    f"量比={vol_ratio:.2f}x，目标{dynamic_vol}手"
                )
                target_volume = dynamic_vol
                self.last_signal = "reverse_to_long"
            elif close_cur > exit_high:
                self.logger.info(
                    f">>> 平空仓：价格{close_cur:.2f} > "
                    f"{self.exit_n}期高点{exit_high:.2f}，平仓"
                )
                target_volume = 0
                self.last_signal = "close_short"

        else:
            if is_breakout_up and is_big_volume:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(
                    f">>> 量价多头开多！"
                    f"价格={close_cur:.2f}>{prev_channel_high:.2f}，"
                    f"量比={vol_ratio:.2f}x，目标{dynamic_vol}手"
                )
                target_volume = dynamic_vol
                self.last_signal = "long"

            elif is_breakout_down and is_big_volume:
                dynamic_vol = self._calc_dynamic_volume()
                self.logger.info(
                    f">>> 量价空头开空！"
                    f"价格={close_cur:.2f}<{prev_channel_low:.2f}，"
                    f"量比={vol_ratio:.2f}x，目标{-dynamic_vol}手"
                )
                target_volume = -dynamic_vol
                self.last_signal = "short"

            else:
                if not is_big_volume and (is_breakout_up or is_breakout_down):
                    self.logger.info(
                        f"[量价策略] 价格突破但量能不足（量比={vol_ratio:.2f}x"
                        f"<{self.vol_multiplier}x），忽略信号（避免假突破）"
                    )

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

            iteration += 1
            if max_iterations is not None and iteration > max_iterations:
                self.logger.info(f"[策略结束] 达到最大迭代次数 {max_iterations}")
                break

            if self.use_continuous:
                if self.current_trading_symbol is None:
                    if hasattr(self.quote, 'underlying_symbol'):
                        underlying = self.quote.underlying_symbol
                        if underlying and underlying != "":
                            self.current_trading_symbol = underlying
                            import re
                            parts = underlying.split('.')
                            prefix = None
                            if len(parts) >= 2:
                                match = re.match(r'([a-zA-Z]+)', parts[1])
                                if match:
                                    prefix = f"{parts[0]}.{match.group(1)}"

                            if prefix in self._UNSUPPORTED_TARGETPOS_PREFIXES:
                                self._use_insert_order = True
                                self.target_pos = None
                                self._current_position = 0
                                self.logger.info(f"[连续合约] {underlying} 不支持TargetPosTask，使用insert_order模式")
                            else:
                                try:
                                    self.target_pos = TargetPosTask(self.api, underlying)
                                    self.logger.info(f"[连续合约] TargetPosTask 创建成功: {underlying}")
                                except Exception as e:
                                    self._use_insert_order = True
                                    self.target_pos = None
                                    self._current_position = 0
                                    self.logger.info(f"[连续合约] TargetPosTask 创建失败: {e}，切换为 insert_order")
                            self._adapt_volume_to_min(underlying)
                            self.logger.info(f"[连续合约] 初始化交易合约: {underlying}")
                    continue

                if hasattr(self.quote, 'underlying_symbol'):
                    underlying = self.quote.underlying_symbol
                    if underlying and underlying != "" and underlying != self.current_trading_symbol:
                        self._switch_contract(underlying)

            if not self.api.is_changing(self.klines):
                continue

            current_kline_id = self.klines.datetime.iloc[-1]
            if current_kline_id == last_kline_id:
                continue
            last_kline_id = current_kline_id

            target_volume = self.on_kline_update()

            if target_volume != self.current_target_volume:
                self.current_target_volume = target_volume

                if self._use_insert_order:
                    self._execute_insert_order(target_volume)
                elif self.target_pos:
                    self.target_pos.set_target_volume(target_volume)

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
            except Exception:
                pass

            if iteration % 100 == 0:
                try:
                    account = self.api.get_account()
                    self.logger.info(
                        f"[账户] 权益:{account.balance:,.0f} | "
                        f"可用:{account.available:,.0f} | "
                        f"浮盈:{account.float_profit:+,.0f} | "
                        f"持仓盈亏:{account.position_profit:+,.0f} | "
                        f"平仓盈亏:{account.close_profit:+,.0f} | "
                        f"保证金:{account.margin:,.0f}"
                    )
                except Exception:
                    pass

    def _execute_insert_order(self, target_volume: int):
        """
        使用 insert_order 直接下单（用于不支持 TargetPosTask 的品种）

        Args:
            target_volume: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        from tqsdk import TqApi

        diff = target_volume - self._current_position

        if diff == 0:
            return

        trading_symbol = self.current_trading_symbol or self.symbol

        try:
            if diff > 0:
                if self._current_position < 0:
                    self.api.insert_order(
                        symbol=trading_symbol,
                        direction="BUY",
                        offset="CLOSETODAY" if self._current_position < 0 else "OPEN",
                        volume=abs(self._current_position),
                    )
                    remaining = diff
                else:
                    remaining = diff

                if remaining > 0:
                    self.api.insert_order(
                        symbol=trading_symbol,
                        direction="BUY",
                        offset="OPEN",
                        volume=remaining,
                    )

            elif diff < 0:
                if self._current_position > 0:
                    self.api.insert_order(
                        symbol=trading_symbol,
                        direction="SELL",
                        offset="CLOSETODAY" if self._current_position > 0 else "OPEN",
                        volume=abs(self._current_position),
                    )
                    remaining = abs(diff) - abs(self._current_position)
                else:
                    remaining = abs(diff)

                if remaining > 0:
                    self.api.insert_order(
                        symbol=trading_symbol,
                        direction="SELL",
                        offset="OPEN",
                        volume=remaining,
                    )

            self._current_position = target_volume
            self.logger.info(f"[insert_order] 目标仓位: {target_volume}, 差值: {diff}")

        except Exception as e:
            self.logger.warning(f"[insert_order] 下单失败: {e}")

    def get_account_snapshot(self):
        """
        获取最后一次保存的账户快照

        Returns:
            dict: 账户快照字典，包含 static_balance、balance 等字段；如果没有快照则返回 None
        """
        return self._last_account_snapshot
