#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网格交易策略 (Grid Trading Strategy)
=====================================

策略逻辑：
    - 在预设价格区间 [GRID_LOW, GRID_HIGH] 内，按固定间距 GRID_STEP 划分网格线
    - 价格从上方跌穿网格线时：在该网格线价位买入（低买）
    - 价格从下方涨穿网格线时：在该网格线价位卖出（高卖）
    - 价格突破区间上限时：平掉所有多仓
    - 价格跌破区间下限时：停止买入

适用品种：
    价格长期在区间内震荡的品种，如农产品（豆粕、玉米）、贵金属（黄金）
    不适用于单边趋势强烈的品种

风险提示：
    - 单边趋势行情中可能持续买入而价格持续下跌
    - 需要大量资金分散在多个网格层级
    - 本代码仅供学习参考，不构成任何投资建议

参数说明：
    SYMBOL           : 交易合约代码，格式为 "交易所.合约代码"
    GRID_LOW         : 网格区间下限价格
    GRID_HIGH        : 网格区间上限价格
    GRID_STEP        : 网格间距（每格价格差）
    VOLUME           : 每格交易手数
    MAX_GRID_POSITION: 最大允许持仓手数（风控）

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from tqsdk import TqApi, TargetPosTask


class GridTradingStrategy:
    """
    网格交易策略类

    使用方式：
        strategy = GridTradingStrategy(api, logger, symbol="CZCE.MA509", grid_low=2200, grid_high=2600, grid_step=40)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    DEFAULT_SYMBOL = "KQ.m@CZCE.MA"
    DEFAULT_GRID_LOW = 2200
    DEFAULT_GRID_HIGH = 2600
    DEFAULT_GRID_STEP = 40
    DEFAULT_VOLUME = 1
    DEFAULT_MAX_GRID_POSITION = 10

    CONTRACT_MULTIPLIER_MAP = {
        'DCE.l': 5, 'DCE.v': 5, 'DCE.pp': 5,
        'DCE.eg': 10, 'DCE.i': 100, 'DCE.j': 100,
        'DCE.a': 10, 'DCE.b': 10, 'DCE.c': 10,
        'DCE.m': 10, 'DCE.p': 10, 'DCE.y': 10,
        'DCE.eb': 5, 'DCE.jd': 10, 'DCE.lh': 16,
        'DCE.cs': 10, 'DCE.pg': 10, 'DCE.rr': 10,
        'CZCE.TA': 5, 'CZCE.MA': 10, 'CZCE.SR': 10,
        'CZCE.CF': 5, 'CZCE.OI': 10, 'CZCE.FG': 20,
        'CZCE.RM': 10, 'CZCE.SF': 5, 'CZCE.UR': 20,
        'CZCE.SM': 5, 'CZCE.CJ': 5, 'CZCE.PK': 5,
        'CZCE.SA': 20, 'CZCE.AP': 10, 'CZCE.PF': 5,
        'SHFE.rb': 10, 'SHFE.au': 1000, 'SHFE.cu': 5,
        'SHFE.al': 5, 'SHFE.zn': 5, 'SHFE.ni': 1,
        'SHFE.sn': 1, 'SHFE.ss': 10, 'SHFE.ag': 15,
        'SHFE.bu': 10, 'SHFE.ru': 10, 'SHFE.hc': 10,
        'SHFE.sp': 10, 'SHFE.fu': 10, 'SHFE.wr': 10,
        'INE.sc': 1000, 'INE.lu': 10,
        'CFFEX.IF': 300, 'CFFEX.IC': 200, 'CFFEX.IH': 300,
        'CFFEX.IM': 200, 'CFFEX.T': 10000, 'CFFEX.TF': 10000, 'CFFEX.TS': 20000,
    }

    MARGIN_RATE_MAP = {
        'DCE.l': 0.12, 'DCE.v': 0.12, 'DCE.pp': 0.12,
        'DCE.eg': 0.12, 'DCE.i': 0.15, 'DCE.j': 0.15,
        'DCE.a': 0.12, 'DCE.b': 0.12, 'DCE.c': 0.12,
        'DCE.m': 0.12, 'DCE.p': 0.12, 'DCE.y': 0.12,
        'DCE.eb': 0.12, 'DCE.jd': 0.12, 'DCE.lh': 0.12,
        'DCE.cs': 0.12, 'DCE.pg': 0.12, 'DCE.rr': 0.12,
        'CZCE.TA': 0.12, 'CZCE.MA': 0.12, 'CZCE.SR': 0.10,
        'CZCE.CF': 0.12, 'CZCE.OI': 0.12, 'CZCE.FG': 0.12,
        'CZCE.RM': 0.12, 'CZCE.SF': 0.12, 'CZCE.UR': 0.12,
        'CZCE.SM': 0.12, 'CZCE.CJ': 0.15, 'CZCE.PK': 0.15,
        'CZCE.SA': 0.15, 'CZCE.AP': 0.12, 'CZCE.PF': 0.12,
        'SHFE.rb': 0.13, 'SHFE.au': 0.12, 'SHFE.cu': 0.12,
        'SHFE.al': 0.11, 'SHFE.zn': 0.12, 'SHFE.ni': 0.16,
        'SHFE.sn': 0.14, 'SHFE.ss': 0.12, 'SHFE.ag': 0.12,
        'SHFE.bu': 0.12, 'SHFE.ru': 0.13, 'SHFE.hc': 0.14,
        'SHFE.sp': 0.12, 'SHFE.fu': 0.12, 'SHFE.wr': 0.12,
        'INE.sc': 0.15, 'INE.lu': 0.12,
        'CFFEX.IF': 0.14, 'CFFEX.IC': 0.14, 'CFFEX.IH': 0.14,
        'CFFEX.IM': 0.14, 'CFFEX.T': 0.02, 'CFFEX.TF': 0.03, 'CFFEX.TS': 0.02,
    }

    MIN_VOLUME_MAP = {
        'DCE.l': 8, 'DCE.v': 8, 'DCE.pp': 8,
        'DCE.eg': 8, 'DCE.i': 1, 'DCE.j': 1,
        'DCE.a': 1, 'DCE.b': 1, 'DCE.c': 1,
        'DCE.m': 1, 'DCE.p': 1, 'DCE.y': 1,
        'DCE.eb': 1, 'DCE.jd': 1, 'DCE.lh': 1,
        'DCE.cs': 1, 'DCE.pg': 1, 'DCE.rr': 1,
        'CZCE.TA': 8, 'CZCE.MA': 8, 'CZCE.SR': 1,
        'CZCE.CF': 1, 'CZCE.OI': 1, 'CZCE.FG': 1,
        'CZCE.RM': 1, 'CZCE.SF': 1, 'CZCE.UR': 1,
        'CZCE.SM': 1, 'CZCE.CJ': 1, 'CZCE.PK': 1,
        'CZCE.SA': 1, 'CZCE.AP': 2, 'CZCE.PF': 1,
        'SHFE.rb': 1, 'SHFE.au': 1, 'SHFE.cu': 1,
        'SHFE.al': 1, 'SHFE.zn': 1, 'SHFE.ni': 1,
        'SHFE.sn': 1, 'SHFE.ss': 1, 'SHFE.ag': 1,
        'SHFE.bu': 1, 'SHFE.ru': 1, 'SHFE.hc': 1,
        'SHFE.sp': 1, 'SHFE.fu': 1, 'SHFE.wr': 1,
        'INE.sc': 1, 'INE.lu': 1,
        'CFFEX.IF': 1, 'CFFEX.IC': 1, 'CFFEX.IH': 1,
        'CFFEX.IM': 1, 'CFFEX.T': 1, 'CFFEX.TF': 1, 'CFFEX.TS': 1,
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
        grid_low: float = None,
        grid_high: float = None,
        grid_step: float = None,
        volume: int = None,
        max_grid_position: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.grid_low = grid_low if grid_low is not None else self.DEFAULT_GRID_LOW
        self.grid_high = grid_high if grid_high is not None else self.DEFAULT_GRID_HIGH
        self.grid_step = grid_step if grid_step is not None else self.DEFAULT_GRID_STEP
        self.volume = volume or self.DEFAULT_VOLUME
        self.max_grid_position = max_grid_position or self.DEFAULT_MAX_GRID_POSITION
        self.use_continuous = use_continuous
        self.initial_balance = initial_balance
        self.margin_ratio = margin_ratio

        self.grid_lines = []
        price = self.grid_low
        while price <= self.grid_high:
            self.grid_lines.append(round(price, 2))
            price += self.grid_step

        self.grid_has_position = {line: False for line in self.grid_lines}
        self.last_price = None
        self.current_target_volume = 0
        self._last_account_snapshot = None
        self._initial_balance = None
        self._pending_signal = None
        self._use_insert_order = False
        self._current_position = 0

        self.quote = api.get_quote(self.symbol)
        self.klines = api.get_kline_serial(self.symbol, 60, data_length=10)

        if self.use_continuous:
            self.current_trading_symbol = None
            self.target_pos = None
        else:
            self.current_trading_symbol = self.symbol
            self.target_pos = TargetPosTask(api, self.symbol)
            self._adapt_volume_to_min(self.symbol)

        self.logger.info(
            f"[策略初始化] 网格策略 | 合约: {self.symbol} | "
            f"区间: [{self.grid_low}, {self.grid_high}] | 间距: {self.grid_step} | "
            f"网格数: {len(self.grid_lines)} | "
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

        for line in self.grid_lines:
            self.grid_has_position[line] = False
        self.current_target_volume = 0
        self.last_price = None

    def _get_grid_below(self, price):
        below = [g for g in self.grid_lines if g < price]
        return below[-1] if below else None

    def _get_grid_above(self, price):
        above = [g for g in self.grid_lines if g > price]
        return above[0] if above else None

    def _execute_trade(self, target_volume: int, direction: str = None):
        from datetime import datetime
        try:
            current_time_t = self.klines.datetime.iloc[-1]
            trade_date = datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            trade_date = "N/A"

        if self._use_insert_order:
            try:
                if direction is None:
                    direction = "BUY" if target_volume > 0 else "SELL"
                offset = "OPEN"
                order = self.api.insert_order(
                    symbol=self.current_trading_symbol,
                    direction=direction,
                    offset=offset,
                    volume=abs(target_volume),
                )
                self.logger.info(
                    f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | "
                    f"方向:{direction} | 手数:{abs(target_volume)}"
                )
                self._current_position = target_volume
                self._pending_signal = None
            except Exception as e:
                self.logger.info(f"[交易-失败] {e}")
        elif self.target_pos is None:
            self._pending_signal = target_volume
            self.logger.info(
                f"[交易-暂存] 日期: {trade_date} | 目标仓位: {target_volume} (等待target_pos初始化)"
            )
        else:
            try:
                self.logger.info(
                    f"[交易] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 目标仓位: {target_volume}"
                )
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
                    if direction is None:
                        direction = "BUY" if target_volume > 0 else "SELL"
                    offset = "OPEN"
                    order = self.api.insert_order(
                        symbol=self.current_trading_symbol,
                        direction=direction,
                        offset=offset,
                        volume=abs(target_volume),
                    )
                    self.logger.info(
                        f"[交易-insert] 日期: {trade_date} | 合约: {self.current_trading_symbol} | "
                        f"方向:{direction} | 手数:{abs(target_volume)}"
                    )
                    self._current_position = target_volume
                except Exception as e2:
                    self.logger.info(f"[交易-insert失败] {e2}")
                self._pending_signal = None

    def on_price_update(self, current_price: float):
        """
        价格更新时的回调函数

        检测价格穿越网格线，执行买入/卖出逻辑

        Args:
            current_price: 当前最新价格
        """
        if self.last_price is None:
            self.last_price = current_price
            self.logger.info(f"[网格策略] 初始化价格：{current_price}")
            return

        position = self.api.get_position(self.current_trading_symbol or self.symbol)
        total_long = position.volume_long

        if current_price >= self.grid_high:
            if total_long > 0:
                self._execute_trade(0)
                for line in self.grid_lines:
                    self.grid_has_position[line] = False
                self.current_target_volume = 0
                self.logger.info(
                    f"[网格策略] 价格突破上限{self.grid_high}，清空全部多仓{total_long}手"
                )
            self.last_price = current_price
            return

        if current_price <= self.grid_low:
            self.last_price = current_price
            return

        for grid_price in self.grid_lines:
            price_crossed_down = (self.last_price > grid_price) and (current_price <= grid_price)
            price_crossed_up = (self.last_price < grid_price) and (current_price >= grid_price)

            if price_crossed_down and not self.grid_has_position[grid_price]:
                if total_long < self.max_grid_position:
                    new_target = total_long + self.volume
                    self._execute_trade(new_target)
                    self.grid_has_position[grid_price] = True
                    total_long += self.volume
                    self.current_target_volume = new_target
                    self.logger.info(
                        f"[网格策略] 买入：网格线={grid_price}，"
                        f"当前价={current_price:.2f}，买入{self.volume}手，总持仓={total_long}"
                    )

            if price_crossed_up:
                grid_below = self._get_grid_below(grid_price)
                if grid_below is not None and self.grid_has_position.get(grid_below, False):
                    new_target = max(0, total_long - self.volume)
                    self._execute_trade(new_target)
                    self.grid_has_position[grid_below] = False
                    total_long -= self.volume
                    self.current_target_volume = new_target
                    profit_estimate = (grid_price - grid_below) * self.volume
                    self.logger.info(
                        f"[网格策略] 卖出：网格线={grid_price}，"
                        f"买入层={grid_below}，卖出{self.volume}手，"
                        f"预估利润≈{profit_estimate}点×合约乘数"
                    )

        self.last_price = current_price

    def run(self, max_iterations: int = None) -> None:
        """
        运行策略主循环

        Args:
            max_iterations: 最大迭代次数（用于回测），None 表示无限循环
        """
        iteration = 0

        while True:
            self.api.wait_update()

            if self.use_continuous and self.target_pos is None:
                if hasattr(self.quote, 'underlying_symbol') and self.quote.underlying_symbol:
                    self._switch_contract(self.quote.underlying_symbol)

            if self.use_continuous and self.api.is_changing(self.quote, "underlying_symbol"):
                new_symbol = self.quote.underlying_symbol
                if new_symbol:
                    self._switch_contract(new_symbol)

            if not self.api.is_changing(self.quote):
                continue

            current_price = self.quote.last_price
            if current_price != current_price or current_price <= 0:
                continue

            self.on_price_update(current_price)

            if self._pending_signal is not None and self.target_pos is not None and not self._use_insert_order:
                try:
                    self.target_pos.set_target_volume(self._pending_signal)
                    self._pending_signal = None
                except Exception:
                    pass

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
                try:
                    current_time = self.klines.datetime.iloc[-1]
                    from datetime import datetime
                    check_date = datetime.fromtimestamp(current_time / 1000000000).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                except Exception:
                    check_date = "N/A"
                snap = self._last_account_snapshot
                active_grids = [g for g, has_pos in self.grid_has_position.items() if has_pos]
                self.logger.info(
                    f"[账户检查] 日期: {check_date} | 账户权益: {snap['balance']:.2f} | "
                    f"可用资金: {snap['available']:.2f} | 持仓盈亏: {snap['position_profit']:.2f} | "
                    f"平仓盈亏: {snap['close_profit']:.2f} | 手续费: {snap['commission']:.2f} | "
                    f"持仓网格: {active_grids}"
                )

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
    symbol: str = "CZCE.MA509",
    grid_low: float = 2200,
    grid_high: float = 2600,
    grid_step: float = 40,
    volume: int = 1,
    max_grid_position: int = 10,
    use_continuous: bool = False,
    initial_balance: float = None,
    margin_ratio: float = None,
) -> GridTradingStrategy:
    """
    工厂函数：创建网格交易策略实例

    Args:
        api: TqApi 实例
        logger: 日志记录器
        symbol: 交易合约代码
        grid_low: 网格区间下限
        grid_high: 网格区间上限
        grid_step: 网格间距
        volume: 每格交易手数
        max_grid_position: 最大持仓手数
        use_continuous: 是否使用连续主力合约
        initial_balance: 初始资金
        margin_ratio: 保证金比例

    Returns:
        GridTradingStrategy: 网格交易策略实例
    """
    return GridTradingStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        grid_low=grid_low,
        grid_high=grid_high,
        grid_step=grid_step,
        volume=volume,
        max_grid_position=max_grid_position,
        use_continuous=use_continuous,
        initial_balance=initial_balance,
        margin_ratio=margin_ratio,
    )
