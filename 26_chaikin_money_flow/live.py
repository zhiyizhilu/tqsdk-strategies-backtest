#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
蔡金资金流量策略 - 实盘入口
=====================

使用 TqAccount 连接实盘期货交易账户

⚠️ 警告：实盘交易将产生真实的资金盈亏，请谨慎操作！

运行方式：
    python live.py
"""

import json
import os
import sys
import webbrowser
from tqsdk import TqApi, TqAuth, TqAccount
from strategy import ChaikinMoneyFlowStrategy

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger


SYMBOL = "KQ.m@SHFE.cu"
CMF_N = 20
KLINE_DUR = 86400
VOLUME = 1
BULL_TH = 0.05
BEAR_TH = -0.05

ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)

WEB_GUI_PORT = 8888


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
    cmf_n = CMF_N
    kline_dur = KLINE_DUR
    volume = VOLUME
    bull_th = BULL_TH
    bear_th = BEAR_TH

    logger = setup_logger(f"live_{symbol.split('.')[-1]}")

    print(f"\n{'='*60}")
    print(f"实盘交易 | {symbol}")
    print(f"{'='*60}")
    print(f"期货公司: {broker_id}")
    print(f"资金账号: {account_id}")
    print(f"交易合约: {symbol}")
    print(f"CMF窗口: {cmf_n} | 多头阈值: {bull_th} | 空头阈值: {bear_th} | K线: {'日线' if kline_dur >= 86400 else f'{kline_dur//3600}h'}")
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

        strategy = ChaikinMoneyFlowStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            cmf_n=cmf_n,
            kline_dur=kline_dur,
            volume=volume,
            bull_th=bull_th,
            bear_th=bear_th,
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
    print("蔡金资金流量策略 - 实盘交易入口")
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
