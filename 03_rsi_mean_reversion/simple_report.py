#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版报告生成器
"""

import json
import os
import csv
import sys
from datetime import datetime

# 配置
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_config.json")
RESULT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_result.csv")
REPORT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_report.html")

def load_config(config_file: str) -> dict:
    """加载回测配置"""
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)

def load_results(csv_file: str) -> list:
    """加载回测结果"""
    results = []
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 转换数值类型
                row["initial_balance"] = float(row["initial_balance"])
                row["final_balance"] = float(row["final_balance"])
                row["profit"] = float(row["profit"])
                row["return_rate"] = float(row["return_rate"])
                row["close_profit"] = float(row["close_profit"])
                row["commission"] = float(row["commission"])
                results.append(row)
    except FileNotFoundError:
        print(f"[错误] 回测结果文件不存在: {csv_file}")
        sys.exit(1)
    return results

def generate_html_report(config: dict, results: list) -> str:
    """生成 HTML 报告"""
    # 计算统计数据
    total_profit = sum(r["profit"] for r in results)
    total_initial = sum(r["initial_balance"] for r in results)
    total_return = (total_profit / total_initial * 100) if total_initial > 0 else 0

    positive_count = sum(1 for r in results if r["profit"] > 0)
    negative_count = sum(1 for r in results if r["profit"] < 0)
    zero_count = sum(1 for r in results if r["profit"] == 0)

    # 按收益率排序
    sorted_results = sorted(results, key=lambda x: x["return_rate"], reverse=True)

    # 生成 HTML
    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RSI 均值回归策略回测报告</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1, h2, h3 {
            color: #333;
        }
        .summary {
            background-color: #f0f8ff;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .stat-card {
            background-color: #e8f4f8;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #0066cc;
        }
        .stat-label {
            font-size: 14px;
            color: #666;
            margin-top: 5px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: right;
        }
        th {
            background-color: #f2f2f2;
            text-align: center;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        .profit-positive {
            color: green;
        }
        .profit-negative {
            color: red;
        }
        .top-performers {
            margin-top: 30px;
        }
        .footer {
            margin-top: 40px;
            text-align: center;
            color: #666;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>RSI 均值回归策略回测报告</h1>
        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="summary">
            <h2>策略信息</h2>
            <p><strong>策略类型:</strong> RSI 均值回归策略</p>
            <p><strong>回测区间:</strong> {config['start_date']} ~ {config['end_date']}</p>
            <p><strong>初始资金:</strong> {config['initial_balance']:,.0f} 元</p>
            <p><strong>RSI周期:</strong> {config['rsi_period']}</p>
            <p><strong>超买阈值:</strong> {config['overbought']}</p>
            <p><strong>超卖阈值:</strong> {config['oversold']}</p>
            <p><strong>K线周期:</strong> {config['kline_dur']} 秒</p>
        </div>

        <h2>回测汇总</h2>
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{len(results)}</div>
                <div class="stat-label">总品种数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{positive_count}</div>
                <div class="stat-label">盈利品种</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{negative_count}</div>
                <div class="stat-label">亏损品种</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{zero_count}</div>
                <div class="stat-label">盈亏平衡</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_profit:+.2f}</div>
                <div class="stat-label">总净利润(元)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_return:+.2f}%</div>
                <div class="stat-label">总收益率</div>
            </div>
        </div>

        <h2>回测结果详情</h2>
        <table>
            <tr>
                <th>合约</th>
                <th>初始资金(元)</th>
                <th>期末资金(元)</th>
                <th>净利润(元)</th>
                <th>收益率(%)</th>
                <th>平仓盈亏(元)</th>
                <th>手续费(元)</th>
            </tr>
        """

    # 添加表格数据
    for r in sorted_results:
        profit_class = "profit-positive" if r["profit"] >= 0 else "profit-negative"
        html += f"""
            <tr>
                <td style="text-align: left;">{r['symbol']}</td>
                <td>{r['initial_balance']:,.2f}</td>
                <td>{r['final_balance']:,.2f}</td>
                <td class="{profit_class}">{r['profit']:,.2f}</td>
                <td class="{profit_class}">{r['return_rate']:,.2f}%</td>
                <td>{r['close_profit']:,.2f}</td>
                <td>{r['commission']:,.2f}</td>
            </tr>
        """

    html += f"""
        </table>

        <div class="top-performers">
            <h3>Top 5 收益率</h3>
            <table>
                <tr>
                    <th>排名</th>
                    <th>合约</th>
                    <th>收益率(%)</th>
                    <th>净利润(元)</th>
                </tr>
        """

    # 添加 Top 5
    for i, r in enumerate(sorted_results[:5]):
        html += f"""
                <tr>
                    <td>{i+1}</td>
                    <td style="text-align: left;">{r['symbol']}</td>
                    <td class="profit-positive">{r['return_rate']:,.2f}%</td>
                    <td class="profit-positive">{r['profit']:,.2f}</td>
                </tr>
        """

    html += f"""
            </table>

            <h3>Bottom 5 收益率</h3>
            <table>
                <tr>
                    <th>排名</th>
                    <th>合约</th>
                    <th>收益率(%)</th>
                    <th>净利润(元)</th>
                </tr>
        """

    # 添加 Bottom 5
    for i, r in enumerate(sorted_results[-5:]):
        profit_class = "profit-positive" if r["profit"] >= 0 else "profit-negative"
        html += f"""
                <tr>
                    <td>{i+1}</td>
                    <td style="text-align: left;">{r['symbol']}</td>
                    <td class="{profit_class}">{r['return_rate']:,.2f}%</td>
                    <td class="{profit_class}">{r['profit']:,.2f}</td>
                </tr>
        """

    html += f"""
            </table>
        </div>

        <div class="footer">
            <p>报告由 RSI 均值回归策略回测系统自动生成</p>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>
        """

    return html

def save_report(html: str, output_file: str):
    """保存 HTML 报告"""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[报告生成] 回测报告已保存到: {output_file}")

def main():
    print("=" * 60)
    print("RSI 均值回归策略 - 回测报告生成器")
    print("=" * 60)

    try:
        # 加载配置和结果
        config = load_config(CONFIG_FILE)
        results = load_results(RESULT_CSV)

        if not results:
            print("[错误] 回测结果为空")
            sys.exit(1)

        # 生成报告
        html = generate_html_report(config, results)

        # 保存报告
        save_report(html, REPORT_HTML)

        print("[完成] 回测报告生成成功")
        print(f"[完成] 请在浏览器中打开: {REPORT_HTML}")

    except Exception as e:
        print(f"[错误] 生成报告失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()