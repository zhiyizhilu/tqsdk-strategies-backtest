#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双均线趋势跟踪策略 (Double Moving Average Strategy)
====================================================

策略逻辑：
    - 使用短期均线（MA5）和长期均线（MA20）的交叉信号判断趋势方向
    - 金叉（短均线从下方向上穿越长均线）：目标仓位设为 +VOLUME（做多）
    - 死叉（短均线从上方向下穿越长均线）：目标仓位设为 -VOLUME（做空）
    - 使用 TargetPosTask 管理持仓，无需手动处理追单、撤单、部分成交等细节

适用品种：
    趋势性较强的品种，如螺纹钢（SHFE.rb）、原油（INE.sc）、铜（SHFE.cu）等

风险提示：
    - 均线策略在震荡行情中容易产生频繁的假信号（亏损）
    - 建议结合成交量、波动率等过滤器使用
    - 本代码仅供学习参考，不构成任何投资建议

依赖：
    pip install tqsdk -U

作者：tqsdk-strategies
文档：https://doc.shinnytech.com/tqsdk/latest/
"""

from tqsdk import TqApi, TargetPosTask
from tqsdk.tafunc import ma, crossup, crossdown


class DoubleMAStrategy:
    """
    双均线策略类
    
    使用方式：
        strategy = DoubleMAStrategy(api, logger, symbol="SHFE.rb2501", short_period=5, long_period=20)
        strategy.run()  # 阻塞运行，直到策略结束
    """

    # 默认交易合约：上期所螺纹钢2605合约
    DEFAULT_SYMBOL = "SHFE.rb2605"
    # 默认短期均线周期：5根K线
    DEFAULT_SHORT_PERIOD = 5
    # 默认长期均线周期：20根K线
    DEFAULT_LONG_PERIOD = 20
    # 默认K线周期：3600秒 = 1小时K线
    DEFAULT_KLINE_DUR = 60 * 60
    # 默认持仓手数（正数=多头，负数=空头，0=空仓）
    DEFAULT_VOLUME = 1

    def __init__(
        self,
        api: TqApi,
        logger,
        symbol: str = None,
        short_period: int = None,
        long_period: int = None,
        kline_dur: int = None,
        volume: int = None,
        use_continuous: bool = False,
        initial_balance: float = None,
        margin_ratio: float = None,
    ):
        """
        初始化双均线策略

        Args:
            api: TqApi 实例，用于与期货交易系统交互
            logger: 日志记录器，用于记录策略运行信息
            symbol: 交易合约代码，格式为 "交易所.合约代码"，或连续合约如 "KQ.m@SHFE.rb"
            short_period: 短期均线周期（K线根数）
            long_period: 长期均线周期（K线根数）
            kline_dur: K线周期（秒），60=1分钟K线，3600=1小时K线
            volume: 固定持仓手数（目标仓位的绝对值）。当使用动态仓位时此值作为保底参考
            use_continuous: 是否使用连续主力合约
            initial_balance: 初始资金（元），用于动态仓位计算
            margin_ratio: 保证金比例（0~1），每次开仓用总资产的该比例作为保证金
        """
        # 保存传入的参数
        self.api = api
        self.logger = logger
        self.symbol = symbol or self.DEFAULT_SYMBOL  # 使用默认合约如果未指定
        self.short_period = short_period or self.DEFAULT_SHORT_PERIOD  # 使用默认短周期如果未指定
        self.long_period = long_period or self.DEFAULT_LONG_PERIOD  # 使用默认长周期如果未指定
        self.kline_dur = kline_dur or self.DEFAULT_KLINE_DUR  # 使用默认K线周期如果未指定
        self.volume = volume or self.DEFAULT_VOLUME  # 使用默认持仓手数如果未指定
        self.use_continuous = use_continuous  # 是否使用连续主力合约
        # 动态仓位参数
        self.initial_balance = initial_balance  # 初始资金，None 表示使用固定 volume
        self.margin_ratio = margin_ratio  # 保证金比例，None 表示不使用动态仓位

        # 获取K线数据，数据长度为长期均线周期+10，确保有足够的数据计算均线
        self.klines = api.get_kline_serial(
            self.symbol, self.kline_dur, data_length=self.long_period + 10
        )

        # 处理连续合约和普通合约的不同初始化逻辑
        if self.use_continuous:
            # 连续合约需要获取报价数据以跟踪底层合约变化
            self.quote = api.get_quote(self.symbol)
            self.current_trading_symbol = None  # 初始时未确定交易合约
            self.target_pos = None  # 初始时未创建目标仓位任务
        else:
            # 普通合约直接使用指定的合约
            self.current_trading_symbol = self.symbol
            # 创建目标仓位任务，用于管理持仓
            self.target_pos = TargetPosTask(api, self.symbol)
            # 检查并适配最小下单量
            self._adapt_volume_to_min(self.symbol)

        # 初始化策略状态变量
        self.last_signal = None  # 上次交易信号
        self.current_target_volume = 0  # 当前目标仓位
        self._last_account_snapshot = None  # 最后一次账户快照
        self._initial_balance = None  # 初始账户余额
        self._pending_signal = None  # 待执行的信号（target_pos未就绪时暂存）
        
        # 已知 TargetPosTask 不支持的品种列表（TqSim回测模式）
        # 这些品种需要用 insert_order 直接下单
        self._use_insert_order = False
        self._current_position = 0  # 手动跟踪持仓（insert_order模式下）
        self._UNSUPPORTED_TARGETPOS_PREFIXES = {
            'DCE.l', 'DCE.v', 'DCE.pp', 'DCE.eg',
            'CZCE.TA', 'CZCE.MA', 'CZCE.AP',
        }

        # 记录策略初始化信息
        self.logger.info(
            f"[策略初始化] 双均线策略 | 合约: {self.symbol} | "
            f"短周期: {self.short_period} | 长周期: {self.long_period} | "
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

    # 各品种的交易所保证金率（比例，如 0.12 表示12%）— 用于估算开仓所需保证金
    MARGIN_RATE_MAP = {
        # 大商所（一般商品期货约8%-15%）
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
        # 中金所（股指/国债保证金较高）
        'CFFEX.IF': 0.14,'CFFEX.IC': 0.14,'CFFEX.IH': 0.14,
        'CFFEX.IM': 0.14,'CFFEX.T': 0.02,'CFFEX.TF': 0.03,'CFFEX.TS': 0.02,
    }

    # 各品种的最小下单量（TqSim/TqBacktest 环境下）
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
        
        如果计算出的手数 < 最小下单量，则使用最小下单量
        
        Returns:
            int: 应开仓的手数（已确保不低于最小下单量）
        """
        # 如果没有启用动态仓位，返回固定 volume
        if self.initial_balance is None or self.margin_ratio is None:
            return self.volume
        
        try:
            # 获取当前账户权益
            account = self.api.get_account()
            current_balance = account.balance  # 总资产（权益）
            
            # 获取当前最新价
            current_price = self.klines.close.iloc[-1]
            if current_price <= 0:
                self.logger.warning(f"[动态仓位] 价格异常 {current_price}，使用固定volume")
                return self.volume
            
            # 获取交易合约
            trading_symbol = self.current_trading_symbol or self.symbol
            
            # 获取品种前缀和相关参数
            prefix = self._get_symbol_prefix(trading_symbol)
            
            # 合约乘数
            multiplier = self.CONTRACT_MULTIPLIER_MAP.get(prefix, 10)
            
            # 保证金率
            margin_rate = self.MARGIN_RATE_MAP.get(prefix, 0.12)
            
            # 最小下单量
            min_vol = self._get_min_volume(trading_symbol)
            
            # 计算可用保证金
            available_margin = current_balance * self.margin_ratio
            
            # 每手需要的保证金 = 价格 × 乘数 × 保证金率
            margin_per_lot = current_price * multiplier * margin_rate
            
            if margin_per_lot <= 0:
                self.logger.warning(f"[动态仓位] 每手保证金异常 {margin_per_lot}，使用固定volume")
                return self.volume
            
            # 计算可开仓手数（向下取整）
            calc_volume = int(available_margin / margin_per_lot)
            
            # 确保不低于最小下单量
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
        
        当使用连续合约时，当底层合约发生变化时调用此方法切换交易合约
        
        Args:
            new_symbol: 新的交易合约代码
        """
        # 如果新合约与当前合约相同，则无需切换
        if new_symbol == self.current_trading_symbol:
            return

        # 记录合约切换信息
        self.logger.info(f"[换月] 从 {self.current_trading_symbol} 切换到 {new_symbol}")
        
        # 先平掉旧合约的仓位
        if self.target_pos and self.current_trading_symbol:
            try:
                self.target_pos.set_target_volume(0)  # 平仓
                self.api.wait_update()  # 等待平仓完成
                self.logger.info(f"[换月] 已平掉旧合约 {self.current_trading_symbol} 的仓位")
            except Exception as e:
                self.logger.warning(f"[换月] 平仓旧合约时异常: {e}")
        
        # 必须先取消旧的 TargetPosTask，否则旧任务的挂单会阻塞回测退出
        if self.target_pos:
            try:
                self.target_pos.cancel()  # 取消旧的目标仓位任务
            except Exception as e:
                # 捕获异常并记录，防止切换过程因异常而中断
                self.logger.info(f"[换月] cancel 旧 TargetPosTask 时异常（可忽略）: {e}")
        
        # 更新当前交易合约
        self.current_trading_symbol = new_symbol
        
        # 检查是否在 TargetPosTask 不支持列表中
        import re
        parts = new_symbol.split('.')
        prefix = None
        if len(parts) >= 2:
            match = re.match(r'([a-zA-Z]+)', parts[1])
            if match:
                prefix = f"{parts[0]}.{match.group(1)}"
        
        if prefix in self._UNSUPPORTED_TARGETPOS_PREFIXES:
            # 不支持 TargetPosTask 的品种，直接用 insert_order
            self._use_insert_order = True
            if self.target_pos:
                try: self.target_pos.cancel()
                except Exception: pass
            self.target_pos = None
            self._current_position = 0
            self.logger.info(f"[换月] {new_symbol} 不支持TargetPosTask，使用insert_order模式")
        else:
            # 正常创建 TargetPosTask
            self._use_insert_order = False
            try:
                self.target_pos = TargetPosTask(self.api, new_symbol)
                self.logger.info(f"[换月] TargetPosTask 创建成功: {new_symbol}")
            except Exception as e:
                # 如果仍然失败，回退到 insert_order
                self._use_insert_order = True
                self.target_pos = None
                self._current_position = 0
                self.logger.info(f"[换月] TargetPosTask 创建失败 {new_symbol}: {e}，切换为 insert_order")
        
        # 检查并适配新合约的最小下单量
        self._adapt_volume_to_min(new_symbol)
        
        # 如果当前有目标仓位，则在新合约上设置相同的仓位
        if self.current_target_volume != 0:
            self.target_pos.set_target_volume(self.current_target_volume)
            self.logger.info(f"[换月] 在新合约 {new_symbol} 上设置仓位: {self.current_target_volume}")

    def _adapt_volume_to_min(self, trading_symbol: str):
        """检查并适配合约的最小下单量，确保 volume 满足交易所要求"""
        # 从交易合约代码中提取品种前缀（如 DCE.l2605 -> DCE.l）
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
        
        计算短期和长期均线，判断是否出现金叉或死叉信号，并返回相应的目标仓位

        Returns:
            int: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        # 计算短期均线（MA5）
        ma_short = ma(self.klines.close, self.short_period)
        # 计算长期均线（MA20）
        ma_long = ma(self.klines.close, self.long_period)

        # 判断是否出现金叉（短均线上穿长均线）
        is_golden_cross = crossup(ma_short, ma_long).iloc[-1]
        # 判断是否出现死叉（短均线下穿长均线）
        is_death_cross = crossdown(ma_short, ma_long).iloc[-1]
        
        # 以下代码用于调试，可根据需要取消注释
        """
        self.logger.info(
            f"最新价: {self.klines.close.iloc[-1]:.2f} | "
            f"MA{self.short_period}: {ma_short.iloc[-1]:.2f} | "
            f"MA{self.long_period}: {ma_long.iloc[-1]:.2f}"
        )
        """

        # 初始化目标仓位为0（空仓）
        target_volume = 0

        # 处理金叉信号：做多
        if is_golden_cross:
            # 使用动态计算的手数（基于总资产×保证金比例）
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(f">>> 金叉！目标仓位: +{dynamic_vol}（做多）")
            target_volume = dynamic_vol  # 设置为多头仓位
            self.last_signal = "golden"  # 记录上次信号为金叉

        # 处理死叉信号：做空
        elif is_death_cross:
            # 使用动态计算的手数（基于总资产×保证金比例）
            dynamic_vol = self._calc_dynamic_volume()
            self.logger.info(f">>> 死叉！目标仓位: -{dynamic_vol}（做空）")
            target_volume = -dynamic_vol  # 设置为空头仓位
            self.last_signal = "death"  # 记录上次信号为死叉

        # 返回目标仓位
        return target_volume

    def run(self, max_iterations: int = None) -> None:
        """
        运行策略主循环
        
        策略的核心运行逻辑，包含以下步骤：
        1. 等待数据更新
        2. 处理连续合约的初始化和切换
        3. 处理K线更新，避免重复处理
        4. 计算交易信号并执行交易
        5. 保存账户快照
        6. 定期打印账户信息
        7. 处理最大迭代次数限制

        Args:
            max_iterations: 最大迭代次数（用于回测），None 表示无限循环
        """
        # 初始化迭代计数器
        iteration = 0
        # 记录上一次处理的K线ID，防止重复处理同一根K线
        last_kline_id = None

        # 策略主循环
        while True:
            # 等待数据更新
            self.api.wait_update()

            # 检查是否需要初始化 target_pos（当使用连续合约时）
            if self.use_continuous and self.target_pos is None:
                if hasattr(self.quote, 'underlying_symbol') and self.quote.underlying_symbol:
                    # 初始化连续合约的目标仓位任务
                    self._switch_contract(self.quote.underlying_symbol)

            # 检查连续合约的底层合约是否发生变化
            if self.use_continuous and self.api.is_changing(self.quote, "underlying_symbol"):
                new_symbol = self.quote.underlying_symbol
                if new_symbol:
                    # 切换到新的底层合约
                    self._switch_contract(new_symbol)

            # 检查K线是否更新
            if not self.api.is_changing(self.klines):
                continue

            # 获取当前K线ID，防止同一K线重复处理
            current_kline_id = self.klines.id.iloc[-1]
            if current_kline_id == last_kline_id:
                continue
            last_kline_id = current_kline_id

            # 计算交易信号并获取目标仓位
            target_volume = self.on_kline_update()

            # 如果有交易信号，记录到 pending（即使 target_pos 还没就绪也不丢失）
            if target_volume != 0:
                self.current_target_volume = target_volume
                current_time_t = self.klines.datetime.iloc[-1]
                from datetime import datetime
                trade_date = datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")
                
                if self._use_insert_order:
                    # insert_order 模式：直接下单
                    try:
                        direction = "BUY" if target_volume > 0 else "SELL"
                        offset = "OPEN"  # 简化处理：始终开仓
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
                    # target_pos 尚未初始化，暂存信号
                    self._pending_signal = target_volume
                    self.logger.info(f"[交易-暂存] 日期: {trade_date} | 目标仓位: {target_volume} (等待target_pos初始化)")
                elif self.target_pos is not None:
                    # TargetPosTask 模式：尝试正常执行，如果失败则切换到 insert_order
                    try:
                        self.logger.info(f"[交易] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 目标仓位: {target_volume}")
                        self.target_pos.set_target_volume(target_volume)
                        self._pending_signal = None
                    except Exception as tp_err:
                        # TargetPosTask 执行失败（可能是不支持该合约或最小下单量限制）
                        # 切换为 insert_order 模式作为回退
                        self._use_insert_order = True
                        self.logger.info(f"[交易] TargetPosTask 执行失败，切换为 insert_order 模式")
                        
                        # 取消旧的 target_pos
                        try:
                            self.target_pos.cancel()
                        except Exception:
                            pass
                        self.target_pos = None
                        
                        # 用 insert_order 执行
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

            # 检查是否有待执行的暂存信号（在 target_pos 刚被创建后）
            if self._pending_signal is not None and self.target_pos is not None and not self._use_insert_order:
                current_time_t = self.klines.datetime.iloc[-1]
                from datetime import datetime
                trade_date = datetime.fromtimestamp(current_time_t / 1000000000).strftime("%Y-%m-%d %H:%M:%S")
                self.logger.info(f"[交易-执行暂存] 日期: {trade_date} | 合约: {self.current_trading_symbol} | 目标仓位: {self._pending_signal}")
                self.target_pos.set_target_volume(self._pending_signal)
                self._pending_signal = None

            # 每次迭代都保存账户快照
            try:
                account = self.api.get_account()
                if account:
                    # 记录初始账户余额
                    if self._initial_balance is None:
                        self._initial_balance = account.static_balance
                    # 保存账户快照
                    self._last_account_snapshot = {
                        "static_balance": self._initial_balance,  # 初始账户余额
                        "balance": account.balance,  # 当前账户权益
                        "available": account.available,  # 可用资金
                        "float_profit": account.float_profit,  # 浮动盈亏
                        "position_profit": account.position_profit,  # 持仓盈亏
                        "close_profit": account.close_profit,  # 平仓盈亏
                        "margin": account.margin,  # 保证金
                        "commission": account.commission,  # 手续费
                    }
            except Exception:
                # 捕获异常并忽略，防止因账户数据获取失败而中断策略
                pass

            # 定期打印账户信息（每10次迭代）
            if iteration % 10 == 0 and self._last_account_snapshot:
                # 获取当前K线的时间
                current_time = self.klines.datetime.iloc[-1]
                # 转换numpy时间戳为datetime对象
                from datetime import datetime
                check_date = datetime.fromtimestamp(current_time / 1000000000).strftime("%Y-%m-%d %H:%M:%S")
                # 获取账户快照
                snap = self._last_account_snapshot
                # 记录账户信息
                self.logger.info(f"[账户检查] 日期: {check_date} | 账户权益: {snap['balance']:.2f} | 可用资金: {snap['available']:.2f} | 持仓盈亏: {snap['position_profit']:.2f} | 平仓盈亏: {snap['close_profit']:.2f} | 手续费: {snap['commission']:.2f}")

            # 增加迭代计数器
            iteration += 1
            # 检查是否达到最大迭代次数
            if max_iterations is not None and iteration >= max_iterations:
                self.logger.info(f"[策略结束] 达到最大迭代次数: {max_iterations}")
                break

    def get_current_position(self) -> int:
        """
        获取当前目标仓位任务
        
        Returns:
            TargetPosTask: 当前的目标仓位任务对象
        """
        return self.target_pos

    def get_account_snapshot(self) -> dict:
        """
        获取最后一次保存的账户快照
        
        Returns:
            dict: 账户快照，包含初始余额、当前权益、可用资金等信息
        """
        return self._last_account_snapshot

    def set_target_volume(self, volume: int) -> None:
        """
        手动设置目标仓位
        
        Args:
            volume: 目标仓位（正数=多头，负数=空头，0=空仓）
        """
        self.target_pos.set_target_volume(volume)


def create_strategy(
    api: TqApi,
    logger,
    symbol: str = "SHFE.rb2501",
    short_period: int = 5,
    long_period: int = 20,
    kline_dur: int = 60 * 60,
    volume: int = 1,
) -> DoubleMAStrategy:
    """
    创建双均线策略实例的工厂函数
    
    提供一个便捷的方式创建双均线策略实例，使用默认参数或自定义参数

    Args:
        api: TqApi 实例，用于与期货交易系统交互
        logger: 日志记录器，用于记录策略运行信息
        symbol: 交易合约代码，默认值为 "SHFE.rb2501"（上期所螺纹钢2501合约）
        short_period: 短期均线周期，默认值为 5
        long_period: 长期均线周期，默认值为 20
        kline_dur: K线周期（秒），默认值为 3600（1小时K线）
        volume: 持仓手数，默认值为 1

    Returns:
        DoubleMAStrategy: 策略实例
    """
    return DoubleMAStrategy(
        api=api,
        logger=logger,
        symbol=symbol,
        short_period=short_period,
        long_period=long_period,
        kline_dur=kline_dur,
        volume=volume,
    )
