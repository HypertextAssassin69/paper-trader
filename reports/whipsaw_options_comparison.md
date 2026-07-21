# 🔬 Whipsaw Mitigation Audit: Option 1 vs. Option 3
*Separated performance analysis of Hysteresis Buffer vs. Soft Regime Scaling*

> [!NOTE]
> * **Option 1 (Hysteresis Buffer):** Maintains previous regime state inside a 1.5% band around the EMA-50 to ignore minor crossovers (State Memory).
> * **Option 3 (Soft Scaling):** Linearly scales weights (SAFE vs. UNSAFE) between a +/- 1.5% band around the EMA-50 (Continuous Allocation).

## 📊 Audited Separation Leaderboard
### 📅 Horizon: 3-Year (to July 2026)
| Strategy Model | CAGR % | Max Drawdown % | Sharpe Ratio |
| :--- | :---: | :---: | :---: |
| **Standard Binary (Base)** | **4.01%** | **-13.83%** | **0.322** 🥇 |
| Option 3 (Soft Scaling Only) | 2.45% | -15.75% | 0.213 |
| Option 1 (Hysteresis Buffer Only) | 0.76% | -24.49% | 0.073 |

### 📅 Horizon: 5-Year (to July 2026)
| Strategy Model | CAGR % | Max Drawdown % | Sharpe Ratio |
| :--- | :---: | :---: | :---: |
| **Standard Binary (Base)** | **28.28%** | **-10.98%** | **1.687** 🥇 |
| Option 3 (Soft Scaling Only) | 21.94% | -12.74% | 1.407 |
| Option 1 (Hysteresis Buffer Only) | 21.87% | -21.23% | 1.318 |

### 📅 Horizon: 10-Year (to July 2026)
| Strategy Model | CAGR % | Max Drawdown % | Sharpe Ratio |
| :--- | :---: | :---: | :---: |
| **Standard Binary (Base)** | **37.42%** | **-11.46%** | **2.111** 🥇 |
| Option 3 (Soft Scaling Only) | 34.04% | -15.55% | 2.023 |
| Option 1 (Hysteresis Buffer Only) | 34.92% | -18.06% | 1.957 |

### 📅 Horizon: 15-Year (to July 2026)
| Strategy Model | CAGR % | Max Drawdown % | Sharpe Ratio |
| :--- | :---: | :---: | :---: |
| **Standard Binary (Base)** | **41.85%** | **-14.56%** | **2.152** 🥇 |
| Option 3 (Soft Scaling Only) | 39.99% | -18.84% | 2.174 |
| Option 1 (Hysteresis Buffer Only) | 37.80% | -23.19% | 1.963 |

## 🧠 Quantitative Takeaway
1. **Hysteresis (Option 1) Fail:** By delaying exit during market drops (requiring Nifty to crash -1.5% below EMA), Hysteresis forces the portfolio to **absorb the worst part of every crash** while long high-beta momentum stocks. This doubled drawdowns (e.g. -24.49% vs -13.83% over 3 years) and destroyed CAGR.
2. **Soft Scaling (Option 3) Drag:** Keep a partial exposure to long stocks during breakdowns. In India's fast-dropping markets, an immediate binary 'all-out' switch acts as a superior circuit breaker, proving that whipsaw noise costs less than delayed protection.
