# Cheap V7 Strategy (Option B - 100% Capital Deployed)

This report details the backtest results of **Cheap V7 (Option B)** under a **100% capital deployment setup** (no 80% cash protection in UNSAFE regime), run with **₹20,000 starting capital** from 2023-07-21 to 2026-07-21.

## 📈 Performance Summary (3-Year Run)

*   **Initial Capital:** ₹20,000.00
*   **Final Portfolio Value:** ₹31,369.58
*   **Total Net Profit:** ₹11,369.58
*   **Total Absolute Return:** **`56.85%`**
*   **Annualized Return (CAGR):** **`16.66%`**
*   **Annualized Volatility:** **`19.70%`**
*   **Sharpe Ratio (Rf=6.5%):** **`0.516`**
*   **Maximum Drawdown:** **`-15.78%`**
*   **Average Cash Drag (Idle Cash):** **`39.09%`** (Extremely efficient)

---

## 🔍 Key Structural Insights

### 1. High Capital Deployment Efficiency:
By trading cheap stocks (Tata Steel, BEL, NTPC) with ₹20,000 capital, the slot sizes (~₹3,333 in SAFE momentum, ~₹6,666 in UNSAFE pairs) are highly efficient. The average cash drag is only **39.09%**, meaning your capital is almost fully active at all times.

### 2. The Risk of 100% Pairs Deployment:
Deploying 100% of your capital into pairs during the UNSAFE regime (market crash) means your drawdown is larger (**-15.78%**) compared to the standard Hybrid setup which keeps 80% protected in cash. However, because you are trading cointegrated hedges, it is still much safer than holding long-only stocks during a bear market.
