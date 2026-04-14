#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
布林带突破策略 - 实盘交易入口
======================================

使用实盘账户运行布林带突破策略，
策略参数在文件头部直接配置。

运行方式：
    python live.py

注意：
    - 实盘交易存在风险，请谨慎使用
    - 请确保已在 tq_account_config.json 中配置好实盘账号信息
"""

import json
import os
import sys
from tqsdk import TqApi, TqAuth

# 将上级目录添加到系统路径，以便导入 logger_config 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger
from strategy import BollBreakoutStrategy


# ===================== 策略配置 =====================
# 策略参数
SYMBOL = "KQ.m@SHFE.au"          # 交易合约：连续主力合约
N_PERIOD = 20                # 布林带计算周期：20根K线
K_TIMES = 2.0                # 标准差倍数：2.0
KLINE_DUR = 60 * 60             # K线周期：3600秒 = 1小时K线
VOLUME = 1                      # 固定持仓手数（如需动态仓位设为 None）
MIN_BAND_WIDTH = 0.01           # 最小带宽比例
INITIAL_BALANCE = 1000000       # 初始资金（元），用于动态仓位计算
MARGIN_RATIO = 0.1              # 保证金比例（None=固定手数，0.1=总资产10%）

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


def main():
    print("=" * 60)
    print("布林带突破策略 - 实盘交易入口")
    print("=" * 60)
    print("[警告] 实盘交易存在风险，请谨慎使用！")
    print("=" * 60)

    # 加载账号信息
    account_config = load_userinfo(ACCOUNT_CONFIG_FILE)
    live_cfg = account_config.get("live", {})
    tq_account = live_cfg.get("tq_username", "")
    tq_password = live_cfg.get("tq_password", "")

    if not tq_account or not tq_password:
        raise ValueError("tq_account_config.json 缺少 live.tq_username 或 live.tq_password")

    # 初始化 API
    api = None
    strategy = None

    try:
        # 使用实盘账户初始化 API
        api = TqApi(
            auth=TqAuth(tq_account, tq_password),
        )

        print(f"[OK] API 初始化成功")
        print(f"[OK] 实盘账号: {tq_account}")
        print(f"[OK] 交易合约: {SYMBOL}")

        # 创建策略实例
        strategy = BollBreakoutStrategy(
            api=api,
            logger=setup_logger("live"),
            symbol=SYMBOL,
            n_period=N_PERIOD,
            k_times=K_TIMES,
            kline_dur=KLINE_DUR,
            volume=VOLUME,
            min_band_width=MIN_BAND_WIDTH,
            use_continuous=True,
            initial_balance=INITIAL_BALANCE,
            margin_ratio=MARGIN_RATIO,
        )

        print(f"[OK] 策略初始化成功")
        print(f"[OK] 策略参数: 周期={N_PERIOD}, 倍数={K_TIMES}, 最小带宽={MIN_BAND_WIDTH}")
        print(f"[OK] 开始运行策略...")
        print(f"[提示] 按 Ctrl+C 退出策略")

        # 运行策略
        strategy.run()

    except KeyboardInterrupt:
        print("\n[用户中断] 策略已停止")
    except Exception as e:
        print(f"[运行异常] {e}")
    finally:
        if api:
            try:
                api.close()
                print("[OK] API 已关闭")
            except Exception:
                pass

    print("\n" + "=" * 60)
    print("策略运行结束")
    print("=" * 60)


if __name__ == "__main__":
    main()
