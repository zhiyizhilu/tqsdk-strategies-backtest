# Z-Score均值回归策略 (Mean Reversion Z-Score Strategy)

## 策略逻辑

- **计算指标**：计算价格在过去N期内的均值（Mean）和标准差（Std）
- **Z-Score计算**：Z = (当前价格 - N期均值) / N期标准差
- **开仓信号**：
  - 当 Z-Score > ENTRY_Z（价格统计意义上"过高"），做空
  - 当 Z-Score < -ENTRY_Z（价格统计意义上"过低"），做多
- **平仓信号**：
  - 当 Z-Score 回归至 EXIT_Z 附近时，认为均值回归完成，平仓
  - 当持仓超过 MAX_HOLD_BARS 根K线时，强制平仓（控制风险）

## 为什么用 TargetPosTask 而不是 insert_order

- **insert_order** 只是"发一笔委托"，策略需要自己跟踪订单状态：
  - 委托未成交怎么办？追单？改价？
  - 部分成交时剩余量如何处理？
  - 反手时先撤未成交的单？

- **TargetPosTask** 封装了这一切：
  - 只需告诉它"我现在想持有多少手"
  - 它自动计算需要买卖的数量，并持续追单直到达到目标仓位
  - 目标仓位改变时会自动撤掉旧委托再按新目标下单
  - 正数 = 多头 N 手，负数 = 空头 N 手，0 = 全部平仓

## 适用品种

- **适合**：均值回归特性强的品种，如豆粕（DCE.m）、菜油（CZCE.OI）、贵金属等
- **不适合**：单边趋势明显的品种（价格持续偏离均值不回归）

## 风险提示

- 在强趋势行情中，价格可能长期不回归，持续亏损
- 均值和标准差的回望期N对结果影响极大
- 建议配合趋势过滤使用
- 本代码仅供学习参考，不构成任何投资建议

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| SYMBOL | 交易合约代码 | "DCE.m2506" |
| ZSCORE_N | Z-Score计算回望周期（K线根数） | 20 |
| ENTRY_Z | 开仓Z-Score阈值 | 2.0 |
| EXIT_Z | 平仓Z-Score阈值 | 0.5 |
| MAX_HOLD_BARS | 最大持仓K线数 | 10 |
| KLINE_DUR | K线周期（秒） | 1800 (30分钟) |
| VOLUME | 持仓手数 | 1 |

## 核心指标计算

```python
# 计算N期均值
mean_n = ma(close, ZSCORE_N)

# 计算N期标准差
std_n = std(close, ZSCORE_N)

# 计算Z-Score
zscore = (close_cur - mean_cur) / std_cur
```

## 信号判断

```python
# 开多信号：Z-Score < -ENTRY_Z
if zscore < -ENTRY_Z:
    target_pos.set_target_volume(VOLUME)  # 做多

# 开空信号：Z-Score > ENTRY_Z
elif zscore > ENTRY_Z:
    target_pos.set_target_volume(-VOLUME)  # 做空

# 平多信号：Z-Score > -EXIT_Z 或 持仓超时
if volume_long > 0 and (zscore > -EXIT_Z or hold_bars_count >= MAX_HOLD_BARS):
    target_pos.set_target_volume(0)  # 平仓

# 平空信号：Z-Score < EXIT_Z 或 持仓超时
if volume_short > 0 and (zscore < EXIT_Z or hold_bars_count >= MAX_HOLD_BARS):
    target_pos.set_target_volume(0)  # 平仓
```

## 目录结构

```
11_mean_reversion_zscore/
├── 1run_backtest.bat        # 单品种回测快捷启动
├── 1run_multi_backtest.bat   # 多品种回测快捷启动
├── 2run_simulation.bat       # 模拟盘快捷启动
├── 3run_live.bat             # 实盘快捷启动
├── README.md                 # 策略说明文档
├── backtest_config.json      # 多品种回测配置
├── backtest_generate_report.py  # HTML报告生成器
├── live.py                   # 实盘交易入口
├── origin_strategy.py        # 原始策略代码
├── strategy.py               # 核心策略类
├── tqkq.py                   # 快期模拟盘入口
├── tqsim.py                  # 本地模拟回测入口
└── tqsim_multi_symbol.py     # 多品种回测脚本
```

## 运行方式

### 1. 单品种回测
```bash
python tqsim.py
# 或指定品种
python tqsim.py --symbol KQ.m@DCE.m
```

### 2. 多品种回测
```bash
python tqsim_multi_symbol.py --all  # 测试所有品种
python tqsim_multi_symbol.py --symbol KQ.m@DCE.m  # 测试指定品种
```

### 3. 生成回测报告
```bash
python backtest_generate_report.py
```

### 4. 模拟盘交易
```bash
python tqkq.py
```

### 5. 实盘交易
```bash
python live.py
```

## 依赖

```bash
pip install tqsdk -U
```

## 文档

- [TqSdk 官方文档](https://doc.shinnytech.com/tqsdk/latest/)
- [TargetPosTask 参考](https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.api.html#tqsdk.api.TqApi.TargetPosTask)

## 作者

- tqsdk-strategies
