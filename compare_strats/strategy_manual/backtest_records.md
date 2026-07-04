# Strategy Historical Backtest Records (7.5-Year & 30-Year)

This document contains the verified backtest records for the **V2 Option A (No-Stops)** and the **V2 Option A (Nifty 50-EMA Circuit Breaker)** strategies.

---

## 1. 30-Year Long-Term Backtest (1996–2026)

* **Horizon**: January 1, 1996 to July 1, 2026
* **Starting Capital**: INR 100,000
* **Universe**: 40 Nifty Large/Mid-Cap Stocks (listed dynamically)
* **Index Proxy**: BSE SENSEX (`^BSESN`)
* **Adjustment**: Fully split, dividend, and demerger-adjusted price series (`auto_adjust=False` + scaled OHLC).

### 📊 Performance Summary (30-Year)

| Metric | V2_A (No-Stops Baseline) | V2_A (Macro Circuit Breaker) |
| :--- | :---: | :---: |
| **Final Portfolio Value** | **INR 8.09 Crores** | **INR 2.84 Crores** |
| **Total Return** | +80,848.07% | +28,392.67% |
| **CAGR (Annual Compounding)** | **25.98%** | **21.52%** |
| **Sharpe Ratio** | 0.305 | **0.988** (Near Perfect) |
| **Max Drawdown (Worst Loss)** | **-89.39%** (2008 Lehman Crash) | **-21.39%** (Protected) |

### 🔍 Key Takeaway
The **Circuit Breaker** cut the maximum drawdown from a devastating **-89%** down to just **-21%** over three decades. It sacrificed a minor portion of the upside (21.52% CAGR vs. 25.98% CAGR) in exchange for exceptional capital protection and a massive increase in risk-adjusted performance (Sharpe Ratio of 0.988).

---

## 2. 20-Year Mid-Term Backtest (2006–2026)

* **Horizon**: January 1, 2006 to July 1, 2026
* **Starting Capital**: INR 100,000
* **Universe**: 40 Nifty Large/Mid-Cap Stocks (listed dynamically)
* **Index Proxy**: Nifty 50 Index (`^NSEI`)

### 📊 Performance Summary (20-Year)

| Metric | V2_A (No-Stops Baseline) | V2_A (Macro Circuit Breaker) |
| :--- | :---: | :---: |
| **Final Portfolio Value** | **INR 25.74 Lakhs** | **INR 22.17 Lakhs** |
| **Total Return** | +2,474.34% | +2,117.75% |
| **CAGR** | **17.18%** | **16.33%** |
| **Sharpe Ratio** | 0.624 | **0.695** |
| **Max Drawdown** | **-52.70%** | **-29.92%** |

### 🔍 Key Takeaway
Over the 20-year horizon, the performance gap narrows further. The Circuit Breaker strategy compounds at **16.33% CAGR** (almost identical to the 17.18% CAGR of the baseline) while successfully capping the maximum drawdown at **-29.92%** instead of **-52.70%**.
