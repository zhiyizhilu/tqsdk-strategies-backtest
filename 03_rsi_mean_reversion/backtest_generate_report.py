#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSI 均值回归策略 - 回测报告生成器
=================================

根据回测结果生成 HTML 格式的回测报告。

运行方式：
    python backtest_generate_report.py

输出：
    生成 backtest_report.html 文件
"""

import csv
import json
import os
from datetime import datetime

# ===================== 配置 =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, "backtest_result.csv")
CONFIG_FILE = os.path.join(BASE_DIR, "backtest_config.json")
OUTPUT_HTML = os.path.join(BASE_DIR, "backtest_report.html")


def load_csv(filepath):
    """加载 CSV 数据"""
    results = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append({
                "symbol": row["symbol"],
                "initial_balance": float(row["initial_balance"]),
                "final_balance": float(row["final_balance"]),
                "profit": float(row["profit"]),
                "return_rate": float(row["return_rate"]),
                "close_profit": float(row["close_profit"]),
                "commission": float(row["commission"]),
            })
    return results


def load_config(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_exchange_name(symbol):
    """从合约代码中提取交易所名称"""
    exchange_map = {
        "SHFE": "上期所",
        "DCE": "大商所",
        "CZCE": "郑商所",
        "INE": "能源中心",
        "CFFEX": "中金所",
    }
    parts = symbol.split("@")
    if len(parts) > 1:
        exch = parts[1].split(".")[0]
        return exchange_map.get(exch, exch)
    return "未知"


def get_product_code(symbol):
    """从合约代码中提取品种代码"""
    parts = symbol.split("@")
    if len(parts) > 1:
        return parts[1].split(".")[1]
    return symbol


def compute_stats(results):
    """计算统计数据"""
    if not results:
        return {}

    profits = [r["profit"] for r in results]
    returns = [r["return_rate"] for r in results]
    commissions = [r["commission"] for r in results]
    close_profits = [r["close_profit"] for r in results]

    winning = [r for r in results if r["profit"] > 0]
    losing = [r for r in results if r["profit"] < 0]
    breakeven = [r for r in results if r["profit"] == 0]

    sorted_by_return = sorted(results, key=lambda x: x["return_rate"], reverse=True)

    return {
        "total": len(results),
        "winning": len(winning),
        "losing": len(losing),
        "breakeven": len(breakeven),
        "win_rate": len(winning) / len(results) * 100,
        "total_profit": sum(profits),
        "avg_return": sum(returns) / len(returns),
        "max_return": max(returns),
        "min_return": min(returns),
        "best_symbol": sorted_by_return[0]["symbol"] if sorted_by_return else "",
        "worst_symbol": sorted_by_return[-1]["symbol"] if sorted_by_return else "",
        "total_commission": sum(commissions),
        "total_close_profit": sum(close_profits),
        "sorted_results": sorted_by_return,
    }


def generate_chart_data(results):
    """生成图表数据"""
    sorted_by_exchange = {}
    for r in results:
        exch = get_exchange_name(r["symbol"])
        if exch not in sorted_by_exchange:
            sorted_by_exchange[exch] = []
        sorted_by_exchange[exch].append(r)

    # 按收益率排序用于条形图
    sorted_results = sorted(results, key=lambda x: x["return_rate"], reverse=True)
    bar_labels = [get_product_code(r["symbol"]) for r in sorted_results]
    bar_values = [round(r["return_rate"], 4) for r in sorted_results]
    bar_colors = ["#c0392b" if v >= 0 else "#27ae60" for v in bar_values]  # 中国惯例：涨红跌绿

    # 交易所分布饼图
    exchange_data = {}
    for r in results:
        exch = get_exchange_name(r["symbol"])
        if exch not in exchange_data:
            exchange_data[exch] = {"winning": 0, "losing": 0, "total": 0}
        exchange_data[exch]["total"] += 1
        if r["profit"] > 0:
            exchange_data[exch]["winning"] += 1
        elif r["profit"] < 0:
            exchange_data[exch]["losing"] += 1

    return {
        "bar_labels": bar_labels,
        "bar_values": bar_values,
        "bar_colors": bar_colors,
        "exchange_data": exchange_data,
    }


def render_html(results, stats, chart_data, config):
    """渲染 HTML 报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start_date = config.get("start_date", "N/A")
    end_date = config.get("end_date", "N/A")
    rsi_period = config.get("rsi_period", "N/A")
    overbought = config.get("overbought", "N/A")
    oversold = config.get("oversold", "N/A")
    kline_dur = config.get("kline_dur", 3600)
    kline_name = {60: "1分钟", 300: "5分钟", 900: "15分钟", 1800: "30分钟", 3600: "1小时", 86400: "日线"}.get(kline_dur, f"{kline_dur}秒")

    # 生成表格行 HTML
    table_rows = ""
    for i, r in enumerate(stats["sorted_results"], 1):
        profit_class = "profit-pos" if r["profit"] > 0 else ("profit-neg" if r["profit"] < 0 else "profit-zero")
        return_class = "return-pos" if r["return_rate"] > 0 else ("return-neg" if r["return_rate"] < 0 else "return-zero")
        table_rows += f"""
        <tr>
            <td class="rank">{i}</td>
            <td class="symbol-cell">{get_product_code(r['symbol'])}<br><span class="exchange-badge">{get_exchange_name(r['symbol'])}</span></td>
            <td>{r['initial_balance']:,.0f}</td>
            <td>{r['final_balance']:,.2f}</td>
            <td class="{profit_class}">{r['profit']:+,.2f}</td>
            <td class="{return_class}">{r['return_rate']:+.4f}%</td>
            <td>{r['close_profit']:,.2f}</td>
            <td>{r['commission']:,.2f}</td>
        </tr>"""

    # 交易所统计卡片
    exchange_cards = ""
    exchange_colors = {
        "上期所": "#e74c3c",
        "大商所": "#3498db",
        "郑商所": "#2ecc71",
        "能源中心": "#f39c12",
        "中金所": "#9b59b6",
        "未知": "#95a5a6",
    }
    for exch, data in chart_data["exchange_data"].items():
        color = exchange_colors.get(exch, "#95a5a6")
        win_rate = data["winning"] / data["total"] * 100 if data["total"] > 0 else 0
        exchange_cards += f"""
        <div class="exchange-card" style="border-left: 4px solid {color}">
            <div class="exch-name">{exch}</div>
            <div class="exch-stat">共 <b>{data['total']}</b> 个品种</div>
            <div class="exch-stat">盈利 <b style="color:#c0392b">{data['winning']}</b> | 亏损 <b style="color:#27ae60">{data['losing']}</b></div>
            <div class="exch-stat">胜率 <b>{win_rate:.1f}%</b></div>
        </div>"""

    bar_labels_json = json.dumps(chart_data["bar_labels"], ensure_ascii=False)
    bar_values_json = json.dumps(chart_data["bar_values"])
    bar_colors_json = json.dumps(chart_data["bar_colors"])

    total_profit_class = "stat-pos" if stats["total_profit"] >= 0 else "stat-neg"
    avg_return_class = "stat-pos" if stats["avg_return"] >= 0 else "stat-neg"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RSI 均值回归策略 - 多品种回测分析报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f0f2f5; color: #333; }}
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); color: white; padding: 40px 48px; }}
  .header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
  .header .subtitle {{ font-size: 14px; opacity: 0.8; }}
  .header .meta {{ margin-top: 20px; display: flex; gap: 32px; font-size: 13px; opacity: 0.9; }}
  .header .meta span {{ background: rgba(255,255,255,0.1); padding: 6px 14px; border-radius: 20px; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 32px 24px; }}
  .section-title {{ font-size: 18px; font-weight: 600; color: #1a1a2e; margin-bottom: 16px; padding-left: 12px; border-left: 4px solid #0f3460; }}

  /* 概览卡片 */
  .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .stat-card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); text-align: center; }}
  .stat-card .label {{ font-size: 12px; color: #888; margin-bottom: 8px; }}
  .stat-card .value {{ font-size: 26px; font-weight: 700; }}
  .stat-pos {{ color: #c0392b; }}
  .stat-neg {{ color: #27ae60; }}
  .stat-neutral {{ color: #0f3460; }}

  /* 交易所卡片 */
  .exchange-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 32px; }}
  .exchange-card {{ background: white; border-radius: 10px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .exch-name {{ font-size: 15px; font-weight: 600; color: #1a1a2e; margin-bottom: 8px; }}
  .exch-stat {{ font-size: 12px; color: #666; margin: 3px 0; }}

  /* 图表区域 */
  .charts-grid {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 32px; }}
  .chart-card {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
  .chart-card h3 {{ font-size: 14px; color: #555; margin-bottom: 16px; }}
  .chart-wrapper {{ position: relative; height: 320px; }}

  /* 数据表格 */
  .table-card {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 32px; overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f8f9fa; padding: 12px 10px; text-align: right; font-weight: 600; color: #555; border-bottom: 2px solid #e9ecef; white-space: nowrap; }}
  th:first-child, th:nth-child(2) {{ text-align: center; }}
  td {{ padding: 11px 10px; text-align: right; border-bottom: 1px solid #f0f0f0; }}
  td:first-child {{ text-align: center; color: #888; font-size: 12px; }}
  td.symbol-cell {{ text-align: center; font-weight: 600; color: #1a1a2e; }}
  .exchange-badge {{ font-size: 10px; color: #888; font-weight: normal; }}
  .rank {{ font-weight: 700; }}
  tr:hover {{ background: #fafbff; }}
  .profit-pos {{ color: #c0392b; font-weight: 600; }}
  .profit-neg {{ color: #27ae60; font-weight: 600; }}
  .profit-zero {{ color: #888; }}
  .return-pos {{ color: #c0392b; font-weight: 700; }}
  .return-neg {{ color: #27ae60; font-weight: 700; }}
  .return-zero {{ color: #888; }}

  .footer {{ text-align: center; color: #aaa; font-size: 12px; padding: 20px; }}
  @media (max-width: 768px) {{
    .charts-grid {{ grid-template-columns: 1fr; }}
    .header {{ padding: 24px 20px; }}
    .header .meta {{ flex-wrap: wrap; gap: 10px; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>📊 RSI 均值回归策略 — 多品种回测分析报告</h1>
  <div class="subtitle">RSI Mean Reversion Strategy Backtest Report</div>
  <div class="meta">
    <span>📅 回测区间：{start_date} ~ {end_date}</span>
    <span>⚡ K线周期：{kline_name}</span>
    <span>📈 RSI周期：{rsi_period} | 超买：{overbought} | 超卖：{oversold}</span>
    <span>🕐 生成时间：{now}</span>
  </div>
</div>

<div class="container">

  <!-- 概览统计 -->
  <div class="section-title">📋 回测概览</div>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="label">测试品种数</div>
      <div class="value stat-neutral">{stats['total']}</div>
    </div>
    <div class="stat-card">
      <div class="label">盈利品种</div>
      <div class="value stat-pos">{stats['winning']}</div>
    </div>
    <div class="stat-card">
      <div class="label">亏损品种</div>
      <div class="value stat-neg">{stats['losing']}</div>
    </div>
    <div class="stat-card">
      <div class="label">持平品种</div>
      <div class="value stat-neutral">{stats['breakeven']}</div>
    </div>
    <div class="stat-card">
      <div class="label">胜率</div>
      <div class="value {'stat-pos' if stats['win_rate'] >= 50 else 'stat-neg'}">{stats['win_rate']:.1f}%</div>
    </div>
    <div class="stat-card">
      <div class="label">总净利润（元）</div>
      <div class="value {total_profit_class}">{stats['total_profit']:+,.0f}</div>
    </div>
    <div class="stat-card">
      <div class="label">平均收益率</div>
      <div class="value {avg_return_class}">{stats['avg_return']:+.4f}%</div>
    </div>
    <div class="stat-card">
      <div class="label">最高收益率</div>
      <div class="value stat-pos">{stats['max_return']:+.4f}%</div>
    </div>
    <div class="stat-card">
      <div class="label">最低收益率</div>
      <div class="value stat-neg">{stats['min_return']:+.4f}%</div>
    </div>
    <div class="stat-card">
      <div class="label">总手续费（元）</div>
      <div class="value stat-neutral">{stats['total_commission']:,.2f}</div>
    </div>
  </div>

  <!-- 交易所分布 -->
  <div class="section-title">🏢 交易所分布</div>
  <div class="exchange-grid">
    {exchange_cards}
  </div>

  <!-- 图表 -->
  <div class="section-title">📊 收益率分布</div>
  <div class="charts-grid">
    <div class="chart-card">
      <h3>各品种收益率（按高低排序，红色=盈利，绿色=亏损）</h3>
      <div class="chart-wrapper">
        <canvas id="barChart"></canvas>
      </div>
    </div>
    <div class="chart-card">
      <h3>盈亏品种比例</h3>
      <div class="chart-wrapper">
        <canvas id="pieChart"></canvas>
      </div>
    </div>
  </div>

  <!-- 详细数据表 -->
  <div class="section-title">📑 详细回测结果（按收益率排序）</div>
  <div class="table-card">
    <table>
      <thead>
        <tr>
          <th>排名</th>
          <th>品种</th>
          <th>初始资金</th>
          <th>期末资金</th>
          <th>净利润</th>
          <th>收益率</th>
          <th>平仓盈亏</th>
          <th>手续费</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>

</div>

<div class="footer">
  本报告由 RSI 均值回归策略回测系统自动生成 · 数据仅供参考，不构成投资建议
</div>

<script>
// 收益率条形图
const barCtx = document.getElementById('barChart').getContext('2d');
const barLabels = {bar_labels_json};
const barValues = {bar_values_json};
const barColors = {bar_colors_json};

new Chart(barCtx, {{
  type: 'bar',
  data: {{
    labels: barLabels,
    datasets: [{{
      label: '收益率 (%)',
      data: barValues,
      backgroundColor: barColors,
      borderColor: barColors,
      borderWidth: 1,
      borderRadius: 3,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        callbacks: {{
          label: (ctx) => ` ${{ctx.parsed.y >= 0 ? '+' : ''}}${{ctx.parsed.y.toFixed(4)}}%`
        }}
      }}
    }},
    scales: {{
      x: {{
        ticks: {{ font: {{ size: 10 }}, maxRotation: 90 }},
        grid: {{ display: false }}
      }},
      y: {{
        ticks: {{ callback: (v) => v.toFixed(2) + '%' }},
        grid: {{ color: '#f0f0f0' }}
      }}
    }}
  }}
}});

// 盈亏饼图
const pieCtx = document.getElementById('pieChart').getContext('2d');
new Chart(pieCtx, {{
  type: 'doughnut',
  data: {{
    labels: ['盈利 ({stats["winning"]})', '亏损 ({stats["losing"]})', '持平 ({stats["breakeven"]})'],
    datasets: [{{
      data: [{stats['winning']}, {stats['losing']}, {stats['breakeven']}],
      backgroundColor: ['#c0392b', '#27ae60', '#95a5a6'],
      borderWidth: 2,
      borderColor: '#fff'
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ font: {{ size: 12 }}, padding: 16 }} }},
      tooltip: {{
        callbacks: {{
          label: (ctx) => ` ${{ctx.label}}: ${{ctx.parsed}} (${{(ctx.parsed/{stats['total']}*100).toFixed(1)}}%)`
        }}
      }}
    }}
  }}
}});
</script>
</body>
</html>"""
    return html


def main():
    print("=" * 60)
    print("RSI 均值回归策略 - 回测报告生成器")
    print("=" * 60)

    if not os.path.exists(CSV_FILE):
        print(f"[错误] 未找到回测结果文件: {CSV_FILE}")
        print("请先运行回测脚本完成回测")
        return

    print(f"[读取数据] {CSV_FILE}")
    results = load_csv(CSV_FILE)
    config = load_config(CONFIG_FILE)

    if not results:
        print("[错误] CSV 文件为空，无数据可分析")
        return

    print(f"[统计] 共加载 {len(results)} 个品种的回测结果")

    stats = compute_stats(results)
    chart_data = generate_chart_data(results)
    html = render_html(results, stats, chart_data, config)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n[完成] 报告已生成: {OUTPUT_HTML}")
    print(f"\n{'='*60}")
    print("快速统计:")
    print(f"  测试品种数: {stats['total']}")
    print(f"  胜率: {stats['win_rate']:.1f}%")
    print(f"  盈利品种: {stats['winning']} | 亏损品种: {stats['losing']} | 持平: {stats['breakeven']}")
    print(f"  平均收益率: {stats['avg_return']:+.4f}%")
    print(f"  最佳品种: {stats['best_symbol']} ({stats['max_return']:+.4f}%)")
    print(f"  最差品种: {stats['worst_symbol']} ({stats['min_return']:+.4f}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
