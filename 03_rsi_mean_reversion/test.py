# 测试脚本
print("测试开始")

# 测试1：直接运行backtest_generate_report.py
print("\n测试1：直接运行backtest_generate_report.py")
try:
    exec(open('backtest_generate_report.py').read())
except Exception as e:
    print(f"错误: {e}")

print("\n测试结束")