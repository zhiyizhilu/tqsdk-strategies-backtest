#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
布林带突破策略 - 多品种回测入口（TqSim）
======================================

使用 TqSim 本地模拟账户进行多品种历史回测，
策略参数从 backtest_config.json 读取。

运行方式：
    # 回测所有品种
    python tqsim_multi_symbol.py --all

    # 回测指定品种
    python tqsim_multi_symbol.py --symbol KQ.m@DCE.m

输出：
    回测结果保存到 backtest_result.csv，并生成 HTML 报告
"""

import json
import os
import sys
from datetime import datetime
from tqsdk import TqApi, TqAuth, TqBacktest, TqSim

# 将上级目录添加到系统路径，以便导入 logger_config 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger
from strategy import BollBreakoutStrategy


# ===================== 配置 =====================
# 配置文件路径
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_config.json")
# 回测结果 CSV 文件路径
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_result.csv")
# 账号信息文件路径
ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)
# ===================================================


def load_userinfo(filepath: str) -> dict:
    """从 JSON 文件加载快期账号信息"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[账号信息] 已从文件加载: {filepath}")
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"账号信息文件不存在: {filepath}")


def load_config(filepath: str) -> dict:
    """从 JSON 文件加载回测配置"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[配置信息] 已从文件加载: {filepath}")
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"配置文件不存在: {filepath}")


def run_single_backtest(symbol: str, config: dict, tq_account: str, tq_password: str) -> dict:
    """
    运行单个品种的回测
    
    Args:
        symbol: 合约代码
        config: 回测配置
        tq_account: 快期账号
        tq_password: 快期密码
    
    Returns:
        dict: 回测结果
    """
    start_date = datetime.strptime(config["start_date"], "%Y-%m-%d").date()
    end_date = datetime.strptime(config["end_date"], "%Y-%m-%d").date()
    n_period = config.get("n_period", 20)
    k_times = config.get("k_times", 2.0)
    kline_dur = config.get("kline_dur", 3600)
    volume = config.get("volume", 1)
    min_band_width = config.get("min_band_width", 0.01)
    initial_balance = config.get("initial_balance", 1000000)
    margin_ratio = config.get("margin_ratio", 0.1)

    logger = setup_logger(f"tqsim_{symbol.split('@')[-1].split('.')[0]}")

    print(f"\n{'='*60}")
    print(f"回测: {symbol}")
    print(f"{'='*60}")
    print(f"回测区间: {start_date} ~ {end_date}")
    print(f"初始资金: {initial_balance:,.0f}元")
    if margin_ratio is not None:
        print(f"仓位模式: 动态（总资产×{margin_ratio:.0%}保证金）")
    else:
        print(f"仓位模式: 固定（{volume}手）")
    print(f"周期: MA{n_period} | 倍数: {k_times} | 最小带宽: {min_band_width}")

    api = None
    strategy = None
    account_summary = None

    try:
        api = TqApi(
            account=TqSim(init_balance=initial_balance),
            backtest=TqBacktest(start_dt=start_date, end_dt=end_date),
            auth=TqAuth(tq_account, tq_password),
            web_gui=False,  # 多品种回测关闭 Web GUI
        )

        strategy = BollBreakoutStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            n_period=n_period,
            k_times=k_times,
            kline_dur=kline_dur,
            volume=volume,
            min_band_width=min_band_width,
            use_continuous=config.get("use_continuous_contract", True),
            initial_balance=initial_balance,
            margin_ratio=margin_ratio,
        )

        strategy.run()

    except Exception as e:
        if "回测结束" in str(e):
            print("[回测正常结束]")
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

    print(f"\n回测结果: {symbol}")
    print(f"初始资金:   {init_bal:>15,.2f} 元")
    print(f"期末资金:   {final_bal:>15,.2f} 元")
    print(f"净利润:     {profit:>+15,.2f} 元")
    print(f"收益率:     {ret_rate:>+14.4f}%")
    print(f"平仓盈亏:   {account_summary.get('close_profit', 0):>+15,.2f}")
    print(f"手续费:     {account_summary.get('commission', 0):>15,.2f}")
    print(f"{'='*60}\n")

    return {
        "symbol": symbol,
        "initial_balance": init_bal,
        "final_balance": final_bal,
        "profit": profit,
        "return_rate": ret_rate,
        "close_profit": account_summary.get('close_profit', 0),
        "commission": account_summary.get('commission', 0),
    }


def save_results(results: list, csv_file: str):
    """
    保存回测结果到 CSV 文件
    
    Args:
        results: 回测结果列表
        csv_file: CSV 文件路径
    """
    if not results:
        return

    # 确保目录存在
    os.makedirs(os.path.dirname(csv_file), exist_ok=True)

    # 写入 CSV 文件
    with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
        # 写入表头
        f.write("symbol,initial_balance,final_balance,profit,return_rate,close_profit,commission\n")
        # 写入数据
        for result in results:
            f.write(
                f"{result['symbol']},{result['initial_balance']},{result['final_balance']},{result['profit']},{result['return_rate']},{result['close_profit']},{result['commission']}\n"
            )

    print(f"[保存结果] 已保存到: {csv_file}")


def main():
    print("=" * 60)
    print("布林带突破策略 - 多品种回测入口")
    print("=" * 60)

    # 加载账号信息
    account_config = load_userinfo(ACCOUNT_CONFIG_FILE)
    tqsim_cfg = account_config.get("tqsim", {})
    tq_account = tqsim_cfg.get("tq_username", "")
    tq_password = tqsim_cfg.get("tq_password", "")

    if not tq_account or not tq_password:
        raise ValueError("tq_account_config.json 缺少 tqsim.tq_username 或 tqsim.tq_password")

    # 加载回测配置
    config = load_config(CONFIG_FILE)

    # 解析命令行参数
    args = sys.argv[1:]
    run_all = "--all" in args
    target_symbol = None

    for i, arg in enumerate(args):
        if arg == "--symbol" and i + 1 < len(args):
            target_symbol = args[i + 1]

    # 确定要回测的品种列表
    if run_all:
        symbols = config.get("symbols", [])
        if not symbols:
            raise ValueError("配置文件中未指定 symbols 列表")
    elif target_symbol:
        symbols = [target_symbol]
    else:
        # 默认回测第一个品种
        symbols = config.get("symbols", [])[:1]
        if not symbols:
            raise ValueError("配置文件中未指定 symbols 列表")

    print(f"[回测计划] 共 {len(symbols)} 个品种")
    for symbol in symbols:
        print(f"  - {symbol}")
    print()

    # 运行回测
    results = []
    for symbol in symbols:
        try:
            result = run_single_backtest(symbol, config, tq_account, tq_password)
            results.append(result)
        except Exception as e:
            print(f"[回测失败] {symbol}: {e}")
            continue

    # 保存结果
    if results:
        save_results(results, CSV_FILE)
        
        # 生成报告
        print("[生成报告] 正在生成回测分析报告...")
        try:
            import backtest_generate_report
            backtest_generate_report.main()
        except Exception as e:
            print(f"[生成报告失败] {e}")
    else:
        print("[回测失败] 没有成功的回测结果")

    print(f"\n{'='*60}")
    print("多品种回测完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
