import traceback

try:
    import backtest_generate_report
    backtest_generate_report.main()
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()