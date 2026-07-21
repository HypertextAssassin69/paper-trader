# 📊 ADX Trend-Filtered Regime Switching Audit
*Comparative study of baseline binary switching vs. ADX trend-strength gatekeeper*

> [!IMPORTANT]
> The ADX Trend-Filtered Switcher ignores crossovers if India Nifty 50-day ADX is below 20 (weak trend) to prevent whipsaw noise.

## 📈 Comparative Results Table
### 📅 Horizon: 3-Year (to July 2026)
| Regime Switcher | CAGR % | Max Drawdown % | Sharpe Ratio |
| :--- | :---: | :---: | :---: |
| **Standard Binary (Base)** | **4.01%** | **-13.83%** | **0.322** 🥇 |
| ADX Trend-Filtered | 4.19% | -26.65% | 0.274 |

### 📅 Horizon: 5-Year (to July 2026)
| Regime Switcher | CAGR % | Max Drawdown % | Sharpe Ratio |
| :--- | :---: | :---: | :---: |
| **Standard Binary (Base)** | **28.28%** | **-10.98%** | **1.687** 🥇 |
| ADX Trend-Filtered | 12.72% | -26.54% | 0.632 |

### 📅 Horizon: 10-Year (to July 2026)
| Regime Switcher | CAGR % | Max Drawdown % | Sharpe Ratio |
| :--- | :---: | :---: | :---: |
| **Standard Binary (Base)** | **37.42%** | **-11.46%** | **2.111** 🥇 |
| ADX Trend-Filtered | 28.59% | -40.33% | 1.233 |

### 📅 Horizon: 15-Year (to July 2026)
| Regime Switcher | CAGR % | Max Drawdown % | Sharpe Ratio |
| :--- | :---: | :---: | :---: |
| **Standard Binary (Base)** | **41.85%** | **-14.56%** | **2.152** 🥇 |
| ADX Trend-Filtered | 30.71% | -37.68% | 1.333 |

## 🔍 Deep Dive Quantitative Analysis
1. **The Volatility Blindspot:** ADX is a lagging indicator. When a fast market crash starts, it starts from a low-volatility state where ADX is very low (< 20). Because ADX is low, the filter **blocks the strategy from exiting**, trapping the portfolio in long momentum stocks while the market plummets.
2. **Catastrophic Drawdowns:** Over the 10-year horizon, the ADX filter caused the max drawdown to spike to **-40.33%** (compared to only **-11.46%** in the base model). This destroyed the CAGR by 8.82%.
