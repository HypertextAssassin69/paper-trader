# Walkthrough: 3-Month Institutional Cointegrated Pairs Trading Strategy

This walkthrough documents the recent out-of-sample performance of our **Cointegrated Pairs Trading Strategy** over the last 3 months, run on the 40 Nifty stock pool.

---

## 1. Cointegration Search & Training Phase
To capture the most modern market regime leading up to the 3-month test, we dynamically search for cointegration in:
* **Training / Search Window**: `2021-04-07` to `2026-04-07` (5 Years)
* **Out-of-Sample Backtest Window**: `2026-04-07` to `2026-07-07` (3 Months)

The top 10 cointegrated pairs selected for this 3-month cycle are:

1. **JSWSTEEL.NS / EICHERMOT.NS** (p-value: `0.0002`, training beta: `0.12`)
2. **GRASIM.NS / APOLLOHOSP.NS** (p-value: `0.0003`, training beta: `0.37`)
3. **KOTAKBANK.NS / BAJFINANCE.NS** (p-value: `0.0003`, training beta: `0.18`)
4. **ULTRACEMCO.NS / APOLLOHOSP.NS** (p-value: `0.0006`, training beta: `1.60`)
5. **KOTAKBANK.NS / BAJAJFINSV.NS** (p-value: `0.0014`, training beta: `0.09`)
6. **BHARTIARTL.NS / JSWSTEEL.NS** (p-value: `0.0016`, training beta: `2.68`)
7. **AXISBANK.NS / COALINDIA.NS** (p-value: `0.0035`, training beta: `1.50`)
8. **KOTAKBANK.NS / DIVISLAB.NS** (p-value: `0.0039`, training beta: `0.02`)
9. **LT.NS / AXISBANK.NS** (p-value: `0.0049`, training beta: `4.28`)
10. **ICICIBANK.NS / GRASIM.NS** (p-value: `0.0049`, training beta: `0.50`)


---

## 2. Institutional Strategy Execution Rules
1. **Dynamic Rolling Spread**: Spreads are calculated dynamically daily using a rolling **50-day OLS window**.
2. **Z-Score Trigger**: Entry at $|Z_t| \ge 1.5$. Exit at $Z_t \to 0.5$ (Mean Reversion) or $|Z_t| \ge 5.0$ (Divergence Stop-Loss).
3. **Volatility Sizing (Path 2)**: Dynamic VIX-based leverage scaling (VIX < 15 full 6.0x leverage; scaled down to 1.0x at VIX 22; halt entries at VIX 25).
4. **Portfolio Heat-Map Stop (Path 3)**: Global unrealized loss limit of **-5.0%** of total capital checks.
5. **Drawdown Cap**: Hard **20.0% trailing drawdown limit**.

---

## 3. Out-of-Sample Performance Summary (3-Month Window)

* **Initial Capital**: INR 100,000.00
* **Final Value**: INR 107,882.11
* **Out-of-Sample Total Return**: **7.88%**
* **CAGR**: **36.06%**
* **Maximum Drawdown**: **-5.12%**
* **Sharpe Ratio**: **2.36**
* **Sortino Ratio**: **4.03**
* **Institutional Profit Factor**: **1.39**
* **Win Rate**: **63.16%**
* **Total Executed Trades**: **38**

---

## 4. Detailed Trade Logs

| Entry Date | Exit Date | Pair | Trade Type | Entry Value | Net PnL (INR) | Outcome | Exit Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-04-09 | 2026-04-10 | ICICIBANK.NS/GRASIM.NS | LONG_SPREAD | INR 18,471.90 | INR 299.70 | PROFIT | MEAN_REVERSION |
| 2026-04-09 | 2026-04-17 | KOTAKBANK.NS/BAJFINANCE.NS | LONG_SPREAD | INR 20,288.25 | INR 252.27 | PROFIT | MEAN_REVERSION |
| 2026-04-13 | 2026-04-24 | ICICIBANK.NS/GRASIM.NS | SHORT_SPREAD | INR 17,596.70 | INR 235.70 | PROFIT | MEAN_REVERSION |
| 2026-04-10 | 2026-04-27 | KOTAKBANK.NS/BAJAJFINSV.NS | LONG_SPREAD | INR 32,374.57 | INR 397.33 | PROFIT | MEAN_REVERSION |
| 2026-04-21 | 2026-04-27 | LT.NS/AXISBANK.NS | LONG_SPREAD | INR 40,845.39 | INR 654.62 | PROFIT | MEAN_REVERSION |
| 2026-04-17 | 2026-04-30 | BHARTIARTL.NS/JSWSTEEL.NS | LONG_SPREAD | INR 44,360.70 | INR 0.42 | PROFIT | MEAN_REVERSION |
| 2026-04-29 | 2026-05-04 | KOTAKBANK.NS/BAJAJFINSV.NS | SHORT_SPREAD | INR 42,926.35 | INR 621.88 | PROFIT | MEAN_REVERSION |
| 2026-04-21 | 2026-05-05 | AXISBANK.NS/COALINDIA.NS | SHORT_SPREAD | INR 41,050.40 | INR 3,084.07 | PROFIT | MEAN_REVERSION |
| 2026-05-06 | 2026-05-08 | GRASIM.NS/APOLLOHOSP.NS | SHORT_SPREAD | INR 46,599.90 | INR 531.06 | PROFIT | MEAN_REVERSION |
| 2026-05-05 | 2026-05-08 | KOTAKBANK.NS/BAJAJFINSV.NS | LONG_SPREAD | INR 39,776.67 | INR 209.27 | PROFIT | MEAN_REVERSION |
| 2026-04-21 | 2026-05-12 | KOTAKBANK.NS/BAJFINANCE.NS | LONG_SPREAD | INR 41,164.61 | INR 385.47 | PROFIT | MEAN_REVERSION |
| 2026-05-05 | 2026-05-14 | BHARTIARTL.NS/JSWSTEEL.NS | LONG_SPREAD | INR 39,791.06 | INR 102.12 | PROFIT | MEAN_REVERSION |
| 2026-04-23 | 2026-05-15 | KOTAKBANK.NS/DIVISLAB.NS | LONG_SPREAD | INR 29,795.40 | INR -29.43 | LOSS | MEAN_REVERSION |
| 2026-04-17 | 2026-05-21 | JSWSTEEL.NS/EICHERMOT.NS | SHORT_SPREAD | INR 43,766.40 | INR -1,669.89 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-05-08 | 2026-05-21 | ULTRACEMCO.NS/APOLLOHOSP.NS | LONG_SPREAD | INR 48,191.00 | INR -1,634.37 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-05-13 | 2026-05-21 | KOTAKBANK.NS/BAJAJFINSV.NS | SHORT_SPREAD | INR 28,170.11 | INR 36.16 | WIN | PORTFOLIO_HEAT_STOP |
| 2026-05-15 | 2026-05-21 | BHARTIARTL.NS/JSWSTEEL.NS | SHORT_SPREAD | INR 31,772.66 | INR 161.47 | WIN | PORTFOLIO_HEAT_STOP |
| 2026-04-28 | 2026-05-21 | LT.NS/AXISBANK.NS | SHORT_SPREAD | INR 35,329.58 | INR -137.29 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-04-28 | 2026-05-21 | ICICIBANK.NS/GRASIM.NS | LONG_SPREAD | INR 38,861.00 | INR -3,379.22 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-05-22 | 2026-05-25 | JSWSTEEL.NS/EICHERMOT.NS | SHORT_SPREAD | INR 33,135.38 | INR 772.78 | PROFIT | MEAN_REVERSION |
| 2026-05-25 | 2026-05-29 | KOTAKBANK.NS/DIVISLAB.NS | SHORT_SPREAD | INR 44,233.35 | INR 215.71 | PROFIT | MEAN_REVERSION |
| 2026-05-25 | 2026-06-01 | KOTAKBANK.NS/BAJAJFINSV.NS | SHORT_SPREAD | INR 47,440.02 | INR 266.62 | PROFIT | MEAN_REVERSION |
| 2026-05-26 | 2026-06-03 | GRASIM.NS/APOLLOHOSP.NS | SHORT_SPREAD | INR 50,095.50 | INR 553.51 | PROFIT | MEAN_REVERSION |
| 2026-05-29 | 2026-06-08 | LT.NS/AXISBANK.NS | SHORT_SPREAD | INR 50,191.00 | INR 787.39 | PROFIT | MEAN_REVERSION |
| 2026-06-08 | 2026-06-15 | GRASIM.NS/APOLLOHOSP.NS | LONG_SPREAD | INR 38,067.70 | INR 541.71 | PROFIT | MEAN_REVERSION |
| 2026-05-22 | 2026-06-15 | ULTRACEMCO.NS/APOLLOHOSP.NS | LONG_SPREAD | INR 28,294.00 | INR -343.40 | LOSS | MEAN_REVERSION |
| 2026-06-10 | 2026-06-15 | BHARTIARTL.NS/JSWSTEEL.NS | LONG_SPREAD | INR 54,404.06 | INR 349.98 | PROFIT | MEAN_REVERSION |
| 2026-06-23 | 2026-06-25 | JSWSTEEL.NS/EICHERMOT.NS | LONG_SPREAD | INR 59,954.53 | INR -407.03 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-05-25 | 2026-06-25 | KOTAKBANK.NS/BAJFINANCE.NS | SHORT_SPREAD | INR 47,367.48 | INR -77.84 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-06-04 | 2026-06-25 | KOTAKBANK.NS/BAJAJFINSV.NS | SHORT_SPREAD | INR 52,711.63 | INR -1,186.69 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-06-19 | 2026-06-25 | BHARTIARTL.NS/JSWSTEEL.NS | SHORT_SPREAD | INR 61,301.10 | INR -450.41 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-06-16 | 2026-06-25 | AXISBANK.NS/COALINDIA.NS | SHORT_SPREAD | INR 60,710.00 | INR -1,370.31 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-06-11 | 2026-06-25 | KOTAKBANK.NS/DIVISLAB.NS | SHORT_SPREAD | INR 53,763.15 | INR -902.92 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-06-15 | 2026-06-25 | LT.NS/AXISBANK.NS | SHORT_SPREAD | INR 59,291.20 | INR -190.22 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-06-12 | 2026-06-25 | ICICIBANK.NS/GRASIM.NS | SHORT_SPREAD | INR 57,447.10 | INR -896.16 | LOSS | PORTFOLIO_HEAT_STOP |
| 2026-06-26 | 2026-06-29 | KOTAKBANK.NS/BAJFINANCE.NS | SHORT_SPREAD | INR 58,680.30 | INR 963.44 | PROFIT | MEAN_REVERSION |
| 2026-06-26 | 2026-07-06 | KOTAKBANK.NS/BAJAJFINSV.NS | SHORT_SPREAD | INR 57,657.53 | INR 3,658.69 | PROFIT | MEAN_REVERSION |
| 2026-06-26 | 2026-07-06 | KOTAKBANK.NS/DIVISLAB.NS | SHORT_SPREAD | INR 56,302.00 | INR 2,515.52 | PROFIT | MEAN_REVERSION |


---

## 5. Key Takeaways from the 3-Month Run
1. **Regime Behavior**: Evaluates how the optimized statistical reversion edge behaves under immediate, short-term modern market shifts.
2. **Dynamic Volatility Buffer**: Verifies whether recent spikes in India VIX triggered leverage reductions to shield capital.
