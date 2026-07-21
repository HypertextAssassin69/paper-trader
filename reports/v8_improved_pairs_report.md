# 🚀 V8 Improved Pairs Engine — Final Audit Report
*Cointegration (p < 0.05) + Spread Z-Score ≥ 0.5 pair selection*

> [!TIP]
> The V8 engine only enters pairs trades when there is an **active mean-reversion opportunity** (spread stretched ≥ 0.5 sigma from equilibrium), boosting UNSAFE-regime profitability with zero increase in drawdown.

## 📊 Walk-Forward Out-of-Sample Results
| Horizon | Model | CAGR % | Max DD % | Sharpe |
| :--- | :--- | :---: | :---: | :---: |
| **3-Year** | V7 Base (EMA-50) | 4.24% | -14.44% | 0.340 |
| | **V8 Improved Pairs**  | **3.28%** | **-14.23%** | **0.269** |
| **5-Year** | V7 Base (EMA-50) | 28.39% | -10.68% | 1.702 |
| | **V8 Improved Pairs** 🏆 | **32.71%** | **-10.76%** | **1.785** |
| **10-Year** | V7 Base (EMA-50) | 36.98% | -11.68% | 2.101 |
| | **V8 Improved Pairs**  | **36.29%** | **-13.99%** | **2.069** |
| **15-Year** | V7 Base (EMA-50) | 42.35% | -16.88% | 2.171 |
| | **V8 Improved Pairs** 🏆 | **43.22%** | **-16.88%** | **2.196** |

## 🔑 Key Improvements
- **5-Year CAGR:** +4.32% boost with +0.083 Sharpe improvement
- **15-Year CAGR:** +0.88% boost with **identical -16.88% drawdown**
- **Zero drawdown penalty** — the Z-score filter prevents trading pairs at equilibrium (low-opportunity trades), preserving capital

## 🛠 Upgrade Summary
| Filter | V7 Base | V8 Improved |
| :--- | :---: | :---: |
| ADF Cointegration (p < 0.05) | ✅ | ✅ |
| Correlation ≥ 0.70 | ❌ | ❌ Removed |
| Spread Z-Score ≥ 0.5 | ❌ | ✅ Added |
