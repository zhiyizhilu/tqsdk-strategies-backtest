# Dual Thrust 日内突破策略

## 策略简介

Dual Thrust 是一个经典的日内突破策略，由 Michael Chalek 在 20 世纪 80 年代开发。该策略通过计算过去 N 日的价格波动范围，结合当日开盘价确定上下轨，当价格突破上轨时做多，跌破下轨时做空，并在收盘前强制平仓。

## 策略逻辑

### 计算公式

```
Range = max(HH - LC, HC - LL)
上轨 = 今日开盘价 + K1 × Range
下轨 = 今日开盘价 - K2 × Range
```

其中：
- **HH** = N 日最高价
- **LL** = N 日最低价
- **HC** = N 日收盘价最高值
- **LC** = N 日收盘价最低值

### 交易规则

1. **突破上轨** → 做多（买入开仓）
2. **跌破下轨** → 做空（卖出开仓）
3. **收盘前** → 强制平仓（避免隔夜风险）

## 文件说明

| 文件名 | 说明 |
|--------|------|
| `strategy.py` | Dual Thrust 策略核心实现（类封装） |
| `tqsim.py` | 单品种回测入口（TqSim 本地模拟） |
| `tqsim_multi_symbol.py` | 多品种回测入口（批量测试） |
| `tqkq.py` | 快期模拟盘交易入口 |
| `live.py` | 实盘交易入口 |
| `backtest_config.json` | 回测参数配置文件 |
| `origin_strategy.py` | 原始策略代码（参考） |

## 运行方式

### 1. 单品种回测

```bash
# 默认跑配置的品种
python tqsim.py

# 指定品种
python tqsim.py --symbol KQ.m@SHFE.cu
```

或直接双击：`1run_backtest.bat`

### 2. 多品种回测

```bash
# 测试所有品种
python tqsim_multi_symbol.py --all

# 测试指定品种
python tqsim_multi_symbol.py --symbol KQ.m@SHFE.cu
```

或直接双击：`1run_multi_backtest.bat`

### 3. 模拟盘交易

```bash
python tqkq.py
```

或直接双击：`2run_simulation.bat`

### 4. 实盘交易

```bash
python live.py
```

或直接双击：`3run_live.bat`

## 参数配置

### 策略参数（可在 `tqsim.py` 头部修改）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `SYMBOL` | `KQ.m@SHFE.cu` | 交易合约（连续主力） |
| `N_DAYS` | 4 | 回溯天数 |
| `K1` | 0.5 | 上轨系数 |
| `K2` | 0.5 | 下轨系数 |
| `VOLUME` | 1 | 持仓手数 |
| `INITIAL_BALANCE` | 1000000 | 初始资金（元） |
| `MARGIN_RATIO` | 0.1 | 保证金比例（None=固定手数） |

### 账户配置

账户信息从上级目录的 `tq_account_config.json` 文件读取，需要配置：
- `tqsim.tq_username` / `tqsim.tq_password` - 快期账号（回测用）
- `tqkq.tq_username` / `tqkq.tq_password` - 快期账号（模拟盘用）
- `tqlive.broker_id` / `tqlive.account` / `tqlive.password` - 实盘账户

## 适用品种

波动性较强的品种效果较好：
- **铜**（SHFE.cu）
- **黄金**（SHFE.au）
- **原油**（INE.sc）
- **螺纹钢**（SHFE.rb）

## 风险提示

- 日内策略在震荡行情中容易产生假突破信号
- 建议结合成交量、波动率等过滤器使用
- 本代码仅供学习参考，不构成任何投资建议

## 依赖

```bash
pip install tqsdk -U
```

## 文档

- TqSDK 官方文档：https://doc.shinnytech.com/tqsdk/latest/
- Dual Thrust 策略介绍：https://www.shinnytech.com/blog/dual-thrust/
