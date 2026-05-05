#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多周期均线共振策略 - 模拟盘交易入口（TqKq）
==============================================

使用 TqKq 连接天勤快期模拟账户进行模拟交易。

运行方式：
    python tqkq.py
"""

import json
import os
import sys
import webbrowser
from tqsdk import TqApi, TqAuth, TqKq

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger
from strategy import MultiPeriodMAStrategy


# ===================== 模拟盘配置 =====================
SYMBOL = "KQ.m@SHFE.au"
DAY_MA_N = 20
HOUR_MA_N = 20
MIN15_FAST_N = 5
MIN15_SLOW_N = 20
VOLUME = 1
INITIAL_BALANCE = 1000000
MARGIN_RATIO = 0.1

ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)

WEB_GUI_PORT = 9875
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


def run_strategy(symbol: str, tq_account: str, tq_password: str):
    day_ma_n = DAY_MA_N
    hour_ma_n = HOUR_MA_N
    min15_fast_n = MIN15_FAST_N
    min15_slow_n = MIN15_SLOW_N
    volume = VOLUME
    initial_balance = INITIAL_BALANCE
    margin_ratio = MARGIN_RATIO

    logger = setup_logger(f"tqkq_{symbol.split('@')[-1].split('.')[0]}")

    print(f"\n{'='*60}")
    print(f"模拟盘交易 | {symbol}")
    print(f"{'='*60}")
    print(f"交易合约: {symbol}（主力连续合约）")
    print(f"日MA{day_ma_n} + 时MA{hour_ma_n} + 15m MA{min15_fast_n}/{min15_slow_n}")
    if margin_ratio is not None:
        print(f"初始资金: {initial_balance:,.0f}元 | 动态仓位（保证金×{margin_ratio:.0%}）")
    else:
        print(f"固定手数: {volume} 手")

    api = None
    strategy = None
    account_summary = None

    try:
        account = TqKq()
        print("[账户类型] 快期模拟盘 (TqKq)")

        api = TqApi(
            account=account,
            auth=TqAuth(tq_account, tq_password),
            web_gui=f"http://0.0.0.0:{WEB_GUI_PORT}",
        )

        print("[OK] API 初始化成功，Web GUI 已启动")
        print(f"[OK] 请在浏览器中打开: http://localhost:{WEB_GUI_PORT}")
        print("[提示] 策略将自动运行，可在GUI界面实时观察交易情况\n")
        webbrowser.open(f"http://localhost:{WEB_GUI_PORT}")

        strategy = MultiPeriodMAStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            day_ma_n=day_ma_n,
            hour_ma_n=hour_ma_n,
            min15_fast_n=min15_fast_n,
            min15_slow_n=min15_slow_n,
            volume=volume,
            use_continuous=True,
            initial_balance=initial_balance if margin_ratio else None,
            margin_ratio=margin_ratio,
        )

        strategy.run()

    except KeyboardInterrupt:
        print("\n[用户中断] 策略停止")
    except Exception as e:
        print(f"[模拟盘异常] {e}")
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
                account_summary = {
                    "static_balance": initial_balance,
                    "balance": initial_balance,
                    "available": initial_balance,
                    "float_profit": 0,
                    "position_profit": 0,
                    "close_profit": 0,
                    "margin": 0,
                    "commission": 0,
                }
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

    print("模拟盘交易结束")


def main():
    print("=" * 60)
    print("多周期均线共振策略 - 快期模拟盘（TqKq）")
    print("=" * 60)

    account_config = load_userinfo(ACCOUNT_CONFIG_FILE)
    tqkq_config = account_config.get("tqkq", {})
    tq_account = tqkq_config.get("tq_username", "")
    tq_password = tqkq_config.get("tq_password", "")

    if not tq_account or not tq_password:
        raise ValueError("tq_account_config.json 缺少 tqkq.tq_username 或 tqkq.tq_password 字段")

    run_strategy(SYMBOL, tq_account, tq_password)


if __name__ == "__main__":
    main()
