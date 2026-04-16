#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KDJ信号策略 - 单品种回测入口（TqSim）
======================================

使用 TqSim 本地模拟账户进行单品种历史回测，
策略参数在文件头部直接配置。

运行方式：
    # 默认跑配置的品种
    python tqsim.py

    # 指定品种
    python tqsim.py --symbol KQ.m@DCE.m

输出：
    回测结果打印到控制台
"""

import json
import os
import sys
import webbrowser
import time
from datetime import datetime
from tqsdk import TqApi, TqAuth, TqBacktest, TqSim

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger
from strategy import KDJSignalStrategy


SYMBOL = "KQ.m@INE.lu"
KDJ_N = 9
KDJ_M1 = 3
KDJ_M2 = 3
OVERBUY = 80
OVERSELL = 20
KLINE_DUR = 60 * 30
VOLUME = 1
INITIAL_BALANCE = 1000000
MARGIN_RATIO = 0.1
START_DATE = "2026-01-01"
END_DATE = "2026-04-08"

ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)

WEB_GUI_PORT = 9876


def load_userinfo(filepath: str) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[账号信息] 已从文件加载: {filepath}")
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"账号信息文件不存在: {filepath}")


def run_single_backtest(symbol: str, tq_account: str, tq_password: str):
    start_date = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    end_date = datetime.strptime(END_DATE, "%Y-%m-%d").date()
    kdj_n = KDJ_N
    kdj_m1 = KDJ_M1
    kdj_m2 = KDJ_M2
    overbuy = OVERBUY
    oversell = OVERSELL
    kline_dur = KLINE_DUR
    volume = VOLUME
    initial_balance = INITIAL_BALANCE
    margin_ratio = MARGIN_RATIO

    logger = setup_logger(f"tqsim_{symbol.split('@')[-1].split('.')[0]}")

    print(f"\n{'='*60}")
    print(f"单品种回测 | {symbol}")
    print(f"{'='*60}")
    print(f"回测区间: {start_date} ~ {end_date}")
    print(f"初始资金: {initial_balance:,.0f}元")
    if margin_ratio is not None:
        print(f"仓位模式: 动态（总资产×{margin_ratio:.0%}保证金）")
    else:
        print(f"仓位模式: 固定（{volume}手）")
    print(f"KDJ参数: N={kdj_n} M1={kdj_m1} M2={kdj_m2} | 超买={overbuy} 超卖={oversell}")

    loop = __import__("asyncio").new_event_loop()
    __import__("asyncio").set_event_loop(loop)

    api = None
    strategy = None
    account_summary = None

    try:
        api = TqApi(
            account=TqSim(init_balance=initial_balance),
            backtest=TqBacktest(start_dt=start_date, end_dt=end_date),
            auth=TqAuth(tq_account, tq_password),
            web_gui=f"http://0.0.0.0:{WEB_GUI_PORT}",
        )

        print(f"[OK] API 初始化成功，Web GUI 已启动")
        print(f"[OK] 请在浏览器中打开: http://localhost:{WEB_GUI_PORT}")
        print(f"[提示] 回测将自动运行，可在GUI界面实时观察\n")
        webbrowser.open(f"http://localhost:{WEB_GUI_PORT}")

        strategy = KDJSignalStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            kdj_n=kdj_n,
            kdj_m1=kdj_m1,
            kdj_m2=kdj_m2,
            overbuy=overbuy,
            oversell=oversell,
            kline_dur=kline_dur,
            volume=volume,
            use_continuous=True,
            initial_balance=initial_balance,
            margin_ratio=margin_ratio,
        )

        strategy.run()

    except Exception as e:
        if "回测结束" in str(e):
            print("[回测正常结束]")

            report_url = f"http://localhost:{WEB_GUI_PORT}/#/report/TQSIM"
            print("\n[提示] 回测已完成，Web GUI 仍在运行")
            print(f"[提示] 正在自动打开统计结果页面: {report_url}")
            print("[提示] 20秒后自动关闭程序...")
            webbrowser.open(report_url)

            api.wait_update(deadline=(time.time() + 20))
        else:
            print(f"[回测异常] {e}")
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

    if not account_summary:
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

    init_bal = account_summary['static_balance']
    final_bal = account_summary['balance']
    profit = final_bal - init_bal
    ret_rate = (profit / init_bal * 100) if init_bal > 0 else 0

    print(f"\n{'='*60}")
    print(f"回测结果: {symbol}")
    print(f"{'='*60}")
    print(f"初始资金:   {init_bal:>15,.2f} 元")
    print(f"期末资金:   {final_bal:>15,.2f} 元")
    print(f"净利润:     {profit:>+15,.2f} 元")
    print(f"收益率:     {ret_rate:>+14.4f}%")
    print(f"平仓盈亏:   {account_summary.get('close_profit', 0):>+15,.2f}")
    print(f"手续费:     {account_summary.get('commission', 0):>15,.2f}")
    print(f"{'='*60}\n")

    return account_summary


def main():
    print("=" * 60)
    print("KDJ信号策略 - TqSim 回测入口")
    print("=" * 60)

    account_config = load_userinfo(ACCOUNT_CONFIG_FILE)
    tqsim_cfg = account_config.get("tqsim", {})
    tq_account = tqsim_cfg.get("tq_username", "")
    tq_password = tqsim_cfg.get("tq_password", "")

    if not tq_account or not tq_password:
        raise ValueError("tq_account_config.json 缺少 tqsim.tq_username 或 tqsim.tq_password")

    run_single_backtest(SYMBOL, tq_account, tq_password)


if __name__ == "__main__":
    main()
