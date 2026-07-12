import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.append(os.path.dirname(__file__))
from intraday_v6_backtester import IntradayPairsBacktester, calculate_metrics

def run_intraday_backtest():
    interval = "15m"
    period = "60d"
    start_capital = 100_000.0

    print("=" * 65)
    print("  V6.0 INTRADAY PAIRS TRADING — 15-Min Bar Backtest")
    print(f"  Target: 4-15 trades/hour | Interval: {interval} | Period: {period}")
    print("=" * 65)

    bt = IntradayPairsBacktester(interval=interval, period=period, initial_capital=start_capital)
    bt.download_data()

    if len(bt.stock_data) < 10:
        print("Not enough tickers with data. Exiting.")
        return

    closes = pd.DataFrame({t: bt.stock_data[t]['Close'] for t in bt.stock_data})
    split_idx = int(len(closes) * 0.55)

    train_start, train_end = 0, split_idx
    test_start, test_end = split_idx, len(closes)

    print(f"\nTrain split: rows {train_start}-{train_end}")
    print(f"Test split:  rows {test_start}-{test_end}")
    print(f"Test dates:  {closes.index[test_start]} to {closes.index[test_end-1]}")

    pairs = bt.find_cointegrated_pairs(train_start, train_end)
    if not pairs:
        print("No cointegrated pairs found.")
        return

    top_pairs = pairs[:10]
    print("\nTop 10 Cointegrated Pairs:")
    for i, p in enumerate(top_pairs):
        print(f"  {i+1}. {p['pair'][0]} / {p['pair'][1]} | p-value: {p['p_value']:.4f} | beta: {p['beta']:.4f}")

    eq_df, trades_df = bt.run_backtest(
        top_pairs, test_start, test_end,
        z_threshold=1.5, z_exit=0.5, z_stop=5.0,
        rolling_window=30, max_drawdown_pct=0.20, leverage=6.0
    )

    m = calculate_metrics(eq_df, trades_df, bt.initial_capital)

    print("\n" + "=" * 65)
    print("  V6.0 INTRADAY PAIRS — RESULTS")
    print("=" * 65)
    print(f"  Final Value:        INR {m.get('Final_Value', 0):,.2f}")
    print(f"  Total Return:       {m.get('Total_Return', 0)*100:.2f}%")
    print(f"  CAGR:               {m.get('CAGR', 0)*100:.2f}%")
    print(f"  Max Drawdown:       {m.get('Max_DD', 0)*100:.2f}%")
    print(f"  Sharpe:             {m.get('Sharpe', 0):.2f}")
    print(f"  Sortino:            {m.get('Sortino', 0):.2f}")
    print(f"  Profit Factor:      {m.get('Profit_Factor', 0):.2f}")
    print(f"  Win Rate:           {m.get('Win_Rate', 0)*100:.2f}%")
    print(f"  Total Trades:       {m.get('Total_Trades', 0)}")
    if m.get('Total_Trades', 0) > 0:
        test_hours = len(eq_df) * 15 / 60
        trades_per_hour = m['Total_Trades'] / max(test_hours, 0.1)
        print(f"  Trading Hours:      {test_hours:.1f}")
        print(f"  Trades/Hour:        {trades_per_hour:.2f}")
    print("=" * 65)

    generate_report(top_pairs, m, trades_df, eq_df, interval)

def generate_report(top_pairs, m, trades_df, eq_df, interval):
    out_dir = os.path.join(os.path.dirname(__file__), 'compare_strats', 'reports')
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "intraday_v6_report.md")

    pairs_md = ""
    for i, p in enumerate(top_pairs):
        pairs_md += f"{i+1}. **{p['pair'][0]} / {p['pair'][1]}** (p-value: `{p['p_value']:.4f}`, beta: `{p['beta']:.2f}`)\n"

    trades_rows = ""
    if not trades_df.empty:
        for _, r in trades_df.iterrows():
            ed = r['Entry_Date']
            xd = r['Exit_Date']
            trades_rows += f"| {ed} | {xd} | {r['Pair']} | {r['Type'].upper()} | INR {r['Entry_Val']:,.2f} | INR {r['Net_PnL']:,.2f} | {r['Outcome']} | {r['Reason']} |\n"

    test_hours = len(eq_df) * 15 / 60 if not eq_df.empty else 0
    tph = m.get('Total_Trades', 0) / max(test_hours, 0.1)

    report = f"""# V6.0 Intraday Pairs Trading — {interval} Bar Backtest

> **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
> **Test Duration:** {test_hours:.1f} trading hours
> **Target Frequency:** 4-15 trades/hour | **Achieved:** {tph:.2f} trades/hour

## Selected Cointegrated Pairs

{pairs_md}

## Performance Summary

| Metric | Value |
| :--- | :---: |
| Initial Capital | INR {m.get('Final_Value', 0) / (1 + m.get('Total_Return', 0)):,.2f} |
| Final Value | INR {m.get('Final_Value', 0):,.2f} |
| Total Return | **{m.get('Total_Return', 0)*100:.2f}%** |
| CAGR | **{m.get('CAGR', 0)*100:.2f}%** |
| Max Drawdown | **{m.get('Max_DD', 0)*100:.2f}%** |
| Sharpe Ratio | **{m.get('Sharpe', 0):.2f}** |
| Sortino Ratio | **{m.get('Sortino', 0):.2f}** |
| Profit Factor | **{m.get('Profit_Factor', 0):.2f}** |
| Win Rate | **{m.get('Win_Rate', 0)*100:.2f}%** |
| Total Trades | **{m.get('Total_Trades', 0)}** |
| Trades/Hour | **{tph:.2f}** |

## Trade Log

| Entry | Exit | Pair | Type | Entry Value | Net PnL | Outcome | Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{trades_rows}
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report -> {report_path}")

if __name__ == "__main__":
    run_intraday_backtest()
