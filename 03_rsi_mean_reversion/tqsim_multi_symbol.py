#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSI 均值回归策略 - 多品种批量回测入口（TqSim）
=========================================

使用 TqSim 本地模拟账户进行多品种批量历史回测，
策略参数从 backtest_config.json 读取。

运行方式：
    python tqsim_multi_symbol.py

输出：
    回测结果打印到控制台并保存到 CSV 文件
"""

import json
import os
import sys
import csv
import time
from datetime import datetime
from tqsdk import TqApi, TqAuth, TqBacktest, TqSim

# 将上级目录添加到系统路径，以便导入 logger_config 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger
from strategy import RSIMeanReversionStrategy


# ===================== 回测配置 =====================
# 配置文件路径
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_config.json")

# 账号信息文件路径
ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)
# ===================================================


class BatchBacktest:
    """批量回测类"""

    def __init__(self, config_file: str, account_config_file: str):
        """
        初始化批量回测

        Args:
            config_file: 回测配置文件路径
            account_config_file: 账号信息文件路径
        """
        # 加载回测配置
        with open(config_file, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # 加载账号信息
        with open(account_config_file, "r", encoding="utf-8") as f:
            account_config = json.load(f)

        tqsim_cfg = account_config.get("tqsim", {})
        self.tq_account = tqsim_cfg.get("tq_username", "")
        self.tq_password = tqsim_cfg.get("tq_password", "")

        if not self.tq_account or not self.tq_password:
            raise ValueError("tq_account_config.json 缺少 tqsim.tq_username 或 tqsim.tq_password")

        # 回测参数
        self.start_date = datetime.strptime(self.config["start_date"], "%Y-%m-%d").date()
        self.end_date = datetime.strptime(self.config["end_date"], "%Y-%m-%d").date()
        self.initial_balance = self.config["initial_balance"]
        self.margin_ratio = self.config["margin_ratio"]
        self.symbols = self.config["symbols"]
        self.use_continuous = self.config["use_continuous_contract"]
        self.rsi_period = self.config["rsi_period"]
        self.overbought = self.config["overbought"]
        self.oversold = self.config["oversold"]
        self.kline_dur = self.config["kline_dur"]
        self.volume = self.config["volume"]
        self.output_csv = self.config["output_csv"]

        # 回测结果
        self.results = []

    def run_single_backtest(self, symbol: str) -> dict:
        """
        运行单个品种的回测

        Args:
            symbol: 合约代码

        Returns:
            dict: 回测结果
        """
        logger = setup_logger(f"tqsim_{symbol.split('@')[-1].split('.')[0]}")

        print(f"\n{'='*60}")
        print(f"开始回测 | {symbol}")
        print(f"{'='*60}")
        print(f"回测区间: {self.start_date} ~ {self.end_date}")
        print(f"初始资金: {self.initial_balance:,.0f}元")
        if self.margin_ratio is not None:
            print(f"仓位模式: 动态（总资产×{self.margin_ratio:.0%}保证金）")
        else:
            print(f"仓位模式: 固定（{self.volume}手）")
        print(f"RSI周期: {self.rsi_period} | 超买: {self.overbought} | 超卖: {self.oversold}")

        loop = __import__("asyncio").new_event_loop()
        __import__("asyncio").set_event_loop(loop)

        api = None
        strategy = None
        account_summary = None

        try:
            api = TqApi(
                account=TqSim(init_balance=self.initial_balance),
                backtest=TqBacktest(start_dt=self.start_date, end_dt=self.end_date),
                auth=TqAuth(self.tq_account, self.tq_password),
            )

            strategy = RSIMeanReversionStrategy(
                api=api,
                logger=logger,
                symbol=symbol,
                rsi_period=self.rsi_period,
                overbought=self.overbought,
                oversold=self.oversold,
                kline_dur=self.kline_dur,
                volume=self.volume,
                use_continuous=self.use_continuous,
                initial_balance=self.initial_balance,
                margin_ratio=self.margin_ratio,
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
                        "static_balance": self.initial_balance,
                        "balance": self.initial_balance,
                        "available": self.initial_balance,
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
                "static_balance": self.initial_balance,
                "balance": self.initial_balance,
                "available": self.initial_balance,
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

        result = {
            "symbol": symbol,
            "initial_balance": init_bal,
            "final_balance": final_bal,
            "profit": profit,
            "return_rate": ret_rate,
            "close_profit": account_summary.get("close_profit", 0),
            "commission": account_summary.get("commission", 0),
        }

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

        return result

    def run_batch(self):
        """
        运行批量回测
        """
        print("=" * 60)
        print("RSI 均值回归策略 - 批量回测")
        print("=" * 60)
        print(f"回测品种数: {len(self.symbols)}")
        print(f"回测区间: {self.start_date} ~ {self.end_date}")
        print(f"初始资金: {self.initial_balance:,.0f}元")
        print(f"RSI周期: {self.rsi_period} | 超买: {self.overbought} | 超卖: {self.oversold}")
        print("=" * 60)

        # 运行每个品种的回测
        for i, symbol in enumerate(self.symbols):
            print(f"\n[{i+1}/{len(self.symbols)}] 回测: {symbol}")
            result = self.run_single_backtest(symbol)
            self.results.append(result)

            # 避免请求过于频繁
            if i < len(self.symbols) - 1:
                print("[等待] 2秒后开始下一个品种回测...")
                time.sleep(2)

        # 保存回测结果到 CSV
        self.save_results()

        # 打印回测汇总
        self.print_summary()

    def save_results(self):
        """
        保存回测结果到 CSV 文件
        """
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.output_csv)

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["symbol", "initial_balance", "final_balance", "profit", "return_rate", "close_profit", "commission"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            writer.writeheader()
            for result in self.results:
                writer.writerow(result)

        print(f"\n[保存结果] 回测结果已保存到: {output_path}")

    def print_summary(self):
        """
        打印回测汇总
        """
        if not self.results:
            print("[汇总] 无回测结果")
            return

        # 计算统计数据
        total_profit = sum(r["profit"] for r in self.results)
        total_initial = sum(r["initial_balance"] for r in self.results)
        total_return = (total_profit / total_initial * 100) if total_initial > 0 else 0

        positive_count = sum(1 for r in self.results if r["profit"] > 0)
        negative_count = sum(1 for r in self.results if r["profit"] < 0)
        zero_count = sum(1 for r in self.results if r["profit"] == 0)

        # 按收益率排序
        sorted_results = sorted(self.results, key=lambda x: x["return_rate"], reverse=True)

        print("\n" + "=" * 60)
        print("回测汇总")
        print("=" * 60)
        print(f"总品种数: {len(self.results)}")
        print(f"盈利品种: {positive_count}")
        print(f"亏损品种: {negative_count}")
        print(f"盈亏平衡: {zero_count}")
        print(f"总初始资金: {total_initial:,.2f} 元")
        print(f"总净利润: {total_profit:>+,.2f} 元")
        print(f"总收益率: {total_return:>+,.4f}%")
        print("=" * 60)

        # 打印前5和后5的品种
        print("\nTop 5 收益率")
        print("-" * 60)
        for i, r in enumerate(sorted_results[:5]):
            print(f"{i+1}. {r['symbol']}: {r['return_rate']:>+,.4f}% (利润: {r['profit']:>+,.2f})")

        print("\nBottom 5 收益率")
        print("-" * 60)
        for i, r in enumerate(sorted_results[-5:]):
            print(f"{i+1}. {r['symbol']}: {r['return_rate']:>+,.4f}% (利润: {r['profit']:>+,.2f})")

        print("=" * 60)


def main():
    try:
        batch_backtest = BatchBacktest(CONFIG_FILE, ACCOUNT_CONFIG_FILE)
        batch_backtest.run_batch()
    except Exception as e:
        print(f"[批量回测失败] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
