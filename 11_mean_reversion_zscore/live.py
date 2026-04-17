#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Z-Score均值回归策略 - 实盘入口
===============================

使用 TqAccount 连接实盘期货交易账户

⚠️ 警告：实盘交易将产生真实的资金盈亏，请谨慎操作！

运行方式：
    python live.py

配置说明：
    - 实盘账户信息从 tq_account_config.json 文件读取
    - 修改策略参数调整策略逻辑

支持的期货公司：
    https://www.shinnytech.com/blog/tq-support-broker/

常用期货公司代码示例：
    - H海通期货
    - H宏源期货
    - N南华期货
    - C中信期货
    - G国泰君安
"""

import json
import os
import sys
import webbrowser
from tqsdk import TqApi, TqAuth, TqAccount
from strategy import MeanReversionZScoreStrategy

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger


# ===================== 实盘配置 =====================
SYMBOL = "KQ.m@DCE.m"             # 交易合约：连续主力合约（豆粕）
ZSCORE_N = 20                     # Z-Score计算回望周期
ENTRY_Z = 2.0                     # 开仓Z-Score阈值
EXIT_Z = 0.5                      # 平仓Z-Score阈值
MAX_HOLD_BARS = 10                # 最大持仓K线数
KLINE_DUR = 1800                  # K线周期：1800秒 = 30分钟K线
VOLUME = 1                        # 持仓手数

ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)

# ===================== Web GUI 配置 =====================
WEB_GUI_PORT = 8888
# =======================================================


def load_userinfo(filepath: str) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[账号信息] 已从文件加载: {filepath}")
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"账号信息文件不存在: {filepath}")
    except json.JSONDecodeError as e:
        raise ValueError(f"账号信息文件格式错误: {e}")


def run_strategy(symbol: str, broker_id: str, account_id: str, password: str):
    zscore_n = ZSCORE_N
    entry_z = ENTRY_Z
    exit_z = EXIT_Z
    max_hold_bars = MAX_HOLD_BARS
    kline_dur = KLINE_DUR
    volume = VOLUME

    logger = setup_logger(f"live_{symbol.split('.')[-1]}")

    print(f"\n{'='*60}")
    print(f"实盘交易 | {symbol}")
    print(f"{'='*60}")
    print(f"期货公司: {broker_id}")
    print(f"资金账号: {account_id}")
    print(f"交易合约: {symbol}")
    print(f"回望N: {zscore_n} | 开仓Z: {entry_z} | 平仓Z: {exit_z} | 最大持仓: {max_hold_bars}根 | K线: {kline_dur//60}min")
    print(f"固定手数: {volume} 手")
    print("=" * 60)
    print("⚠️  警告：实盘交易将产生真实的资金盈亏！")
    print("=" * 60)

    api = None
    strategy = None
    account_summary = None

    try:
        account = TqAccount(broker_id, account_id, password)
        print(f"[账户类型] 实盘账户 ({broker_id})")

        api = TqApi(
            account=account,
            auth=TqAuth(account_id, password),
            web_gui=f"http://0.0.0.0:{WEB_GUI_PORT}",
        )

        print("[OK] API 初始化成功，Web GUI 已启动")
        print(f"[OK] 请在浏览器中打开: http://localhost:{WEB_GUI_PORT}")
        print("[提示] 策略将自动运行，可在GUI界面实时观察交易情况\n")
        webbrowser.open(f"http://localhost:{WEB_GUI_PORT}")

        strategy = MeanReversionZScoreStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            zscore_n=zscore_n,
            entry_z=entry_z,
            exit_z=exit_z,
            max_hold_bars=max_hold_bars,
            kline_dur=kline_dur,
            volume=volume,
        )

        strategy.run()

    except KeyboardInterrupt:
        print("\n[用户中断] 策略停止")
    except Exception as e:
        print(f"[实盘异常] {e}")
    finally:
        if api:
            try:
                if strategy:
                    snap = strategy.get_account_snapshot()
                    if snap:
                        account_summary = snap
                    else:
                        acc = api.get_account()
                        account_summary = {
                            "static_balance": acc.static_balance,
                            "balance": acc.balance,
                            "available": acc.available,
                            "float_profit": acc.float_profit,
                            "position_profit": acc.position_profit,
                            "close_profit": acc.close_profit,
                            "margin": acc.margin,
                            "commission": acc.commission,
                        }
                else:
                    acc = api.get_account()
                    account_summary = {
                        "static_balance": acc.static_balance,
                        "balance": acc.balance,
                        "available": acc.available,
                        "float_profit": acc.float_profit,
                        "position_profit": acc.position_profit,
                        "close_profit": acc.close_profit,
                        "margin": acc.margin,
                        "commission": acc.commission,
                    }
            except Exception as e:
                print(f"[获取账户信息失败] {e}")
            finally:
                try:
                    api.close()
                except Exception:
                    pass

    if account_summary:
        init_bal = account_summary['static_balance']
        final_bal = account_summary['balance']
        profit = final_bal - init_bal
        ret_rate = (profit / init_bal * 100) if init_bal > 0 else 0

        print(f"\n{'='*60}")
        print(f"交易结果: {symbol}")
        print(f"{'='*60}")
        print(f"初始资金:   {init_bal:>15,.2f} 元")
        print(f"期末资金:   {final_bal:>15,.2f} 元")
        print(f"净利润:     {profit:>+15,.2f} 元")
        print(f"收益率:     {ret_rate:>+14.4f}%")
        print(f"平仓盈亏:   {account_summary.get('close_profit', 0):>+15,.2f}")
        print(f"手续费:     {account_summary.get('commission', 0):>15,.2f}")
        print(f"{'='*60}\n")

    print("实盘交易结束")


def main():
    print("=" * 60)
    print("Z-Score均值回归策略 - 实盘交易入口")
    print("=" * 60)

    config = load_userinfo(ACCOUNT_CONFIG_FILE)
    tqlive_config = config.get("tqlive", {})
    broker_id = tqlive_config.get("broker_id", "")
    account_id = tqlive_config.get("account", "")
    password = tqlive_config.get("password", "")

    if not broker_id or not account_id or not password:
        raise ValueError("tq_account_config.json 缺少 tqlive.broker_id、tqlive.account 或 tqlive.password 字段")

    run_strategy(SYMBOL, broker_id, account_id, password)


if __name__ == "__main__":
    main()
