#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开盘区间突破策略 (Opening Range Breakout Strategy)
====================================================

策略逻辑：
    - 在交易日开盘后前N分钟（默认30分钟）内，记录最高价和最低价，形成"开盘区间"
    - 开盘区间确立后，监控价格突破：
      - 价格向上突破区间高点：做多
      - 价格向下突破区间低点：做空
    - 每天只交易一次，建仓后不再接受新信号
    - 收盘前固定时间强制平仓，避免隔夜风险
    - 止损距离 = 区间宽度 × 倍数

适用品种：
    开盘趋势性强的品种，如股指期货（IF、IC、IM）、原油（SC）、黄金（AU）等

风险提示：
    - 假突破（价格突破后反转）频繁发生，需要过滤
    - 在开盘区间过宽的日子，止损距离大，风险较高
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from tqsdk import TqApi, TargetPosTask
import datetime


class OpeningRangeBreakoutStrategy:
    """
    开盘区间突破策略类

    使用方式：
        strategy = OpeningRangeBreakoutStrategy(api, logger, symbol="CFFEX.IF2506")
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "KQ.m@CFFEX.IF"
    DEFAULT_OPEN_RANGE_MINUTES = 30
    DEFAULT_OPEN_HOUR = 9
    DEFAULT_OPEN_MIN = 30
    DEFAULT_CLOSE_HOUR = 14
    DEFAULT_CLOSE_MIN = 45
    DEFAULT_STOP_LOSS_MULTIPLIER = 1.0
    DEFAULT_KLINE_DUR = 60
    DEFAULT_VOLUME = 1

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
        open_range_minutes: int = None,
        open_hour: int = None,
        open_min: int = None,
        close_hour: int = None,
        close_min: int = None,
        stop_loss_multiplier: float = None,
        kline_dur: int = None,
        volume: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.open_range_minutes = open_range_minutes or self.DEFAULT_OPEN_RANGE_MINUTES
        self.open_hour = open_hour if open_hour is not None else self.DEFAULT_OPEN_HOUR
        self.open_min = open_min if open_min is not None else self.DEFAULT_OPEN_MIN
        self.close_hour = close_hour if close_hour is not None else self.DEFAULT_CLOSE_HOUR
        self.close_min = close_min if close_min is not None else self.DEFAULT_CLOSE_MIN
        self.stop_loss_multiplier = stop_loss_multiplier if stop_loss_multiplier is not None else self.DEFAULT_STOP_LOSS_MULTIPLIER
        self.kline_dur = kline_dur or self.DEFAULT_KLINE_DUR
        self.volume = volume or self.DEFAULT_VOLUME
        self.use_continuous = use_continuous
        self.initial_balance = initial_balance
        self.margin_ratio = margin_ratio

        orb_end_min = self.open_min + self.open_range_minutes
        orb_end_hour = self.open_hour
        if orb_end_min >= 60:
            orb_end_hour += 1
            orb_end_min -= 60
        self.orb_end_hour = orb_end_hour
        self.orb_end_min = orb_end_min

        self.klines = api.get_kline_serial(
            self.symbol, self.kline_dur, data_length=200
        )

        if self.use_continuous:
            self.quote = api.get_quote(self.symbol)
            self.current_trading_symbol = None
            self.target_pos = None
        else:
            self.current_trading_symbol = self.symbol
            self.target_pos = TargetPosTask(api, self.symbol)
            self._adapt_volume_to_min(self.symbol)

        self.orb_high = None
        self.orb_low = None
        self.orb_confirmed = False
        self.traded_today = False
        self.current_date = None
        self.stop_loss_price = None
        self.current_target_volume = 0
        self._last_account_snapshot = None
        self._initial_balance = None
        self._pending_signal = None
        self._use_insert_order = False
        self._current_position = 0

        self.logger.info(
            f"[策略初始化] 开盘区间突破策略 | 合约: {self.symbol} | "
            f"开盘区间: {self.open_range_minutes}分钟 | "
            f"开盘时间: {self.open_hour:02d}:{self.open_min:02d} | "
            f"区间结束: {self.orb_end_hour:02d}:{self.orb_end_min:02d} | "
            f"收盘平仓: {self.close_hour:02d}:{self.close_min:02d} | "
            f"止损倍数: {self.stop_loss_multiplier} | "
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

    def _reset_daily_state(self):
        self.orb_high = None
        self.orb_low = None
        self.orb_confirmed = False
        self.traded_today = False
        self.stop_loss_price = None
        self.logger.info(f"[ORB策略] 新交易日开始，状态已重置")

    def on_kline_update(self) -> int:
        bar_dt_ns = self.klines["datetime"].iloc[-2]
        bar_dt = datetime.datetime.fromtimestamp(bar_dt_ns / 1e9)
        bar_date = bar_dt.date()
        bar_time = bar_dt.time()

        if self.current_date != bar_date:
            self.current_date = bar_date
            self._reset_daily_state()

        close_time = datetime.time(self.close_hour, self.close_min)
        if bar_time >= close_time:
            if self.current_target_volume != 0:
                self.logger.info(f"[ORB策略] 收盘强制平仓：时间={bar_time}")
                self.current_target_volume = 0
                return 0
            return self.current_target_volume

        open_time = datetime.time(self.open_hour, self.open_min)
        orb_end_time = datetime.time(self.orb_end_hour, self.orb_end_min)

        if open_time <= bar_time < orb_end_time:
            bar_high = self.klines["high"].iloc[-2]
            bar_low = self.klines["low"].iloc[-2]

            if self.orb_high is None:
                self.orb_high = bar_high
                self.orb_low = bar_low
            else:
                self.orb_high = max(self.orb_high, bar_high)
                self.orb_low = min(self.orb_low, bar_low)

            self.logger.info(
                f"[ORB策略] 建立开盘区间中 {bar_time}："
                f"区间高={self.orb_high:.2f}，区间低={self.orb_low:.2f}"
            )
            return self.current_target_volume

        elif bar_time >= orb_end_time and not self.orb_confirmed:
            if self.orb_high is not None and self.orb_low is not None:
                self.orb_confirmed = True
                orb_range = self.orb_high - self.orb_low
                self.logger.info(
                    f"[ORB策略] 开盘区间确立：高={self.orb_high:.2f}，"
                    f"低={self.orb_low:.2f}，宽度={orb_range:.2f}"
                )
            return self.current_target_volume

        elif self.orb_confirmed and not self.traded_today:
            quote = self.api.get_quote(self.current_trading_symbol or self.symbol)
            current_price = quote.last_price
            if current_price <= 0 or current_price != current_price:
                return self.current_target_volume

            orb_range = self.orb_high - self.orb_low
            stop_dist = orb_range * self.stop_loss_multiplier

            if self.stop_loss_price is not None:
                position = self.api.get_position(self.current_trading_symbol or self.symbol)
                if position.volume_long > 0 and current_price < self.stop_loss_price:
                    self.logger.info(
                        f"[ORB策略] 多仓止损触发：价格={current_price:.2f}，"
                        f"止损线={self.stop_loss_price:.2f}"
                    )
                    self.traded_today = True
                    self.current_target_volume = 0
                    return 0

                if position.volume_short > 0 and current_price > self.stop_loss_price:
                    self.logger.info(
                        f"[ORB策略] 空仓止损触发：价格={current_price:.2f}，"
                        f"止损线={self.stop_loss_price:.2f}"
                    )
                    self.traded_today = True
                    self.current_target_volume = 0
                    return 0

            position = self.api.get_position(self.current_trading_symbol or self.symbol)
            if position.volume_long == 0 and position.volume_short == 0:
                dynamic_vol = self._calc_dynamic_volume()

                if current_price > self.orb_high:
                    self.stop_loss_price = current_price - stop_dist
                    self.traded_today = True
                    self.current_target_volume = dynamic_vol
                    self.logger.info(
                        f"[ORB策略] 向上突破开多！"
                        f"价格={current_price:.2f}，区间高={self.orb_high:.2f}，"
                        f"止损={self.stop_loss_price:.2f}，开{dynamic_vol}手"
                    )
                    return dynamic_vol

                elif current_price < self.orb_low:
                    self.stop_loss_price = current_price + stop_dist
                    self.traded_today = True
                    self.current_target_volume = -dynamic_vol
                    self.logger.info(
                        f"[ORB策略] 向下突破开空！"
                        f"价格={current_price:.2f}，区间低={self.orb_low:.2f}，"
                        f"止损={self.stop_loss_price:.2f}，开{dynamic_vol}手"
                    )
                    return -dynamic_vol

        return self.current_target_volume

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

            if target_volume != self.current_target_volume or target_volume != 0:
                self.current_target_volume = target_volume
                current_time_t = self.klines.datetime.iloc[-1]
                trade_date = datetime.datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")

                if self._use_insert_order:
                    try:
                        if target_volume == 0 and self._current_position != 0:
                            if self._current_position > 0:
                                direction = "SELL"
                                offset = "CLOSE"
                            else:
                                direction = "BUY"
                                offset = "CLOSE"
                            order = self.api.insert_order(
                                symbol=self.current_trading_symbol,
                                direction=direction,
                                offset=offset,
                                volume=abs(self._current_position),
                            )
                            self.logger.info(f"[交易-insert平仓] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{abs(self._current_position)}")
                            self._current_position = 0
                        elif target_volume != 0:
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
                            if target_volume == 0 and self._current_position != 0:
                                if self._current_position > 0:
                                    direction = "SELL"
                                    offset = "CLOSE"
                                else:
                                    direction = "BUY"
                                    offset = "CLOSE"
                                order = self.api.insert_order(
                                    symbol=self.current_trading_symbol,
                                    direction=direction,
                                    offset=offset,
                                    volume=abs(self._current_position),
                                )
                                self.logger.info(f"[交易-insert平仓] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{abs(self._current_position)}")
                                self._current_position = 0
                            elif target_volume != 0:
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
                trade_date = datetime.datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")
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
                check_date = datetime.datetime.fromtimestamp(current_time / 1000000000).strftime("%Y-%m-%d %H:%M:%S")
                snap = self._last_account_snapshot
                self.logger.info(f"[账户检查] 日期: {check_date} | 账户权益: {snap['balance']:.2f} | 可用资金: {snap['available']:.2f} | 持仓盈亏: {snap['position_profit']:.2f} | 平仓盈亏: {snap['close_profit']:.2f} | 手续费: {snap['commission']:.2f}")

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
    symbol: str = "KQ.m@CFFEX.IF",
    open_range_minutes: int = 30,
    open_hour: int = 9,
    open_min: int = 30,
    close_hour: int = 14,
    close_min: int = 45,
    stop_loss_multiplier: float = 1.0,
    kline_dur: int = 60,
    volume: int = 1,
) -> OpeningRangeBreakoutStrategy:
    return OpeningRangeBreakoutStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        open_range_minutes=open_range_minutes,
        open_hour=open_hour,
        open_min=open_min,
        close_hour=close_hour,
        close_min=close_min,
        stop_loss_multiplier=stop_loss_multiplier,
        kline_dur=kline_dur,
        volume=volume,
    )
