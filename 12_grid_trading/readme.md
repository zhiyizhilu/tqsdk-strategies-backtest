# 网格交易策略 (Grid Trading Strategy)

## 策略简介

网格交易（Grid Trading）是一种以固定价格间距，在预设价格区间内分层布置买单和卖单，通过价格在区间内的波动来反复盈利的量化交易策略。

**核心理念**：不预测价格方向，利用价格的上下波动套利。只要价格在设定的区间内震荡，每一次价格穿越网格线都可以完成一次低买高卖的循环，积累小额利润。

### 策略逻辑

1. 预设价格区间 `[GRID_LOW, GRID_HIGH]`
2. 按固定间距 `GRID_STEP` 划分若干网格线
3. 价格从上方跌穿网格线 → 买入（低买）
4. 价格从下方涨穿网格线 → 卖出（高卖）
5. 价格突破区间上限 → 平掉所有多仓
6. 价格跌破区间下限 → 停止买入

### 适用品种

| 适合 | 不适合 |
|------|--------|
| 价格长期在区间内震荡的品种（豆粕、玉米、黄金） | 单边趋势强烈的品种 |
| 历史波动率适中、趋势性不强的品种 | 波动率极高且单边行情的品种 |

### 优缺点

**优点：**
- 不需要预测价格方向，在震荡市场中持续盈利
- 策略逻辑简单，自动化程度高，情绪干扰少
- 只要价格在区间内，每次波动都能产生利润
- 可通过调整网格密度灵活适应不同波动率

**缺点：**
- 单边趋势行情中可能持续买入而价格持续下跌（左侧接刀）
- 需要大量资金分散在多个网格层级
- 价格突破区间后策略失效，需手动调整区间
- 期货到期换月时需要重新设置网格
- 手续费累积对策略盈利有较大影响

---

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `SYMBOL` | `KQ.m@CZCE.MA` | 交易合约代码，`KQ.m@` 前缀表示连续主力合约（自动换月） |
| `GRID_LOW` | 2200 | 网格区间下限价格 |
| `GRID_HIGH` | 2600 | 网格区间上限价格 |
| `GRID_STEP` | 40 | 网格间距（每格价格差） |
| `VOLUME` | 1 | 每格交易手数 |
| `MAX_GRID_POSITION` | 10 | 最大允许持仓手数（风控） |
| `INITIAL_BALANCE` | 1000000 | 初始资金（元），仅回测使用 |

### 计算公式

```
网格数量 = (GRID_HIGH - GRID_LOW) / GRID_STEP
每格理论利润（不含手续费）= GRID_STEP × 合约乘数
总投入资金（参考）= 网格数量 × VOLUME × 每手初始保证金
```

---

## 文件结构

```
12_grid_trading/
├── strategy.py                  # 策略核心类（GridTradingStrategy）
├── origin_strategy.py           # 原始策略脚本（单文件版，仅供学习参考）
├── tqsim.py                     # 单品种回测入口（TqSim 本地模拟）
├── tqsim_multi_symbol.py        # 多品种批量回测入口
├── tqkq.py                      # 模拟盘交易入口（TqKq 快期模拟环境）
├── live.py                      # 实盘交易入口（TqAccount）
├── backtest_config.json         # 多品种回测配置文件
├── backtest_generate_report.py  # 回测结果 HTML 报告生成器
├── 1run_backtest.bat            # Windows 快捷启动：单品种回测
├── 1run_multi_backtest.bat      # Windows 快捷启动：多品种回测
├── 2run_simulation.bat          # Windows 快捷启动：模拟盘
└── 3run_live.bat                # Windows 快捷启动：实盘
```

---

## 快速开始

### 环境依赖

- Python 3.7+
- TqSdk：`pip install tqsdk -U`

### 账号配置

在项目根目录下创建 `tq_account_config.json` 文件，格式如下：

```json
{
    "tq_account": "你的天勤账号",
    "tq_password": "你的天勤密码",
    "broker_id": "期货公司代码（实盘用）",
    "account_id": "期货账户（实盘用）",
    "account_password": "期货密码（实盘用）"
}
```

### 运行方式

#### 1. 单品种回测

```bash
# 使用默认品种
python tqsim.py

# 指定品种
python tqsim.py --symbol KQ.m@CZCE.MA
```

或双击 `1run_backtest.bat`

#### 2. 多品种批量回测

先编辑 `backtest_config.json` 配置回测品种和参数，然后：

```bash
python tqsim_multi_symbol.py
```

或双击 `1run_multi_backtest.bat`

回测完成后结果保存在 `backtest_result.csv`。

#### 3. 生成回测报告

```bash
python backtest_generate_report.py
```

读取 `backtest_result.csv`，生成 `backtest_report.html` 可视化报告。

#### 4. 模拟盘交易

```bash
python tqkq.py
```

或双击 `2run_simulation.bat`

> 使用天勤快期免费模拟环境，行情与真实市场一致，不产生真实资金盈亏。

#### 5. 实盘交易

```bash
python live.py
```

或双击 `3run_live.bat`

> ⚠️ **警告**：实盘交易将产生真实的资金盈亏，请谨慎操作！

---

## 策略类接口

`strategy.py` 中的 `GridTradingStrategy` 是策略核心类，供各入口脚本调用：

```python
from tqsdk import TqApi
from strategy import GridTradingStrategy

api = TqApi(auth=TqAuth("账号", "密码"))
strategy = GridTradingStrategy(
    api=api,
    logger=logger,
    symbol="KQ.m@CZCE.MA",
    grid_low=2200,
    grid_high=2600,
    grid_step=40,
    volume=1,
    max_grid_position=10,
    use_continuous=True,       # 连续主力合约模式（自动换月）
    initial_balance=1000000,
)
strategy.run()  # 阻塞运行
```

### 主要特性

- **自动换月**：启用 `use_continuous=True` 后，使用 `KQ.m@` 连续主力合约，策略自动处理换月逻辑
- **最小下单量适配**：自动检测品种最小下单量并调整（如塑料、PP 等品种最小 8 手）
- **双下单模式**：支持 `TargetPosTask` 和 `insert_order` 两种下单方式，对不支持 TargetPosTask 的品种自动切换
- **合约乘数/保证金映射**：内置主流品种的合约乘数和保证金比例数据

---

## 回测配置说明

`backtest_config.json` 字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `start_date` | string | 回测开始日期，格式 `YYYY-MM-DD` |
| `end_date` | string | 回测结束日期，格式 `YYYY-MM-DD` |
| `initial_balance` | number | 初始资金（元） |
| `grid_low` | number | 网格区间下限 |
| `grid_high` | number | 网格区间上限 |
| `grid_step` | number | 网格间距 |
| `volume` | number | 每格交易手数 |
| `max_grid_position` | number | 最大允许持仓手数 |
| `symbols` | array | 回测品种列表 |
| `use_continuous_contract` | bool | 是否使用连续主力合约 |
| `output_csv` | string | 回测结果输出文件名 |

---

## 风险提示

- 本策略仅供学习参考，**不构成任何投资建议**
- 网格策略在单边趋势行情中可能产生较大亏损
- 期货交易具有杠杆风险，请充分了解风险后谨慎操作
- 实盘前建议先在模拟环境充分测试

---

## 参考文档

- [TqSdk 官方文档](https://doc.shinnytech.com/tqsdk/latest/)
- [支持的期货公司列表](https://www.shinnytech.com/blog/tq-support-broker/)
