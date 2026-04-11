#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多品种回测脚本
================

功能：
    - 循环测试多个品种的双均线策略
    - 汇总各品种的收益情况
    - 将结果导出到CSV文件

使用方法：
    1. 确保已配置 backtest_config.json 文件
    2. 确保已配置 tq_account_config.json 文件
    3. 运行：python multi_symbol_backtest.py
    4. 可选：运行特定品种：python multi_symbol_backtest.py --symbol KQ.m@SHFE.rb
"""

import json
import os
import sys
import csv
import asyncio
import argparse
from datetime import datetime
from tqsdk import TqApi, TqAuth, TqBacktest, TqSim

# 将上级目录添加到系统路径，以便导入 logger_config 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger


# ===================== 配置文件路径 =====================
# 账号信息文件路径（相对于当前文件的上级目录）
ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)

# 回测参数配置文件路径（当前目录）
BACKTEST_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "backtest_config.json"
)
# ===================================================


class SimpleLogger:
    """
    简单的日志记录器
    
    用于在子进程回测中替代标准logger，避免多进程间的日志冲突
    直接打印信息到标准输出
    """
    def info(self, message):
        """打印信息"""
        print(message)


def load_userinfo(filepath: str) -> dict:
    """
    从 JSON 文件加载账号信息
    
    读取并解析存储在JSON文件中的回测账户信息，包括快期账号和密码

    Args:
        filepath: JSON 文件路径

    Returns:
        dict: 账号信息字典，包含 tq_username、tq_password 等字段
    """
    try:
        # 以UTF-8编码打开并读取JSON文件
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[账号信息] 已从文件加载: {filepath}")
        return data
    except FileNotFoundError:
        # 文件不存在时抛出异常
        raise FileNotFoundError(f"账号信息文件不存在: {filepath}")
    except json.JSONDecodeError as e:
        # JSON格式错误时抛出异常
        raise ValueError(f"账号信息文件格式错误: {e}")


def load_backtest_config(filepath: str) -> dict:
    """
    从 JSON 文件加载回测配置
    
    读取并解析存储在JSON文件中的多品种回测参数配置，包括回测区间、品种列表、策略参数等

    Args:
        filepath: JSON 文件路径

    Returns:
        dict: 回测配置字典，包含 start_date、end_date、symbols 等字段
    """
    try:
        # 以UTF-8编码打开并读取JSON文件
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[回测配置] 已从文件加载: {filepath}")
        return data
    except FileNotFoundError:
        # 文件不存在时抛出异常
        raise FileNotFoundError(f"回测配置文件不存在: {filepath}")
    except json.JSONDecodeError as e:
        # JSON格式错误时抛出异常
        raise ValueError(f"回测配置文件格式错误: {e}")


def run_backtest(symbol: str, config: dict, tq_account: str, tq_password: str) -> dict:
    """
    运行单个品种的回测
    
    为指定品种创建独立的TqApi实例和策略实例，运行完整的回测流程并返回结果

    Args:
        symbol: 合约代码
        config: 回测配置字典
        tq_account: 快期账号
        tq_password: 快期密码

    Returns:
        dict: 回测结果字典，包含品种代码、初始资金、期末资金、净利润、收益率等字段
    """
    from strategy import DoubleMAStrategy

    # 解析回测配置参数
    start_date = datetime.strptime(config.get("start_date", "2024-01-01"), "%Y-%m-%d").date()
    end_date = datetime.strptime(config.get("end_date", "2024-12-31"), "%Y-%m-%d").date()
    short_period = config.get("short_period", 5)  # 短期均线周期
    long_period = config.get("long_period", 20)  # 长期均线周期
    kline_dur = config.get("kline_dur", 3600)  # K线周期（秒）
    volume = config.get("volume", 1)  # 持仓手数（动态仓位模式下作为保底参考）
    use_continuous = config.get("use_continuous_contract", True)  # 是否使用连续主力合约
    initial_balance = config.get("initial_balance", 10000000)  # 初始资金（默认1000万）
    margin_ratio = config.get("margin_ratio", None)  # 保证金比例（None=固定手数）

    # 打印回测开始信息
    print(f"\n{'='*60}")
    print(f"开始回测品种: {symbol}")
    print(f"{'='*60}")
    print(f"回测区间: {start_date} ~ {end_date}")
    print(f"短周期: {short_period} | 长周期: {long_period}")
    print(f"K线周期: {kline_dur}秒 | 初始资金: {initial_balance:,.0f}元")
    if margin_ratio is not None:
        print(f"仓位模式: 动态（总资产×{margin_ratio:.0%}保证金）")
    else:
        print(f"仓位模式: 固定（{volume}手）")

    # 处理事件循环（兼容 Python 3.10+，避免 DeprecationWarning）
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 初始化变量
    api = None
    strategy = None
    account_summary = None

    try:
        # 创建TqApi实例，连接模拟账户进行回测
        api = TqApi(
            account=TqSim(init_balance=initial_balance),  # 使用模拟账户，设置初始资金
            backtest=TqBacktest(start_dt=start_date, end_dt=end_date),  # 设置回测时间范围
            auth=TqAuth(tq_account, tq_password),  # 认证信息
        )

        # 使用简单的日志记录器
        logger = SimpleLogger()

        # 创建双均线策略实例
        strategy = DoubleMAStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            short_period=short_period,
            long_period=long_period,
            kline_dur=kline_dur,
            volume=volume,
            use_continuous=use_continuous,
            initial_balance=initial_balance,
            margin_ratio=margin_ratio,
        )

        # 运行策略主循环
        strategy.run()

    except Exception as e:
        # 判断是否为回测正常结束异常
        if "回测结束" in str(e):
            print("[回测正常结束]")
        else:
            print(f"[回测异常] {e}")
    finally:
        if api:
            try:
                # 优先使用策略运行过程中保存的账户快照
                if strategy:
                    account_snapshot = strategy.get_account_snapshot()
                    if account_snapshot:
                        account_summary = account_snapshot
                        print("[使用策略运行中的账户快照]")
                    else:
                        # 如果策略没有保存快照，则尝试从API获取
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
                    # 策略初始化失败，尝试直接从API获取账户信息
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
                # 使用默认值作为后备
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
                    api.close()  # 关闭API连接
                except Exception as e:
                    print(f"[关闭API失败] {e}")

        # 确保账户信息已设置（防止异常情况下未获取到账户信息）
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

    # 计算收益率
    initial_balance = account_summary['static_balance']  # 初始资金
    final_balance = account_summary['balance']  # 期末资金
    profit = final_balance - initial_balance  # 净利润
    return_rate = (profit / initial_balance) * 100 if initial_balance > 0 else 0  # 收益率（百分比）

    # 打印回测结果
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

    # 返回回测结果字典
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
    """
    保存回测结果到 CSV 文件
    
    将多品种回测的结果列表写入CSV文件，每行包含一个品种的回测结果

    Args:
        results: 回测结果列表，每个元素是一个包含品种回测结果的字典
        output_file: 输出文件路径
    """
    # 检查是否有结果需要保存
    if not results:
        print("没有结果需要保存")
        return

    # 定义CSV文件的列名
    fieldnames = ['symbol', 'initial_balance', 'final_balance', 'profit', 'return_rate', 'close_profit', 'commission']

    # 以写入模式打开CSV文件
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        # 写入表头
        writer.writeheader()
        # 批量写入数据行
        writer.writerows(results)

    print(f"\n[结果保存] 已保存到: {output_file}")


def print_summary(results: list):
    """
    打印回测结果汇总
    
    将多品种回测结果以表格形式打印到控制台，并输出统计信息

    Args:
        results: 回测结果列表，每个元素是一个包含品种回测结果的字典
    """
    # 检查是否有结果需要汇总
    if not results:
        print("没有结果需要汇总")
        return

    # 打印汇总标题
    print("\n" + "="*80)
    print("多品种回测结果汇总")
    print("="*80)

    # 按收益率从高到低排序
    sorted_results = sorted(results, key=lambda x: x['return_rate'], reverse=True)

    # 打印表头
    print(f"{'排名':<6}{'品种':<20}{'初始资金':<15}{'期末资金':<15}{'净利润':<15}{'收益率':<10}")
    print("-"*80)

    # 遍历并打印每个品种的结果
    for i, result in enumerate(sorted_results, 1):
        symbol = result['symbol']
        initial = result['initial_balance']
        final = result['final_balance']
        profit = result['profit']
        return_rate = result['return_rate']

        print(f"{i:<6}{symbol:<20}{initial:<15.2f}{final:<15.2f}{profit:<15.2f}{return_rate:<10.2f}%")

    print("-"*80)

    # 提取所有品种的盈亏和收益率数据
    profits = [r['profit'] for r in results]
    returns = [r['return_rate'] for r in results]

    # 统计盈利、亏损和持平品种数量
    winning_trades = len([p for p in profits if p > 0])
    losing_trades = len([p for p in profits if p < 0])
    break_even = len([p for p in profits if p == 0])

    # 打印统计信息
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
    """
    多品种回测主函数
    
    多品种回测的主要入口函数，负责：
    1. 解析命令行参数
    2. 加载账户配置和回测配置
    3. 确定要测试的品种列表
    4. 循环运行各品种的回测
    5. 保存结果到CSV文件并打印汇总信息
    """
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='双均线策略多品种回测')
    # 添加命令行参数：指定测试品种
    parser.add_argument('--symbol', type=str, help='指定测试的品种代码，如 KQ.m@SHFE.rb')
    # 添加命令行参数：测试所有品种
    parser.add_argument('--all', action='store_true', help='测试所有品种')
    # 解析命令行参数
    args = parser.parse_args()

    # 打印程序标题
    print("="*60)
    print("双均线策略 - 多品种回测")
    print("="*60)

    # 加载账号配置
    account_config = load_userinfo(ACCOUNT_CONFIG_FILE)
    # 获取模拟账户配置
    tqsim_config = account_config.get("tqsim", {})
    # 获取快期账号
    tq_account = tqsim_config.get("tq_username", "")
    # 获取快期密码
    tq_password = tqsim_config.get("tq_password", "")

    # 验证必要的配置信息是否完整
    if not tq_account or not tq_password:
        raise ValueError("tq_account_config.json 缺少 tqsim.tq_username 或 tqsim.tq_password 字段")

    # 加载回测配置
    backtest_config = load_backtest_config(BACKTEST_CONFIG_FILE)
    # 获取配置中的所有品种列表
    all_symbols = backtest_config.get('symbols', [])
    # 获取输出CSV文件名
    output_csv = backtest_config.get('output_csv', 'backtest_result.csv')

    # 验证品种列表是否配置
    if not all_symbols:
        raise ValueError("backtest_config.json 中没有配置品种列表 (symbols)")

    # 根据命令行参数确定要测试的品种
    if args.symbol:
        # 测试指定的品种
        if args.symbol in all_symbols:
            symbols = [args.symbol]  # 使用列表包装单个品种
            print(f"\n将测试 1 个指定品种: {args.symbol}")
        else:
            print(f"错误: 品种 {args.symbol} 不在配置列表中")
            return
    elif args.all:
        # 测试所有品种
        symbols = all_symbols
        print(f"\n将测试 {len(symbols)} 个品种")
    else:
        # 默认只测试第一个品种
        symbols = [all_symbols[0]]
        print(f"\n默认测试第一个品种: {symbols[0]}")
        print("提示: 使用 --all 测试所有品种，或使用 --symbol 指定品种")

    print(f"结果将保存到: {output_csv}")

    # 用于存储所有品种的回测结果
    results = []

    # 循环对每个品种进行回测
    for i, symbol in enumerate(symbols, 1):
        print(f"\n\n[{i}/{len(symbols)}] ", end="")
        try:
            # 运行单个品种的回测
            result = run_backtest(symbol, backtest_config, tq_account, tq_password)
            results.append(result)  # 将结果添加到列表
        except Exception as e:
            # 捕获异常并记录错误
            print(f"[错误] 品种 {symbol} 回测失败: {e}")
            # 记录失败的结果（各项数据为0）
            results.append({
                'symbol': symbol,
                'initial_balance': 0,
                'final_balance': 0,
                'profit': 0,
                'return_rate': 0,
                'close_profit': 0,
                'commission': 0,
            })

    # 构建输出文件完整路径
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_csv)
    # 保存结果到CSV文件
    save_results_to_csv(results, output_file)

    # 打印汇总信息
    print_summary(results)

    # 打印程序结束信息
    print("\n" + "="*60)
    print("多品种回测完成")
    print("="*60)


if __name__ == "__main__":
    main()
