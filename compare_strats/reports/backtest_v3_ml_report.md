# Version 3.0 ML Probabilistic Softmax (Fix B) - Backtest Report

> **GMM Training**: 1996-01-01 to 1997-07-01 (1.5 yrs warmup, no trading)
> **Trading Period**: 1997-07-01 to 2026-07-01  |  **Universe**: 38 stocks
> **T=0.15** | **Max cap=20%/stock** | **Nifty EMA-50 Bear Guard: ON**

## Performance Metrics
| Metric | Value |
| :--- | :---: |
| Final Portfolio Value | **INR 97,255,233.08** |
| Total Return | **+97155.23%** |
| CAGR (Annualized) | **26.96%** |
| Sharpe Ratio | 0.503 |
| Sortino Ratio | 1.100 |
| Calmar Ratio | 0.396 |
| Max Drawdown | -68.11% |
| Avg Top-Stock Allocation | 11.3% |
| Days in Cash (Bear Guard) | 1629 (22.4%) |

## Head-to-Head vs All Versions (7-8 Year Backtest)
| Strategy | CAGR | Sharpe | Sortino | Max DD |
| :--- | :---: | :---: | :---: | :---: |
| **V3.0 ML Fix-B (this)** | **26.96%** | **0.503** | **1.100** | -68.11% |
| V2 No-Stops (Heuristic) | ~26.99% | 1.075 | 1.609 | -23.23% |
| V2 Bulletproof (Heuristic + EMA) | ~21.52% | 0.988 | 1.512 | -21.39% |
| V3.0 Raw (T=0.05, no guard) | 7.45% | 0.318 | 1.23 | -88.4% |

## Fix B Changes Explained
| Fix | Change | Why |
| :--- | :--- | :--- |
| Temperature | 0.05 -> 0.15 | Reduces single-stock concentration from 48% avg to ~11% avg |
| Max Stock Cap | None -> 20% | Hard ceiling so no single stock can dominate |
| Bear Guard | OFF -> ON | Nifty EMA-50 circuit breaker flushes to cash in bear markets |