# 布林带突破策略 (Bollinger Bands Breakout Strategy)

## 策略简介

布林带突破策略是一种基于技术分析的趋势跟踪策略，利用布林带指标来识别价格突破和趋势方向。

### 策略逻辑

- **布林带计算**：由中轨（N周期移动平均线）和上下轨（中轨 ± K倍标准差）组成
  - 上轨 = MA(N) + K × STD(N)
  - 中轨 = MA(N)
  - 下轨 = MA(N) - K × STD(N)

- **交易信号**：
  - 价格向上突破上轨：趋势突破信号，做多
  - 价格向下突破下轨：趋势突破信号，做空
  - 价格回落至中轨以下（多头）或回升至中轨以上（空头）：趋势减弱，平仓

- **带宽过滤**：
  - 布林带宽度（带宽）= (上轨 - 下轨) / 中轨
  - 带宽越大 → 市场波动越大 → 突破信号越有效
  - 低于最小带宽时不入场，避免震荡市假突破

## 目录结构

```
02_boll_breakout/
├── 1run_backtest.bat        # 单品种回测运行脚本
├── 1run_multi_backtest.bat  # 多品种回测运行脚本
├── 2run_simulation.bat      # 模拟交易运行脚本
├── 3run_live.bat            # 实盘交易运行脚本
├── backtest_config.json      # 回测配置文件
├── backtest_generate_report.py  # 回测报告生成器
├── live.py                   # 实盘交易入口
├── origin_strategy.py        # 原始策略文件
├── README.md                 # 本说明文件
├── strategy.py               # 策略核心实现
├── tqsim.py                 # 单品种回测入口
└── tqsim_multi_symbol.py     # 多品种回测入口
```

## 依赖

- Python 3.7+
- tqsdk：`pip install tqsdk -U`

## 快速开始

### 1. 配置账号信息

在 `tq_account_config.json` 文件中配置快期账号信息：

```json
{
    "tqsim": {
        "tq_username": "你的快期账号",
        "tq_password": "你的快期密码"
    },
    "live": {
        "tq_username": "你的快期账号",
        "tq_password": "你的快期密码"
    }
}
```

### 2. 运行回测

#### 单品种回测
1. 双击运行 `1run_backtest.bat`
2. 或在命令行执行：`python tqsim.py`
3. 可指定品种：`python tqsim.py --symbol KQ.m@DCE.m`

#### 多品种回测
1. 双击运行 `1run_multi_backtest.bat`
2. 或在命令行执行：`python tqsim_multi_symbol.py --all`
3. 回测结果会保存到 `backtest_result.csv`
4. 自动生成 HTML 分析报告 `backtest_report.html`

### 3. 运行模拟交易

1. 双击运行 `2run_simulation.bat`
2. 或在命令行执行：`python tqsim.py`

### 4. 运行实盘交易

1. 双击运行 `3run_live.bat`
2. 或在命令行执行：`python live.py`
3. **注意：实盘交易存在风险，请谨慎使用**

## 策略参数

策略参数可在各文件中配置：

- **strategy.py**：默认参数配置
- **tqsim.py**：单品种回测参数
- **tqsim_multi_symbol.py**：多品种回测参数（从 backtest_config.json 读取）
- **live.py**：实盘交易参数
- **backtest_config.json**：多品种回测配置

### 主要参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| symbol | 交易合约代码 | DCE.m2501 |
| n_period | 布林带计算周期（K线根数） | 20 |
| k_times | 标准差倍数 | 2.0 |
| kline_dur | K线周期（秒） | 3600（1小时） |
| volume | 固定持仓手数 | 1 |
| min_band_width | 最小带宽比例 | 0.01 |
| initial_balance | 初始资金（元） | 1000000 |
| margin_ratio | 保证金比例 | 0.1（10%） |

## 回测报告

多品种回测完成后，会生成以下文件：

- **backtest_result.csv**：回测结果数据
- **backtest_report.html**：美观的 HTML 分析报告，包含：
  - 回测概览（胜率、收益率等）
  - 交易所分布统计
  - 收益率分布图表
  - 详细回测结果表格

## 策略特点

1. **趋势跟踪**：利用布林带突破识别趋势方向
2. **带宽过滤**：避免在低波动期入场，减少假突破
3. **动态仓位**：支持基于账户资金和保证金比例的动态仓位计算
4. **连续合约**：支持使用连续主力合约，自动处理合约换月
5. **多品种回测**：支持批量回测多个品种，生成综合分析报告
6. **Web GUI**：回测过程中可通过 Web 界面实时观察

## 风险提示

- 本策略在趋势明显的市场环境中表现较好，在震荡行情中可能产生频繁假信号
- 回测结果仅供参考，不代表未来表现
- 实盘交易存在风险，请根据自身风险承受能力谨慎使用
- 建议在使用前充分了解策略逻辑和参数设置

## 参考文档

- [TqSDK 官方文档](https://doc.shinnytech.com/tqsdk/latest/)
- [布林带指标详解](https://www.investopedia.com/terms/b/bollingerbands.asp)
