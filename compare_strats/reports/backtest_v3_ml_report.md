# Version 3.0 ML Probabilistic Softmax (Fix B) - Backtest Report

> **GMM Training**: 2018-01-01 to 2019-07-01 (1.5 yrs warmup, no trading)
> **Trading Period**: 2019-07-01 to 2026-07-01  |  **Universe**: 38 stocks
> **T=0.15** | **Max cap=20%/stock** | **Nifty EMA-50 Bear Guard: ON**

## Performance Metrics
| Metric | Value |
| :--- | :---: |
| Final Portfolio Value | **INR 476,418.15** |
| Total Return | **+376.42%** |
| CAGR (Annualized) | **25.50%** |
| Sharpe Ratio | 1.602 |
| Sortino Ratio | 1.390 |
| Calmar Ratio | 1.954 |
| Max Drawdown | -13.05% |
| Avg Top-Stock Allocation | 15.0% |
| Days in Cash (Bear Guard) | 586 (33.8%) |

## Head-to-Head vs All Versions (7-8 Year Backtest)
| Strategy | CAGR | Sharpe | Sortino | Max DD |
| :--- | :---: | :---: | :---: | :---: |
| **V3.0 ML Fix-B (this)** | **25.50%** | **1.602** | **1.390** | -13.05% |
| V2 No-Stops (Heuristic) | ~26.99% | 1.075 | 1.609 | -23.23% |
| V2 Bulletproof (Heuristic + EMA) | ~21.52% | 0.988 | 1.512 | -21.39% |
| V3.0 Raw (T=0.05, no guard) | 7.45% | 0.318 | 1.23 | -88.4% |

## Fix B Changes Explained
| Fix | Change | Why |
| :--- | :--- | :--- |
| Temperature | 0.05 -> 0.15 | Reduces single-stock concentration from 48% avg to ~15% avg |
| Max Stock Cap | None -> 20% | Hard ceiling so no single stock can dominate |
| Bear Guard | OFF -> ON | Nifty EMA-50 circuit breaker flushes to cash in bear markets |