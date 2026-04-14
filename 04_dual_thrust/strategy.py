#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dual Thrust 日内突破策略 (Dual Thrust Intraday Breakout Strategy)
=================================================================

策略逻辑：
    - 经典日内突破策略，每日根据过去 N 日高低收价计算上下轨
    - Range = max(HH - LC, HC - LL)
        HH = N日最高价, LL = N日最低价
        HC = N日收盘价最高, LC = N日收盘价最低
    - 上轨 = 今日开盘价 + K1 × Range
    - 下轨 = 今日开盘价 - K2 × Range
    - 价格突破上轨做多，跌破下轨做空
    - 收盘前强制平仓

适用品种：
    波动性较强的品种，如铜（SHFE.cu）、黄金（SHFE.au）、原油（INE.sc）等

风险提示：
    - 日内策略在震荡行情中容易产生假突破信号
    - 建议结合成交量、波动率等过滤器使用
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from datetime import time
import math
from tqsdk import TqApi, TargetPosTask


class DualThrustStrategy:
    """
    Dual Thrust 日内突破策略类
    
    使用方式：
        strategy = DualThrustStrategy(api, logger, symbol="SHFE.cu2501", n_days=4, k1=0.5, k2=0.5)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    # 默认交易合约：上期所铜2605合约
    DEFAULT_SYMBOL = "SHFE.cu2605"
    # 默认回溯天数：4天
    DEFAULT_N_DAYS = 4
    # 默认上轨系数：0.5
    DEFAULT_K1 = 0.5
    # 默认下轨系数：0.5
    DEFAULT_K2 = 0.5
    # 默认持仓手数
    DEFAULT_VOLUME = 1
    # 默认平仓时间：14:50
    DEFAULT_CLOSE_HOUR = 14
    DEFAULT_CLOSE_MINUTE = 50
    # 默认K线周期：86400秒 = 日线
    DEFAULT_KLINE_DUR = 86400

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        n_days: int = None,
        k1: float = None,
        k2: float = None,
        volume: int = None,
        close_hour: int = None,
        close_minute: int = None,
        kline_dur: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        """
        初始化 Dual Thrust 策略

        Args:
            api: TqApi 实例，用于与期货交易系统交互
            logger: 日志记录器，用于记录策略运行信息
            symbol: 交易合约代码，格式为 "交易所.合约代码"，或连续合约如 "KQ.m@SHFE.cu"
            n_days: 回溯天数，用于计算 Range
            k1: 上轨系数
            k2: 下轨系数
            volume: 固定持仓手数（目标仓位的绝对值）。当使用动态仓位时此值作为保底参考
            close_hour: 日内强制平仓小时
            close_minute: 日内强制平分钟
            kline_dur: K线周期（秒），86400=日线
            use_continuous: 是否使用连续主力合约
            initial_balance: 初始资金（元），用于动态仓位计算
            margin_ratio: 保证金比例（0~1），每次开仓用总资产的该比例作为保证金
        """
        # 保存传入的参数
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL
        self.n_days = n_days if n_days is not None else self.DEFAULT_N_DAYS
        self.k1 = k1 if k1 is not None else self.DEFAULT_K1
        self.k2 = k2 if k2 is not None else self.DEFAULT_K2
        self.volume = volume if volume is not None else self.DEFAULT_VOLUME
        self.close_hour = close_hour if close_hour is not None else self.DEFAULT_CLOSE_HOUR
        self.close_minute = close_minute if close_minute is not None else self.DEFAULT_CLOSE_MINUTE
        self.kline_dur = kline_dur if kline_dur is not None else self.DEFAULT_KLINE_DUR
        self.use_continuous = use_continuous
        # 动态仓位参数
        self.initial_balance = initial_balance
        self.margin_ratio = margin_ratio

        # 获取日线数据，用于计算 Range
        self.daily_klines = api.get_kline_serial(
            self.symbol, self.kline_dur, data_length=self.n_days + 10
        )

        # 获取分钟K线数据，用于日内突破判断
        self.klines = api.get_kline_serial(
            self.symbol, 60, data_length=100
        )

        # 处理连续合约和普通合约的不同初始化逻辑
        if self.use_continuous:
            self.quote = api.get_quote(self.symbol)
            self.current_trading_symbol = None
            self.target_pos = None
        else:
            self.current_trading_symbol = self.symbol
            self.target_pos = TargetPosTask(api, self.symbol)
            self._adapt_volume_to_min(self.symbol)

        # 获取实时报价
        if not self.use_continuous:
            self.quote = api.get_quote(self.symbol)

        # 初始化策略状态变量
        self.today_date = None
        self.today_open = None
        self.buy_line = None
        self.sell_line = None
        self.last_signal = None
        self.current_target_volume = 0
        self._last_account_snapshot = None
        self._initial_balance = None
        self._pending_signal = None
        
        # 已知 TargetPosTask 不支持的品种列表（TqSim回测模式）
        self._use_insert_order = False
        self._current_position = 0
        self._UNSUPPORTED_TARGETPOS_PREFIXES = {
            'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
            'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
        }

        # 记录策略初始化信息
        self.logger.info(
            f"[策略初始化] Dual Thrust 策略 | 合约: {self.symbol} | "
            f"N={self.n_days} | K1={self.k1} | K2={self.k2} | "
            f"平仓时间: {self.close_hour}:{self.close_minute:02d} | "
            f"连续合约: {self.use_continuous} | "
            f"初始资金: {self.initial_balance} | 保证金比例: {self.margin_ratio}"
        )

    # 各品种的合约乘数（手数单位）
    CONTRACT_MULTIPLIER_MAP = {
        # 大商所
        'DCE.l': 5,   'DCE.v': 5,   'DCE.pp': 5,
        'DCE.eg': 10, 'DCE.i': 100,  'DCE.j': 100,
        'DCE.a': 10,  'DCE.b': 10,   'DCE.c': 10,
        'DCE.m': 10,  'DCE.p': 10,   'DCE.y': 10,
        'DCE.eb': 5,  'DCE.jd': 10,  'DCE.lh': 16,
        'DCE.cs': 10, 'DCE.pg': 10,  'DCE.rr': 10,
        # 郑商所
        'CZCE.TA': 5,'CZCE.MA': 10,'CZCE.SR': 10,
        'CZCE.CF': 5,'CZCE.OI': 10,'CZCE.FG': 20,
        'CZCE.RM': 10,'CZCE.SF': 5,'CZCE.UR': 20,
        'CZCE.SM': 5,'CZCE.CJ': 5,'CZCE.PK': 5,
        'CZCE.SA': 20,'CZCE.AP': 10,'CZCE.PF': 5,
        # 上期所
        'SHFE.rb': 10,'SHFE.au': 1000,'SHFE.cu': 5,
        'SHFE.al': 5,'SHFE.zn': 5,'SHFE.ni': 1,
        'SHFE.sn': 1,'SHFE.ss': 10,'SHFE.ag': 15,
        'SHFE.bu': 10,'SHFE.ru': 10,'SHFE.hc': 10,
        'SHFE.sp': 10,'SHFE.fu': 10,'SHFE.wr': 10,
        # 能源中心
        'INE.sc': 1000,'INE.lu': 10,
        # 中金所
        'CFFEX.IF': 300,'CFFEX.IC': 200,'CFFEX.IH': 300,
        'CFFEX.IM': 200,'CFFEX.T': 10000,'CFFEX.TF': 10000,'CFFEX.TS': 20000,
    }

    # 各品种的交易所保证金率（比例，如 0.12 表示12%）
    MARGIN_RATE_MAP = {
        # 大商所
        'DCE.l': 0.12,  'DCE.v': 0.12,  'DCE.pp': 0.12,
        'DCE.eg': 0.12, 'DCE.i': 0.15,  'DCE.j': 0.15,
        'DCE.a': 0.12,  'DCE.b': 0.12,  'DCE.c': 0.12,
        'DCE.m': 0.12,  'DCE.p': 0.12,  'DCE.y': 0.12,
        'DCE.eb': 0.12, 'DCE.jd': 0.12, 'DCE.lh': 0.12,
        'DCE.cs': 0.12, 'DCE.pg': 0.12, 'DCE.rr': 0.12,
        # 郑商所
        'CZCE.TA': 0.12,'CZCE.MA': 0.12,'CZCE.SR': 0.10,
        'CZCE.CF': 0.12,'CZCE.OI': 0.12,'CZCE.FG': 0.12,
        'CZCE.RM': 0.12,'CZCE.SF': 0.12,'CZCE.UR': 0.12,
        'CZCE.SM': 0.12,'CZCE.CJ': 0.15,'CZCE.PK': 0.15,
        'CZCE.SA': 0.15,'CZCE.AP': 0.12,'CZCE.PF': 0.12,
        # 上期所
        'SHFE.rb': 0.13,'SHFE.au': 0.12,'SHFE.cu': 0.12,
        'SHFE.al': 0.11,'SHFE.zn': 0.12,'SHFE.ni': 0.16,
        'SHFE.sn': 0.14,'SHFE.ss': 0.12,'SHFE.ag': 0.12,
        'SHFE.bu': 0.12,'SHFE.ru': 0.13,'SHFE.hc': 0.14,
        'SHFE.sp': 0.12,'SHFE.fu': 0.12,'SHFE.wr': 0.12,
        # 能源中心
        'INE.sc': 0.15,'INE.lu': 0.12,
        # 中金所
        'CFFEX.IF': 0.14,'CFFEX.IC': 0.14,'CFFEX.IH': 0.14,
        'CFFEX.IM': 0.14,'CFFEX.T': 0.02,'CFFEX.TF': 0.03,'CFFEX.TS': 0.02,
    }

    # 各品种的最小下单量
    MIN_VOLUME_MAP = {
        # 大商所
        'DCE.l': 8,   'DCE.v': 8,   'DCE.pp': 8,
        'DCE.eg': 8,  'DCE.i': 1,   'DCE.j': 1,
        'DCE.a': 1,   'DCE.b': 1,   'DCE.c': 1,
        'DCE.m': 1,   'DCE.p': 1,   'DCE.y': 1,
        'DCE.eb': 1,  'DCE.jd': 1,  'DCE.lh': 1,
        'DCE.cs': 1,  'DCE.pg': 1,  'DCE.rr': 1,
        # 郑商所
        'CZCE.TA': 8,'CZCE.MA': 8,'CZCE.SR': 1,
        'CZCE.CF': 1,'CZCE.OI': 1,'CZCE.FG': 1,
        'CZCE.RM': 1,'CZCE.SF': 1,'CZCE.UR': 1,
        'CZCE.SM': 1,'CZCE.CJ': 1,'CZCE.PK': 1,
        'CZCE.SA': 1,'CZCE.AP': 2,'CZCE.PF': 1,
        # 上期所
        'SHFE.rb': 1,'SHFE.au': 1,'SHFE.cu': 1,
        'SHFE.al': 1,'SHFE.zn': 1,'SHFE.ni': 1,
        'SHFE.sn': 1,'SHFE.ss': 1,'SHFE.ag': 1,
        'SHFE.bu': 1,'SHFE.ru': 1,'SHFE.hc': 1,
        'SHFE.sp': 1,'SHFE.fu': 1,'SHFE.wr': 1,
        # 能源中心
        'INE.sc': 1,'INE.lu': 1,
        # 中金所
        'CFFEX.IF': 1,'CFFEX.IC': 1,'CFFEX.IH': 1,
        'CFFEX.IM': 1,'CFFEX.T': 1,'CFFEX.TF': 1,'CFFEX.TS': 1,
    }

    def _get_symbol_prefix(self, trading_symbol: str):
        """从交易合约代码提取品种前缀，如 DCE.l2605 -> DCE.l"""
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
        """获取品种的最小下单量"""
        prefix = self._get_symbol_prefix(trading_symbol)
        if prefix and prefix in self.MIN_VOLUME_MAP:
            return self.MIN_VOLUME_MAP[prefix]
        return 1

    def _calc_dynamic_volume(self) -> int:
        """
        根据当前总资产和保证金比例动态计算开仓手数
        
        计算公式：
            可用保证金 = 当前账户权益 × margin_ratio
            每手保证金 ≈ 最新价 × 合约乘数 × 交易所保证金率
            开仓手数 = floor(可用保证金 / 每手保证金)
        
        Returns:
            int: 应开仓的手数（已确保不低于最小下单量）
        """
        if self.initial_balance is None or self.margin_ratio is None:
            return self.volume
        
        try:
            account = self.api.get_account()
            current_balance = account.balance
            
            # 使用K线数据获取价格
            current_price = self.klines.close.iloc[-1]
            if current_price <= 0:
                # 回退到quote数据
                if hasattr(self, 'quote') and self.quote.last_price:
                    current_price = self.quote.last_price
                else:
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
        """
        切换交易合约
        
        Args:
            new_symbol: 新的交易合约代码
        """
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
        """检查并适配合约的最小下单量"""
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

    def calculate_range(self) -> bool:
        """
        计算当日的上下轨
        
        Returns:
            bool: 是否成功计算（True=新交易日已计算，False=非新交易日）
        """
        # 获取当前日期
        if hasattr(self, 'quote') and self.quote.datetime:
            current_date = self.quote.datetime[:10]
        else:
            # 从K线数据获取日期
            if len(self.klines) > 0:
                kline_time = self.klines.datetime.iloc[-1]
                from datetime import datetime
                kline_dt = datetime.fromtimestamp(kline_time / 1000000000)
                current_date = kline_dt.strftime('%Y-%m-%d')
            else:
                return False
        
        if current_date is None or current_date == self.today_date:
            return False
        
        self.today_date = current_date
        
        # 获取今日开盘价
        # 优先使用分钟K线的当日开盘价
        if len(self.klines) > 0:
            # 过滤出今日的K线数据
            from datetime import datetime
            today_str = self.today_date
            today_klines = []
            for i in range(len(self.klines)):
                try:
                    kline_time = self.klines.datetime.iloc[i]
                    kline_dt = datetime.fromtimestamp(kline_time / 1000000000)
                    kline_date = kline_dt.strftime('%Y-%m-%d')
                    if kline_date == today_str:
                        today_klines.append(self.klines.open.iloc[i])
                except:
                    continue
            
            if today_klines:
                self.today_open = today_klines[0]  # 使用当日第一根K线的开盘价
            elif len(self.daily_klines) > 0:
                # 从日线数据获取开盘价
                self.today_open = self.daily_klines.open.iloc[-1]
            elif hasattr(self, 'quote') and hasattr(self.quote, 'open') and self.quote.open is not None and (not isinstance(self.quote.open, float) or (isinstance(self.quote.open, float) and not math.isnan(self.quote.open))):
                # 回退到quote数据
                self.today_open = self.quote.open
            else:
                self.logger.warning("[计算Range] 无法获取开盘价，使用前一天收盘价")
                if len(self.daily_klines) > 1:
                    self.today_open = self.daily_klines.close.iloc[-2]
                else:
                    self.logger.error("[计算Range] 没有足够数据获取开盘价")
                    return False
        
        # 确保有足够的历史数据
        if len(self.daily_klines) < self.n_days + 1:
            self.logger.warning(f"[计算Range] 历史数据不足，需要 {self.n_days + 1} 根K线，当前只有 {len(self.daily_klines)} 根")
            return False
        
        hist_high = self.daily_klines.high.iloc[-(self.n_days + 1):-1]
        hist_low = self.daily_klines.low.iloc[-(self.n_days + 1):-1]
        hist_close = self.daily_klines.close.iloc[-(self.n_days + 1):-1]
        
        hh = hist_high.max()
        ll = hist_low.min()
        lc = hist_close.min()
        hc = hist_close.max()
        
        price_range = max(hh - lc, hc - ll)
        
        self.buy_line = self.today_open + self.k1 * price_range
        self.sell_line = self.today_open - self.k2 * price_range
        
        self.logger.info(
            f"[{self.today_date}] 开盘:{self.today_open} | "
            f"上轨:{self.buy_line:.2f} | 下轨:{self.sell_line:.2f} | "
            f"Range:{price_range:.2f}"
        )
        
        return True

    def on_tick_update(self) -> int:
        """
        Tick 更新时的回调函数
        
        判断价格是否突破上下轨，并返回相应的目标仓位

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        if self.buy_line is None or self.sell_line is None:
            return 0
        
        # 使用K线数据进行突破判断
        last_price = self.klines.close.iloc[-1]
        if last_price is None or last_price <= 0:
            # 回退到quote数据
            if hasattr(self, 'quote') and self.quote.last_price:
                last_price = self.quote.last_price
            else:
                return 0
        
        # 获取时间
        if hasattr(self, 'quote') and self.quote.datetime:
            # 从quote获取时间
            t_str = self.quote.datetime[11:19] if len(self.quote.datetime) > 19 else "00:00:00"
            try:
                t = time(*[int(x) for x in t_str.split(":")])
            except:
                t = time(0, 0, 0)
        else:
            # 使用K线时间
            kline_time = self.klines.datetime.iloc[-1]
            from datetime import datetime
            try:
                kline_dt = datetime.fromtimestamp(kline_time / 1000000000)
                t = time(kline_dt.hour, kline_dt.minute, kline_dt.second)
            except:
                t = time(0, 0, 0)
        
        # 收盘前强制平仓
        # 处理夜盘和日盘的不同收盘时间
        hour = t.hour
        if hour >= 21 and hour < 24:
            # 夜盘时间 (21:00-23:59)，不收盘
            pass
        elif hour >= 0 and hour < 1:
            # 夜盘时间 (00:00-00:59)，不收盘
            pass
        elif hour >= 1 and hour < 9:
            # 夜盘收盘时间 (01:00-08:59)，强制平仓
            self.logger.info(f"[收盘平仓] 夜盘收盘时间:{t} >= 01:00")
            return 0
        else:
            # 日盘时间，收盘时间为14:50
            if t >= time(self.close_hour, self.close_minute):
                self.logger.info(f"[收盘平仓] 日盘时间:{t} >= {self.close_hour}:{self.close_minute:02d}")
                return 0
        
        # 获取K线的最高价和最低价
        high_price = self.klines.high.iloc[-1]
        low_price = self.klines.low.iloc[-1]
        
        # 突破上轨 → 做多
        if high_price > self.buy_line:
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(f">>> 突破上轨！最高价:{high_price} > 上轨:{self.buy_line:.2f} | 目标仓位: +{dynamic_vol}")
            self.last_signal = "buy"
            return dynamic_vol
        
        # 跌破下轨 → 做空
        elif low_price < self.sell_line:
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(f">>> 跌破下轨！最低价:{low_price} < 下轨:{self.sell_line:.2f} | 目标仓位: -{dynamic_vol}")
            self.last_signal = "sell"
            return -dynamic_vol
        
        return 0

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

            # 处理连续合约的初始化和切换
            if self.use_continuous and self.target_pos is None:
                if hasattr(self.quote, 'underlying_symbol') and self.quote.underlying_symbol:
                    self._switch_contract(self.quote.underlying_symbol)

            if self.use_continuous and self.api.is_changing(self.quote, "underlying_symbol"):
                new_symbol = self.quote.underlying_symbol
                if new_symbol:
                    self._switch_contract(new_symbol)

            # 检查K线是否更新
            if not self.api.is_changing(self.klines):
                continue

            # 获取当前K线ID，防止同一K线重复处理
            current_kline_id = self.klines.id.iloc[-1]
            if current_kline_id == last_kline_id:
                continue
            last_kline_id = current_kline_id

            if not self.quote.datetime:
                continue

            # 计算当日上下轨（新交易日时）
            self.calculate_range()

            if self.buy_line is None:
                continue

            # 计算交易信号并获取目标仓位
            target_volume = self.on_tick_update()

            # 如果有交易信号
            if target_volume != 0:
                self.current_target_volume = target_volume
                
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
                        self.logger.info(f"[交易-insert] 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{abs(target_volume)}")
                        self._current_position = target_volume
                        self._pending_signal = None
                    except Exception as e:
                        self.logger.info(f"[交易-失败] {e}")
                        
                elif self.target_pos is None:
                    self._pending_signal = target_volume
                    self.logger.info(f"[交易-暂存] 目标仓位: {target_volume} (等待target_pos初始化)")
                elif self.target_pos is not None:
                    try:
                        self.logger.info(f"[交易] 合约: {self.current_trading_symbol} | 目标仓位: {target_volume}")
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
                            self.logger.info(f"[交易-insert] 合约: {self.current_trading_symbol} | 方向:{direction} | 手数:{abs(target_volume)}")
                            self._current_position = target_volume
                        except Exception as e2:
                            self.logger.info(f"[交易-insert失败] {e2}")
                    self._pending_signal = None

            # 检查是否有待执行的暂存信号
            if self._pending_signal is not None and self.target_pos is not None and not self._use_insert_order:
                self.logger.info(f"[交易-执行暂存] 合约: {self.current_trading_symbol} | 目标仓位: {self._pending_signal}")
                self.target_pos.set_target_volume(self._pending_signal)
                self._pending_signal = None

            # 保存账户快照
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

            # 定期打印账户信息
            if iteration % 10 == 0 and self._last_account_snapshot:
                snap = self._last_account_snapshot
                self.logger.info(
                    f"[账户检查] 账户权益: {snap['balance']:.2f} | "
                    f"可用资金: {snap['available']:.2f} | "
                    f"持仓盈亏: {snap['position_profit']:.2f} | "
                    f"平仓盈亏: {snap['close_profit']:.2f} | "
                    f"手续费: {snap['commission']:.2f}"
                )

            iteration += 1
            if max_iterations is not None and iteration >= max_iterations:
                self.logger.info(f"[策略结束] 达到最大迭代次数: {max_iterations}")
                break

    def get_current_position(self) -> int:
        """获取当前目标仓位任务"""
        return self.target_pos

    def get_account_snapshot(self) -> dict:
        """获取最后一次保存的账户快照"""
        return self._last_account_snapshot

    def set_target_volume(self, volume: int) -> None:
        """手动设置目标仓位"""
        self.target_pos.set_target_volume(volume)


def create_strategy(
    api: TqApi,
    logger,
    symbol: str = "SHFE.cu2501",
    n_days: int = 4,
    k1: float = 0.5,
    k2: float = 0.5,
    volume: int = 1,
) -> DualThrustStrategy:
    """
    创建 Dual Thrust 策略实例的工厂函数

    Args:
        api: TqApi 实例
        logger: 日志记录器
        symbol: 交易合约代码
        n_days: 回溯天数
        k1: 上轨系数
        k2: 下轨系数
        volume: 持仓手数

    Returns:
        DualThrustStrategy: 策略实例
    """
    return DualThrustStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        n_days=n_days,
        k1=k1,
        k2=k2,
        volume=volume,
    )
