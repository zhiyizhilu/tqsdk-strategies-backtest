#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSI 均值回归策略 - 实盘交易入口
=================================

使用实盘账户进行交易，策略参数在文件头部直接配置。

运行方式：
    python live.py

注意：
    - 实盘交易有风险，请谨慎使用
    - 请确保已在 tq_account_config.json 中配置了实盘账户信息
"""

import json
import os
import sys
from datetime import datetime
from tqsdk import TqApi, TqAuth, TqAccount

# 将上级目录添加到系统路径，以便导入 logger_config 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger
from strategy import RSIMeanReversionStrategy


# ===================== 实盘配置 =====================
# 策略参数
SYMBOL = "KQ.m@CZCE.MA"          # 交易合约：连续主力合约
RSI_PERIOD = 14                  # RSI计算周期：14根K线
OVERBOUGHT = 70                  # 超买阈值
OVERSOLD = 30                    # 超卖阈值
KLINE_DUR = 60 * 15              # K线周期：900秒 = 15分钟K线
VOLUME = 1                       # 固定持仓手数（如需动态仓位设为 None）
INITIAL_BALANCE = 1000000        # 初始资金（元），用于动态仓位计算
MARGIN_RATIO = 0.1               # 保证金比例（None=固定手数，0.1=总资产10%）

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


def run_live_trading(symbol: str, broker_id: str, account_id: str, password: str):
    """
    运行实盘交易
    
    Args:
        symbol: 合约代码
        broker_id: 期货公司代码
        account_id: 期货账号
        password: 期货账号密码
    """
    rsi_period = RSI_PERIOD
    overbought = OVERBOUGHT
    oversold = OVERSOLD
    kline_dur = KLINE_DUR
    volume = VOLUME
    initial_balance = INITIAL_BALANCE
    margin_ratio = MARGIN_RATIO

    logger = setup_logger(f"live_{symbol.split('@')[-1].split('.')[0]}")

    print(f"\n{'='*60}")
    print(f"实盘交易 | {symbol}")
    print(f"{'='*60}")
    print(f"账号: {broker_id}/{account_id}")
    print(f"RSI周期: {rsi_period} | 超买: {overbought} | 超卖: {oversold}")
    print(f"K线周期: {kline_dur}秒")
    if margin_ratio is not None:
        print(f"仓位模式: 动态（总资产×{margin_ratio:.0%}保证金）")
    else:
        print(f"仓位模式: 固定（{volume}手）")
    print("="*60)
    print("[风险提示] 实盘交易有风险，请谨慎使用！")
    print("[风险提示] 策略可能会产生连续亏损，请确保了解策略逻辑。")
    print("="*60)

    api = None
    strategy = None

    try:
        # 创建实盘API实例
        api = TqApi(
            account=TqAccount(broker_id, account_id, password),
            auth=TqAuth(account_id, password),
        )

        print(f"[OK] API 初始化成功，已连接到实盘账户")
        print(f"[OK] 开始运行 RSI 均值回归策略...")

        # 创建策略实例
        strategy = RSIMeanReversionStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            rsi_period=rsi_period,
            overbought=overbought,
            oversold=oversold,
            kline_dur=kline_dur,
            volume=volume,
            use_continuous=True,
            initial_balance=initial_balance,
            margin_ratio=margin_ratio,
        )

        # 运行策略
        strategy.run()

    except KeyboardInterrupt:
        print("\n[用户中断] 交易已停止")
    except Exception as e:
        print(f"[交易异常] {e}")
    finally:
        if api:
            try:
                # 获取最终账户信息
                acc = api.get_account()
                if acc:
                    print(f"\n{'='*60}")
                    print(f"最终账户信息")
                    print(f"{'='*60}")
                    print(f"账户权益: {acc.balance:.2f} 元")
                    print(f"可用资金: {acc.available:.2f} 元")
                    print(f"浮动盈亏: {acc.float_profit:.2f} 元")
                    print(f"持仓盈亏: {acc.position_profit:.2f} 元")
                    print(f"平仓盈亏: {acc.close_profit:.2f} 元")
                    print(f"保证金: {acc.margin:.2f} 元")
                    print(f"手续费: {acc.commission:.2f} 元")
                    print(f"{'='*60}")
            except Exception as e:
                print(f"[获取账户信息失败] {e}")
            finally:
                try:
                    api.close()
                    print("[OK] API 已关闭")
                except Exception:
                    pass


def main():
    print("=" * 60)
    print("RSI 均值回归策略 - 实盘交易入口")
    print("=" * 60)

    account_config = load_userinfo(ACCOUNT_CONFIG_FILE)
    live_cfg = account_config.get("live", {})
    broker_id = live_cfg.get("broker_id", "")
    account_id = live_cfg.get("account_id", "")
    password = live_cfg.get("password", "")

    if not broker_id or not account_id or not password:
        raise ValueError("tq_account_config.json 缺少 live.broker_id、live.account_id 或 live.password")

    run_live_trading(SYMBOL, broker_id, account_id, password)


if __name__ == "__main__":
    main()
