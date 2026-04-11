# TQSDK 策略回测项目

本项目是基于 [tqsdk-strategies](https://github.com/ringoshinnytech/tqsdk-strategies) 的回测实现，提供了多种量化交易策略的回测和模拟交易功能。

## 项目结构

```
tqsdk-strategies-backtest/
├── 01_double_ma/           # 双均线策略
│   ├── origin_strategy.py  # 原始策略代码
│   ├── strategy.py         # 回测策略代码
│   ├── backtest_config.json # 回测配置文件
│   ├── backtest_result.csv  # 回测结果
│   ├── backtest_report.html # 回测报告
│   └── README.md            # 策略说明
├── 02_boll_breakout/       # 布林带突破策略
│   └── origin_strategy.py  # 原始策略代码
├── logger_config.py        # 日志配置
├── tq_account_config.json.example # 账户配置示例
├── .gitignore              # Git 忽略文件
└── README.md               # 项目说明（本文档）
```

## 策略说明

### 1. 双均线策略 (01_double_ma)
- **策略逻辑**：使用短期均线（MA5）和长期均线（MA20）的交叉信号判断趋势方向
- **金叉**：短均线从下方向上穿越长均线，目标仓位设为 +VOLUME（做多）
- **死叉**：短均线从上方向下穿越长均线，目标仓位设为 -VOLUME（做空）
- **适用品种**：趋势性较强的品种，如螺纹钢（SHFE.rb）、原油（INE.sc）、铜（SHFE.cu）等

### 2. 布林带突破策略 (02_boll_breakout)
- 基于布林带指标的突破策略
- 具体实现正在开发中

## 如何运行

### 回测
1. 进入对应策略目录（如 `01_double_ma`）
2. 修改 `backtest_config.json` 配置文件，设置回测参数
3. 运行 `backtest_generate_report.py` 生成回测报告

### 模拟交易
1. 进入对应策略目录
2. 修改 `tqsim.py` 中的账户信息
3. 运行 `2run_simulation.bat` 启动模拟交易

### 实盘交易
1. 进入对应策略目录
2. 修改 `live.py` 中的账户信息
3. 运行 `3run_live.bat` 启动实盘交易

## 依赖

```bash
pip install tqsdk -U
```

## 账户配置

在运行策略前，需要配置账户信息。复制 `tq_account_config.json.example` 文件为 `tq_account_config.json` 并填写相应的账户信息：

```json
{
    "tqsim": {
        "tq_username": "用户名",
        "tq_password": "密码"
    },
    "tqkq": {
        "tq_username": "用户名",
        "tq_password": "密码"
    },
    "tqlive": {
        "broker_id": "期货公司",
        "account": "用户名",
        "password": "密码"
    }
}
```

## 免责声明

- 本项目仅供学习参考，不构成任何投资建议
- 策略在不同市场环境下表现可能差异较大
- 实盘交易前请充分测试并评估风险

## 参考链接

- [TQSDK 官方文档](https://doc.shinnytech.com/tqsdk/latest/)
- [tqsdk-strategies 原始项目](https://github.com/ringoshinnytech/tqsdk-strategies)
- [TargetPosTask 文档](https://doc.shinnytech.com/tqsdk/latest/reference/tqsdk.api.html#tqsdk.api.TqApi.TargetPosTask)
