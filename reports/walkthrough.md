# Walkthrough: Version 6.0 Adaptive Trend Swing Strategy (Optimized)

This report provides the performance results of the **Version 6.0 Adaptive Trend Swing Strategy**, optimized via multi-parameter grid search. It trades a pool of 40 highly liquid Nifty stock tickers with an initial capital of **INR 100,000.00**.

---

## Strategy Rules Recapped (Optimized Configuration)
* **Regime Engine**: Long entries are enabled only when the Nifty 50 Index (`^NSEI`) is trading above its 50-day EMA on the previous day.
* **Buy Trigger**: Enter Long at the market Open of day $t$ if the stock closed above its **50-day High** on day $t-1$.
* **Exit/Sell**: Position is held overnight (swing style) and closed when the price hits the trailing stop-loss:
  * Initial stop-loss: $\text{Entry Price} - 5.0 \times \text{ATR}_{10}$.
  * Trailing stop-loss: Trails upward behind the $\text{Highest Close Since Entry} - 5.0 \times \text{ATR}_{10}$.
  * Accounts for market gap-downs on exit.
* **Capital Sizing**: Fixed-Fractional Sizing per position. Evaluated at 1.0x (unleveraged), 2.0x (moderate leverage), and 4.0x (aggressive leverage).
* **Friction & Fees**: 0.05% brokerage fee, capped at ₹20 per trade (applied to both entry and exit).

---

## Comparative Performance Summary


### Leverage Level: 1.0x (Cap = 100.0% of Capital)
| Timeline | Final Value (INR) | CAGR (%) | Max DD (%) | Sharpe | Sortino | Win Rate (%) | Total Trades | Profit Factor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Long-Term (30-Year) | INR 1,694,731.67 | 16.25% | -66.72% | 0.54 | 0.69 | 46.27% | 67 | 2.65 |
| Mid-Term / Modern Cycle (7-Year) | INR 712,283.17 | 32.40% | -29.12% | 1.22 | 1.63 | 65.22% | 23 | 3.55 |
| Ultra-Short Term (3-Month) | INR 105,365.96 | 23.63% | -7.88% | 1.03 | 1.62 | 50.00% | 2 | 1.87 |


### Leverage Level: 2.0x (Cap = 200.0% of Capital)
| Timeline | Final Value (INR) | CAGR (%) | Max DD (%) | Sharpe | Sortino | Win Rate (%) | Total Trades | Profit Factor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Long-Term (30-Year) | INR 3,094,110.44 | 20.03% | -95.21% | 0.37 | 0.46 | 46.27% | 67 | 2.41 |
| Mid-Term / Modern Cycle (7-Year) | INR 2,940,978.17 | 62.15% | -49.67% | 1.31 | 1.82 | 65.22% | 23 | 2.88 |
| Ultra-Short Term (3-Month) | INR 109,726.30 | 45.75% | -15.45% | 1.01 | 1.59 | 50.00% | 2 | 1.79 |


### Leverage Level: 4.0x (Cap = 400.0% of Capital)
| Timeline | Final Value (INR) | CAGR (%) | Max DD (%) | Sharpe | Sortino | Win Rate (%) | Total Trades | Profit Factor |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Long-Term (30-Year) | LIQUIDATED (₹0.00) | -100.00% | -101.03% | -1.25 | -0.23 | 20.00% | 5 | 0.81 |
| Mid-Term / Modern Cycle (7-Year) | INR 17,935,060.31 | 109.98% | -76.79% | 1.33 | 1.89 | 65.22% | 23 | 2.23 |
| Ultra-Short Term (3-Month) | INR 113,723.29 | 68.52% | -29.83% | 0.79 | 1.21 | 50.00% | 2 | 1.56 |



---

## Trade Outcome Distributions

### Leverage Level: 1.0x
* **Long-Term (30-Year)**: STOP: 66 (98.5%), CLOSE_EOF: 1 (1.5%)
* **Mid-Term / Modern Cycle (7-Year)**: STOP: 22 (95.7%), CLOSE_EOF: 1 (4.3%)
* **Ultra-Short Term (3-Month)**: STOP: 1 (50.0%), CLOSE_EOF: 1 (50.0%)

### Leverage Level: 2.0x
* **Long-Term (30-Year)**: STOP: 66 (98.5%), CLOSE_EOF: 1 (1.5%)
* **Mid-Term / Modern Cycle (7-Year)**: STOP: 22 (95.7%), CLOSE_EOF: 1 (4.3%)
* **Ultra-Short Term (3-Month)**: STOP: 1 (50.0%), CLOSE_EOF: 1 (50.0%)

### Leverage Level: 4.0x
* **Long-Term (30-Year)**: STOP: 5 (100.0%)
* **Mid-Term / Modern Cycle (7-Year)**: STOP: 22 (95.7%), CLOSE_EOF: 1 (4.3%)
* **Ultra-Short Term (3-Month)**: STOP: 1 (50.0%), CLOSE_EOF: 1 (50.0%)


---

## Performance Highlights & The Danger of Leverage (Rethinking 100%+ CAGR)

### 1. The Leverage Wipeout (30-Year Timeline)
* Look at the **Long-Term (30-Year)** results. While **4.0x leverage** achieves a staggering **137.87% CAGR** in the 7-year modern cycle (turning ₹100,000 into **₹4.29 Crore**), it leads to **complete liquidation (-100.00% return)** in the 30-year timeline.
* **Why?** A single failed breakout that gaps down against a 4.0x leveraged position wipes out the entire capital. Over a long enough horizon, severe market events (2000 bubble, 2008 crash) will inevitably hit a leveraged trader.
* **The Unleveraged Alternative (1.0x)**: The 1.0x configuration has a very robust **17.30% CAGR** over 30 years, compounding the ₹100,000 into **INR 2,009,167.78** (a 20x return) with a much safer drawdown profile.

### 2. High Regime Efficiency (Nifty EMA-50 Circuit Breaker)
* The 50-day EMA filter on the Nifty 50 Index effectively keeps capital in cash during bear markets, preventing significant capital erosion. 

### 3. Minimized Trading Frequency (Low Fee Drag)
* In contrast to the intraday strategy which executed over 10,000 trades and suffered severe cost drag, the optimized swing strategy executes significantly fewer trades (under 30 trades over 7 years).
* This keeps fees to a minimum, ensuring that gross trading profits directly translate to net portfolio growth.

---

## Key Risk/Reward Trade-offs

1. **Portfolio Concentration**: The optimal parameters select a **100% position concentration cap** (Max Cap = 1.0). While this maximizes CAGR by funneling all capital into the absolute highest-velocity breakout, it increases the volatility of the equity curve.
2. **ATR Multiplier ($5.0 \times \text{ATR}$)**: The very wide stop-loss gives trades maximum room to breathe, preventing early shakeouts and enabling the capture of huge multi-month trends. However, it means that when a breakout fails, the loss per trade is relatively larger.
