#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
布林带突破策略 - 单品种回测入口（TqSim）
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

# 将上级目录添加到系统路径，以便导入 logger_config 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger
from strategy import BollBreakoutStrategy


# ===================== 回测配置 =====================
# 策略参数
SYMBOL = "KQ.m@CZCE.TA"          # 交易合约：连续主力合约
N_PERIOD = 20                # 布林带计算周期：20根K线
K_TIMES = 2.0                # 标准差倍数：2.0
KLINE_DUR = 60 * 60             # K线周期：3600秒 = 1小时K线
VOLUME = 1                      # 固定持仓手数（如需动态仓位设为 None）
MIN_BAND_WIDTH = 0.01           # 最小带宽比例
INITIAL_BALANCE = 1000000       # 初始资金（元）
MARGIN_RATIO = 0.1              # 保证金比例（None=固定手数，0.1=总资产10%）
START_DATE = "2026-01-01"        # 回测开始日期
END_DATE = "2026-04-08"          # 回测结束日期

# 账号信息文件路径
ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)
# ===================================================

# ===================== Web GUI 配置 =====================
WEB_GUI_PORT = 9876  # Web GUI 端口
# =======================================================


def load_userinfo(filepath: str) -> dict:
    """从 JSON 文件加载快期账号信息"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[账号信息] 已从文件加载: {filepath}")
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"账号信息文件不存在: {filepath}")


def run_single_backtest(symbol: str, tq_account: str, tq_password: str):
    """
    运行单个品种的回测
    
    Args:
        symbol: 合约代码
        tq_account: 快期账号
        tq_password: 快期密码
    """
    start_date = datetime.strptime(START_DATE, "%Y-%m-%d").date()
    end_date = datetime.strptime(END_DATE, "%Y-%m-%d").date()
    n_period = N_PERIOD
    k_times = K_TIMES
    kline_dur = KLINE_DUR
    volume = VOLUME
    min_band_width = MIN_BAND_WIDTH
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
    print(f"周期: MA{n_period} | 倍数: {k_times} | 最小带宽: {min_band_width}")

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
            web_gui=f"http://0.0.0.0:{WEB_GUI_PORT}",  # 开启 Web GUI
        )

        print(f"[OK] API 初始化成功，Web GUI 已启动")
        print(f"[OK] 请在浏览器中打开: http://localhost:{WEB_GUI_PORT}")
        print(f"[提示] 回测将自动运行，可在GUI界面实时观察\n")
        webbrowser.open(f"http://localhost:{WEB_GUI_PORT}")

        strategy = BollBreakoutStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            n_period=n_period,
            k_times=k_times,
            kline_dur=kline_dur,
            volume=volume,
            min_band_width=min_band_width,
            use_continuous=True,
            initial_balance=initial_balance,
            margin_ratio=margin_ratio,
        )

        strategy.run()

    except Exception as e:
        if "回测结束" in str(e):
            print("[回测正常结束]")
            
            # 回测结束后保持运行，以便访问web页面
            report_url = f"http://localhost:{WEB_GUI_PORT}/#/report/TQSIM"
            print("\n[提示] 回测已完成，Web GUI 仍在运行")
            print(f"[提示] 正在自动打开统计结果页面: {report_url}")
            print("[提示] 20秒后自动关闭程序...")
            # 自动打开浏览器
            webbrowser.open(report_url)

            # 等待20秒
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
    print("布林带突破策略 - TqSim 回测入口")
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
