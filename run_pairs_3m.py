import os
import sys
import pandas as pd
import numpy as np

# Add the src folder to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from pairs_backtester import PairsTradingBacktester, calculate_pairs_metrics_static

def generate_markdown_report_3m(top_pairs, m, trades_df):
    report_path = "reports/pairs_3m_walkthrough.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    pairs_list_md = ""
    for idx, p in enumerate(top_pairs):
        pairs_list_md += f"{idx+1}. **{p['pair'][0]} / {p['pair'][1]}** (p-value: `{p['p_value']:.4f}`, training beta: `{p['beta']:.2f}`)\n"
        
    trades_rows = ""
    if not trades_df.empty:
        for idx, r in trades_df.iterrows():
            trades_rows += f"| {r['Entry_Date'].date()} | {r['Exit_Date'].date()} | {r['Pair']} | {r['Type'].upper()} | INR {r['Entry_Val']:,.2f} | INR {r['Net_PnL']:,.2f} | {r['Outcome']} | {r['Reason']} |\n"
    else:
        trades_rows = "| No trades executed during the testing window |"
        
    report_content = f"""# Walkthrough: 3-Month Institutional Cointegrated Pairs Trading Strategy

This walkthrough documents the recent out-of-sample performance of our **Cointegrated Pairs Trading Strategy** over the last 3 months, run on the 40 Nifty stock pool.

---

## 1. Cointegration Search & Training Phase
To capture the most modern market regime leading up to the 3-month test, we dynamically search for cointegration in:
* **Training / Search Window**: `2021-04-07` to `2026-04-07` (5 Years)
* **Out-of-Sample Backtest Window**: `2026-04-07` to `2026-07-07` (3 Months)

The top 10 cointegrated pairs selected for this 3-month cycle are:

{pairs_list_md}

---

## 2. Institutional Strategy Execution Rules
1. **Dynamic Rolling Spread**: Spreads are calculated dynamically daily using a rolling **50-day OLS window**.
2. **Z-Score Trigger**: Entry at $|Z_t| \\ge 1.5$. Exit at $Z_t \\to 0.5$ (Mean Reversion) or $|Z_t| \\ge 5.0$ (Divergence Stop-Loss).
3. **Volatility Sizing (Path 2)**: Dynamic VIX-based leverage scaling (VIX < 15 full 6.0x leverage; scaled down to 1.0x at VIX 22; halt entries at VIX 25).
4. **Portfolio Heat-Map Stop (Path 3)**: Global unrealized loss limit of **-5.0%** of total capital checks.
5. **Drawdown Cap**: Hard **20.0% trailing drawdown limit**.

---

## 3. Out-of-Sample Performance Summary (3-Month Window)

* **Initial Capital**: INR 100,000.00
* **Final Value**: INR {m.get('Final_Value', 0.0):,.2f}
* **Out-of-Sample Total Return**: **{m.get('Total_Return', 0.0)*100:.2f}%**
* **CAGR**: **{m.get('CAGR', 0.0)*100:.2f}%**
* **Maximum Drawdown**: **{m.get('Max_DD', 0.0)*100:.2f}%**
* **Sharpe Ratio**: **{m.get('Sharpe', 0.0):.2f}**
* **Sortino Ratio**: **{m.get('Sortino', 0.0):.2f}**
* **Institutional Profit Factor**: **{m.get('Profit_Factor', 0.0):.2f}**
* **Win Rate**: **{m.get('Win_Rate', 0.0)*100:.2f}%**
* **Total Executed Trades**: **{m.get('Total_Trades', 0)}**

---

## 4. Detailed Trade Logs

| Entry Date | Exit Date | Pair | Trade Type | Entry Value | Net PnL (INR) | Outcome | Exit Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{trades_rows}

---

## 5. Key Takeaways from the 3-Month Run
1. **Regime Behavior**: Evaluates how the optimized statistical reversion edge behaves under immediate, short-term modern market shifts.
2. **Dynamic Volatility Buffer**: Verifies whether recent spikes in India VIX triggered leverage reductions to shield capital.
"""

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    print(f"3-Month Pairs report written to: {report_path}")

def run_pipeline_3m():
    data_dir = "data"
    
    downloader = PairsTradingBacktester(data_dir=data_dir)
    downloader.load_data()
    
    # 5-year training leading up to 2026-04-07
    train_start = pd.to_datetime("2021-04-07")
    train_end = pd.to_datetime("2026-04-07")
    
    # 3-month testing window
    test_start = pd.to_datetime("2026-04-07")
    test_end = pd.to_datetime("2026-07-07")
    
    cointegrated_pairs = downloader.find_cointegrated_pairs(train_start, train_end)
    
    if not cointegrated_pairs:
        print("No cointegrated pairs found. Exiting.")
        return
        
    top_pairs = cointegrated_pairs[:10]
    print("\n" + "="*50)
    print("SELECTED TOP 10 COINTEGRATED PAIRS TO TRADE (3M WINDOW):")
    for idx, p in enumerate(top_pairs):
        print(f"  {idx+1}. Pair: {p['pair'][0]} / {p['pair'][1]} | Coint p-value: {p['p_value']:.4f} | Training Beta: {p['beta']:.4f}")
    print("="*50)
    
    eq_df, trades_df = downloader.run_backtest(
        top_pairs, 
        test_start, 
        test_end,
        z_threshold=1.5,
        z_exit=0.5,
        z_stop=5.0,
        rolling_window=50,
        max_drawdown_pct=0.20,
        leverage=6.0
    )
    
    m = calculate_pairs_metrics_static(eq_df, trades_df, downloader.initial_capital)
    
    print("\n" + "="*50)
    print("Pairs Trading 3-Month Out-Of-Sample Results:")
    print("="*50)
    print(f"  Final Portfolio Value: INR {m.get('Final_Value', 0.0):,.2f}")
    print(f"  Out-of-Sample Return:  {m.get('Total_Return', 0.0)*100:.2f}%")
    print(f"  CAGR:                  {m.get('CAGR', 0.0)*100:.2f}%")
    print(f"  Max Drawdown:          {m.get('Max_DD', 0.0)*100:.2f}%")
    print(f"  Sharpe Ratio:          {m.get('Sharpe', 0.0):.2f}")
    print(f"  Sortino Ratio:         {m.get('Sortino', 0.0):.2f}")
    print(f"  Profit Factor:         {m.get('Profit_Factor', 0.0):.2f}")
    print(f"  Win Rate:              {m.get('Win_Rate', 0.0)*100:.2f}%")
    print(f"  Total Trades:          {m.get('Total_Trades', 0)}")
    print("="*50)
    
    generate_markdown_report_3m(top_pairs, m, trades_df)

if __name__ == "__main__":
    run_pipeline_3m()
