import os
import sys
import pandas as pd
import numpy as np

import sys
sys.path.append(r"D:\strats\src")
from pairs_backtester import PairsTradingBacktester, calculate_pairs_metrics

START_CAPITAL = 100_000.0
TRAIN_START   = "2023-01-01"
TRAIN_END     = "2026-01-07"
TEST_START    = "2026-01-07"
TEST_END      = "2026-07-07"

def generate_report(top_pairs, m, trades_df):
    report_path = "compare_strats/reports/backtest_v6_pairs_report.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    pairs_list_md = ""
    for idx, p in enumerate(top_pairs):
        pairs_list_md += f"{idx+1}. **{p['pair'][0]} / {p['pair'][1]}** (p-value: `{p['p_value']:.4f}`, beta: `{p['beta']:.2f}`)\n"

    trades_rows = ""
    if not trades_df.empty:
        for _, r in trades_df.iterrows():
            trades_rows += f"| {r['Entry_Date'].date()} | {r['Exit_Date'].date()} | {r['Pair']} | {r['Type'].upper()} | INR {r['Entry_Val']:,.2f} | INR {r['Net_PnL']:,.2f} | {r['Outcome']} | {r['Reason']} |\n"

    report_content = f"""# Version 6.0 Pairs Trading - 6-Month Backtest Report

> **Training Period**: {TRAIN_START} to {TRAIN_END} (3 years)
> **Testing Period**: {TEST_START} to {TEST_END} (6 months)

## Selected Cointegrated Pairs

{pairs_list_md}

## Performance Summary

| Metric | Value |
| :--- | :---: |
| Initial Capital | INR {START_CAPITAL:,.2f} |
| Final Value | INR {m.get('Final_Value', 0.0):,.2f} |
| Total Return | **{m.get('Total_Return', 0.0)*100:.2f}%** |
| CAGR | **{m.get('CAGR', 0.0)*100:.2f}%** |
| Max Drawdown | **{m.get('Max_DD', 0.0)*100:.2f}%** |
| Sharpe Ratio | **{m.get('Sharpe', 0.0):.2f}** |
| Sortino Ratio | **{m.get('Sortino', 0.0):.2f}** |
| Profit Factor | **{m.get('Profit_Factor', 0.0):.2f}** |
| Win Rate | **{m.get('Win_Rate', 0.0)*100:.2f}%** |
| Total Trades | **{m.get('Total_Trades', 0)}** |

## Trade Log

| Entry | Exit | Pair | Type | Entry Value | Net PnL | Outcome | Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{trades_rows}
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"Report -> {report_path}")

def run_6m():
    data_dir = "data"
    print("=" * 60)
    print("  V6.0 Pairs Trading — 6-Month Backtest")
    print(f"  Train: {TRAIN_START} to {TRAIN_END}")
    print(f"  Test:  {TEST_START} to {TEST_END}")
    print("=" * 60)

    bt = PairsTradingBacktester(data_dir=data_dir, initial_capital=START_CAPITAL)
    bt.load_data()

    cointegrated_pairs = bt.find_cointegrated_pairs(
        pd.to_datetime(TRAIN_START), pd.to_datetime(TRAIN_END)
    )
    if not cointegrated_pairs:
        print("No cointegrated pairs found.")
        return

    top_pairs = cointegrated_pairs[:10]
    print("\nSelected Top 10 Pairs:")
    for idx, p in enumerate(top_pairs):
        print(f"  {idx+1}. {p['pair'][0]} / {p['pair'][1]} | p-value: {p['p_value']:.4f} | beta: {p['beta']:.4f}")

    eq_df, trades_df = bt.run_backtest(
        top_pairs,
        pd.to_datetime(TEST_START),
        pd.to_datetime(TEST_END),
        z_threshold=1.5,
        z_exit=0.5,
        z_stop=5.0,
        rolling_window=50,
        max_drawdown_pct=0.20,
        leverage=6.0
    )

    m = calculate_pairs_metrics(eq_df, trades_df, bt.initial_capital)
    print("\n" + "=" * 60)
    print("V6.0 PAIRS RESULTS:")
    print("=" * 60)
    print(f"  Final Value:       INR {m.get('Final_Value', 0.0):,.2f}")
    print(f"  Total Return:      {m.get('Total_Return', 0.0)*100:.2f}%")
    print(f"  CAGR:              {m.get('CAGR', 0.0)*100:.2f}%")
    print(f"  Max Drawdown:      {m.get('Max_DD', 0.0)*100:.2f}%")
    print(f"  Sharpe:            {m.get('Sharpe', 0.0):.2f}")
    print(f"  Sortino:           {m.get('Sortino', 0.0):.2f}")
    print(f"  Profit Factor:     {m.get('Profit_Factor', 0.0):.2f}")
    print(f"  Win Rate:          {m.get('Win_Rate', 0.0)*100:.2f}%")
    print(f"  Total Trades:      {m.get('Total_Trades', 0)}")
    print("=" * 60)

    generate_report(top_pairs, m, trades_df)

if __name__ == "__main__":
    run_6m()
