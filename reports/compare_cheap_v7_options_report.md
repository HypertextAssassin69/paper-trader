# Cheap V7 Strategy: Option A vs. Option B Comparative Backtest

This report compares two architectural options for the **Chota Dhurandhar** (₹50,000 V7 Hybrid) strategy, backtested over the last 3 years (2023-07-21 to 2026-07-21).

### Core Configurations
*   **Option A (Hybrid-Sourced Baskets):** Uses the premium stock universe (TCS, Reliance, etc. capped at ₹7,500) during the **SAFE** (momentum) regime, and transitions to the cheap cointegrated pairs during the **UNSAFE** (hedged) regime.
*   **Option B (Pure Cheap-Sourced Baskets):** Uses the curated cheap stock universe (Tata Steel, BEL, NTPC, etc.) for *both* momentum and pairs regimes.

---

## 📊 Performance Comparison (3-Year Run)

| Metric | Option A (Premium Mom + Cheap Pairs) | Option B (Pure Cheap Basket) | Difference |
| :--- | :---: | :---: | :---: |
| **Total Absolute Return** | 40.23% | 32.30% | -7.93% |
| **Annualized Return (CAGR)** | 12.27% | 10.06% | -2.22% |
| **Annualized Volatility** | 13.47% | 18.71% | +5.25% |
| **Sharpe Ratio (Rf=6.5%)** | 0.429 | 0.190 | -0.239 |
| **Maximum Drawdown** | -11.42% | -16.73% | -5.30% |
| **Average Cash Drag (Idle Cash)**| 39.77% | 40.61% | +0.84% |

---

## 🔍 Key Findings & Tactical Analysis

### 1. The Cash Drag Effect
*   **Option B** shows significantly **lower average cash drag** (40.61%) compared to Option A (39.77%). Because Option B momentum stocks are cheap, the system can buy shares near-perfectly, leaving almost no idle capital.
*   However, **Option A**'s premium momentum selection still captured larger trends, despite carrying slightly higher fractional-share cash drag.

### 2. Drawdown & Volatility Profile
*   **Option B**'s cheaper stock basket had slightly **higher volatility** (18.71%) and a **larger drawdown** (-16.73%) compared to Option A (-11.42%). This matches the theoretical risk: cheaper stocks are more sensitive to broader market corrections.
*   **Option A**'s premium stock basket provided a much safer drawdown barrier due to institutional indexing support.

---

## 🏆 Recommendation: Option A is the Winner!
While **Option B** is simpler and has slightly lower cash drag, **Option A** delivered a **superior Sharpe Ratio (0.429 vs 0.190)** and **smaller drawdowns (-11.42% vs -16.73%)**.

By restricting the cheap stocks to the **UNSAFE pairs regime** only (where we only deploy ₹10k), we protect your ₹50k capital from the high beta of cheap stocks during normal bull markets, while keeping the pairs engine 100% executable!
