#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dual Thrust 策略 - 实盘入口
===========================

使用 TqAccount 连接实盘期货交易账户

⚠️ 警告：实盘交易将产生真实的资金盈亏，请谨慎操作！

运行方式：
    python live.py

配置说明：
    - 实盘账户信息从 tq_account_config.json 文件读取
    - 修改策略参数调整策略逻辑

支持的期货公司：
    https://www.shinnytech.com/blog/tq-support-broker/

常用期货公司代码示例：
    - H海通期货
    - H宏源期货
    - N南华期货
    - C中信期货
    - G国泰君安
"""

import json
import os
import sys
import webbrowser
from tqsdk import TqApi, TqAuth, TqAccount
from strategy import DualThrustStrategy

# 将上级目录添加到系统路径，以便导入 logger_config 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger_config import setup_logger


# ===================== 实盘配置 =====================
# 策略参数
SYMBOL = "KQ.m@SHFE.cu"         # 交易合约：连续主力合约（自动换月）
N_DAYS = 4                      # 回溯天数：4天
K1 = 0.5                        # 上轨系数
K2 = 0.5                        # 下轨系数
VOLUME = 1                      # 持仓手数

# 账号信息文件路径（相对于当前文件的上级目录）
ACCOUNT_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tq_account_config.json"
)

# ===================== Web GUI 配置 =====================
WEB_GUI_PORT = 8888  # Web GUI 端口
# =======================================================


def load_userinfo(filepath: str) -> dict:
    """
    从 JSON 文件加载账号信息

    Args:
        filepath: JSON 文件路径

    Returns:
        dict: 账号信息字典，包含 broker_id、account、password 等字段
    """
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
    """
    运行实盘策略
    
    Args:
        symbol: 合约代码
        broker_id: 期货公司代码
        account_id: 资金账号
        password: 交易密码
    """
    n_days = N_DAYS
    k1 = K1
    k2 = K2
    volume = VOLUME

    logger = setup_logger(f"live_{symbol.split('.')[-1]}")

    print(f"\n{'='*60}")
    print(f"实盘交易 | {symbol}")
    print(f"{'='*60}")
    print(f"期货公司: {broker_id}")
    print(f"资金账号: {account_id}")
    print(f"交易合约: {symbol}")
    print(f"N={n_days} | K1={k1} | K2={k2}")
    print(f"固定手数: {volume} 手")
    print("=" * 60)
    print("⚠️  警告：实盘交易将产生真实的资金盈亏！")
    print("=" * 60)

    api = None
    strategy = None
    account_summary = None

    try:
        # 创建实盘账户对象
        account = TqAccount(broker_id, account_id, password)
        print(f"[账户类型] 实盘账户 ({broker_id})")

        # 创建TqApi实例，连接实盘账户
        api = TqApi(
            account=account,
            auth=TqAuth(account_id, password),
            web_gui=f"http://0.0.0.0:{WEB_GUI_PORT}",  # 开启 Web GUI
        )

        print("[OK] API 初始化成功，Web GUI 已启动")
        print(f"[OK] 请在浏览器中打开: http://localhost:{WEB_GUI_PORT}")
        print("[提示] 策略将自动运行，可在GUI界面实时观察交易情况\n")
        webbrowser.open(f"http://localhost:{WEB_GUI_PORT}")

        # 创建 Dual Thrust 策略实例
        strategy = DualThrustStrategy(
            api=api,
            logger=logger,
            symbol=symbol,
            n_days=n_days,
            k1=k1,
            k2=k2,
            volume=volume,
        )

        # 运行策略主循环
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
    print("Dual Thrust 策略 - 实盘交易入口")
    print("=" * 60)

    # 从配置文件加载账户信息
    config = load_userinfo(ACCOUNT_CONFIG_FILE)
    # 获取实盘账户配置
    tqlive_config = config.get("tqlive", {})
    # 获取期货公司代码
    broker_id = tqlive_config.get("broker_id", "")
    # 获取资金账号
    account_id = tqlive_config.get("account", "")
    # 获取交易密码
    password = tqlive_config.get("password", "")

    # 验证必要的配置信息是否完整
    if not broker_id or not account_id or not password:
        raise ValueError("tq_account_config.json 缺少 tqlive.broker_id、tqlive.account 或 tqlive.password 字段")

    run_strategy(SYMBOL, broker_id, account_id, password)


if __name__ == "__main__":
    main()
