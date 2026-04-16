#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多品种回测脚本
================

功能：
    - 循环测试多个品种的MACD趋势策略
    - 汇总各品种的收益情况
    - 将结果导出到CSV文件

使用方法：
    1. 确保已配置 backtest_config.json 文件
    2. 确保已配置 tq_account_config.json 文件
    3. 运行：python tqsim_multi_symbol.py
    4. 可选：运行特定品种：python tqsim_multi_symbol.py --symbol KQ.m@SHFE.cu
"""

import json
import os
import sys
import csv
import asyncio
import argparse
from datetime import datetime
from tqsdk import TqApi, TqAuth, TqBacktest, TqSim

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger


ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)

BACKTEST_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "backtest_config.json"
)


class SimpleLogger:
    """简单的日志记录器"""
    def info(self, message):
        print(message)


def load_userinfo(filepath: str) -> dict:
    """从 JSON 文件加载账号信息"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[账号信息] 已从文件加载: {filepath}")
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"账号信息文件不存在: {filepath}")
    except json.JSONDecodeError as e:
        raise ValueError(f"账号信息文件格式错误: {e}")


def load_backtest_config(filepath: str) -> dict:
    """从 JSON 文件加载回测配置"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[回测配置] 已从文件加载: {filepath}")
        return data
    except FileNotFoundError:
        raise FileNotFoundError(f"回测配置文件不存在: {filepath}")
    except json.JSONDecodeError as e:
        raise ValueError(f"回测配置文件格式错误: {e}")


def run_backtest(symbol: str, config: dict, tq_account: str, tq_password: str) -> dict:
    """
    运行单个品种的回测

    Args:
        symbol: 合约代码
        config: 回测配置字典
        tq_account: 快期账号
        tq_password: 快期密码

    Returns:
        dict: 回测结果字典
    """
    from strategy import MACDTrendStrategy

    start_date = datetime.strptime(config.get("start_date", "2024-01-01"), "%Y-%m-%d").date()
    end_date = datetime.strptime(config.get("end_date", "2024-12-31"), "%Y-%m-%d").date()
    fast_period = config.get("fast_period", 12)
    slow_period = config.get("slow_period", 26)
    signal_period = config.get("signal_period", 9)
    kline_dur = config.get("kline_dur", 3600)
    volume = config.get("volume", 1)
    use_continuous = config.get("use_continuous_contract", True)
    initial_balance = config.get("initial_balance", 10000000)
    margin_ratio = config.get("margin_ratio", None)

    print(f"\n{'='*60}")
    print(f"开始回测品种: {symbol}")
    print(f"{'='*60}")
    print(f"回测区间: {start_date} ~ {end_date}")
    print(f"快线EMA: {fast_period} | 慢线EMA: {slow_period} | 信号线: {signal_period}")
    print(f"K线周期: {kline_dur}秒 | 初始资金: {initial_balance:,.0f}元")
    if margin_ratio is not None:
        print(f"仓位模式: 动态（总资产×{margin_ratio:.0%}保证金）")
    else:
        print(f"仓位模式: 固定（{volume}手）")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    api = None
    strategy = None
    account_summary = None

    try:
        api = TqApi(
            account=TqSim(init_balance=initial_balance),
            backtest=TqBacktest(start_dt=start_date, end_dt=end_date),
            auth=TqAuth(tq_account, tq_password),
        )

        logger = SimpleLogger()

        strategy = MACDTrendStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            fast_period=fast_period,
            slow_period=slow_period,
            signal_period=signal_period,
            kline_dur=kline_dur,
            volume=volume,
            use_continuous=use_continuous,
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
                    account_snapshot = strategy.get_account_snapshot()
                    if account_snapshot:
                        account_summary = account_snapshot
                        print("[使用策略运行中的账户快照]")
                    else:
                        account = api.get_account()
                        account_summary = {
                            "static_balance": account.static_balance,
                            "balance": account.balance,
                            "available": account.available,
                            "float_profit": account.float_profit,
                            "position_profit": account.position_profit,
                            "close_profit": account.close_profit,
                            "margin": account.margin,
                            "commission": account.commission,
                        }
                else:
                    account = api.get_account()
                    account_summary = {
                        "static_balance": account.static_balance,
                        "balance": account.balance,
                        "available": account.available,
                        "float_profit": account.float_profit,
                        "position_profit": account.position_profit,
                        "close_profit": account.close_profit,
                        "margin": account.margin,
                        "commission": account.commission,
                    }
            except Exception as e:
                print(f"[获取账户信息失败] {e}")
                account_summary = {
                    "static_balance": 10000000.0,
                    "balance": 10000000.0,
                    "available": 10000000.0,
                    "float_profit": 0.0,
                    "position_profit": 0.0,
                    "close_profit": 0.0,
                    "margin": 0.0,
                    "commission": 0.0,
                }
            finally:
                try:
                    api.close()
                except Exception as e:
                    print(f"[关闭API失败] {e}")

        if not account_summary:
            account_summary = {
                "static_balance": 10000000.0,
                "balance": 10000000.0,
                "available": 10000000.0,
                "float_profit": 0.0,
                "position_profit": 0.0,
                "close_profit": 0.0,
                "margin": 0.0,
                "commission": 0.0,
            }

    initial_balance = account_summary['static_balance']
    final_balance = account_summary['balance']
    profit = final_balance - initial_balance
    return_rate = (profit / initial_balance) * 100 if initial_balance > 0 else 0

    print(f"\n{'='*60}")
    print("回测结果")
    print(f"{'='*60}")
    print(f"初始资金: {initial_balance:.2f}")
    print(f"期末资金: {final_balance:.2f}")
    print(f"净利润: {profit:.2f}")
    print(f"收益率: {return_rate:.2f}%")
    print(f"平仓盈亏: {account_summary.get('close_profit', 0):.2f}")
    print(f"手续费: {account_summary.get('commission', 0):.2f}")
    print(f"{'='*60}")

    return {
        'symbol': symbol,
        'initial_balance': initial_balance,
        'final_balance': final_balance,
        'profit': profit,
        'return_rate': return_rate,
        'close_profit': account_summary.get('close_profit', 0),
        'commission': account_summary.get('commission', 0),
    }


def save_results_to_csv(results: list, output_file: str):
    """保存回测结果到 CSV 文件"""
    if not results:
        print("没有结果需要保存")
        return

    fieldnames = ['symbol', 'initial_balance', 'final_balance', 'profit', 'return_rate', 'close_profit', 'commission']

    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[结果保存] 已保存到: {output_file}")


def print_summary(results: list):
    """打印回测结果汇总"""
    if not results:
        print("没有结果需要汇总")
        return

    print("\n" + "="*80)
    print("多品种回测结果汇总")
    print("="*80)

    sorted_results = sorted(results, key=lambda x: x['return_rate'], reverse=True)

    print(f"{'排名':<6}{'品种':<20}{'初始资金':<15}{'期末资金':<15}{'净利润':<15}{'收益率':<10}")
    print("-"*80)

    for i, result in enumerate(sorted_results, 1):
        symbol = result['symbol']
        initial = result['initial_balance']
        final = result['final_balance']
        profit = result['profit']
        return_rate = result['return_rate']

        print(f"{i:<6}{symbol:<20}{initial:<15.2f}{final:<15.2f}{profit:<15.2f}{return_rate:<10.2f}%")

    print("-"*80)

    profits = [r['profit'] for r in results]
    returns = [r['return_rate'] for r in results]

    winning_trades = len([p for p in profits if p > 0])
    losing_trades = len([p for p in profits if p < 0])
    break_even = len([p for p in profits if p == 0])

    print(f"\n统计信息:")
    print(f"  测试品种总数: {len(results)}")
    print(f"  盈利品种: {winning_trades} ({winning_trades/len(results)*100:.1f}%)")
    print(f"  亏损品种: {losing_trades} ({losing_trades/len(results)*100:.1f}%)")
    print(f"  持平品种: {break_even} ({break_even/len(results)*100:.1f}%)")
    print(f"\n  最高收益率: {max(returns):.2f}% ({sorted_results[0]['symbol']})")
    print(f"  最低收益率: {min(returns):.2f}% ({sorted_results[-1]['symbol']})")
    print(f"  平均收益率: {sum(returns)/len(returns):.2f}%")
    print(f"  总净利润: {sum(profits):.2f}")
    print("="*80)


def main():
    """多品种回测主函数"""
    parser = argparse.ArgumentParser(description='MACD趋势策略多品种回测')
    parser.add_argument('--symbol', type=str, help='指定测试的品种代码，如 KQ.m@SHFE.cu')
    parser.add_argument('--all', action='store_true', help='测试所有品种')
    args = parser.parse_args()

    print("="*60)
    print("MACD趋势策略 - 多品种回测")
    print("="*60)

    account_config = load_userinfo(ACCOUNT_CONFIG_FILE)
    tqsim_config = account_config.get("tqsim", {})
    tq_account = tqsim_config.get("tq_username", "")
    tq_password = tqsim_config.get("tq_password", "")

    if not tq_account or not tq_password:
        raise ValueError("tq_account_config.json 缺少 tqsim.tq_username 或 tqsim.tq_password 字段")

    backtest_config = load_backtest_config(BACKTEST_CONFIG_FILE)
    all_symbols = backtest_config.get('symbols', [])
    output_csv = backtest_config.get('output_csv', 'backtest_result.csv')

    if not all_symbols:
        raise ValueError("backtest_config.json 中没有配置品种列表 (symbols)")

    if args.symbol:
        if args.symbol in all_symbols:
            symbols = [args.symbol]
            print(f"\n将测试 1 个指定品种: {args.symbol}")
        else:
            print(f"错误: 品种 {args.symbol} 不在配置列表中")
            return
    elif args.all:
        symbols = all_symbols
        print(f"\n将测试 {len(symbols)} 个品种")
    else:
        symbols = [all_symbols[0]]
        print(f"\n默认测试第一个品种: {symbols[0]}")
        print("提示: 使用 --all 测试所有品种，或使用 --symbol 指定品种")

    print(f"结果将保存到: {output_csv}")

    results = []

    for i, symbol in enumerate(symbols, 1):
        print(f"\n\n[{i}/{len(symbols)}] ", end="")
        try:
            result = run_backtest(symbol, backtest_config, tq_account, tq_password)
            results.append(result)
        except Exception as e:
            print(f"[错误] 品种 {symbol} 回测失败: {e}")
            results.append({
                'symbol': symbol,
                'initial_balance': 0,
                'final_balance': 0,
                'profit': 0,
                'return_rate': 0,
                'close_profit': 0,
                'commission': 0,
            })

    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_csv)
    save_results_to_csv(results, output_file)

    print_summary(results)

    print("\n" + "="*60)
    print("多品种回测完成")
    print("="*60)


if __name__ == "__main__":
    main()
