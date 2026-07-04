# Strategy Operational Manual: V2 Option A + Nifty 50-EMA Circuit Breaker

This manual documents the mathematical framework and execution rules of the two active trading systems running in this repository.

---

## 1. Core Architecture (V2 Option A: Regime-Adaptive Momentum)

The strategy automatically switches its stock selection filters based on the current regime of the broader market.

### A. Market Regime Classifier (GMM)
Every week, the system runs a **Gaussian Mixture Model (GMM)** clustering algorithm on the trailing 20-day returns and volatility of the index (SENSEX/Nifty 50). It classifies the current market into one of three regimes:
1. **Bullish Regime** (High average returns, low/stable volatility)
2. **Choppy/Sideways Regime** (Stable/flat returns, moderate volatility)
3. **Bearish Regime** (Negative average returns, high volatility)

### B. Stock Selection & Scoring Filters
Depending on the classified regime, the strategy scores and ranks the 40-stock universe:

* **In a Bullish Regime**:
  * *Condition*: Only buy/hold stocks where the **Supertrend (10, 3.0)** is green (indicating an active medium-term uptrend).
  * *Scoring*: Rank the qualified stocks by their trailing **20-day returns** (high momentum).
* **In a Choppy Regime**:
  * *Condition*: Only buy/hold stocks trading below their **Bollinger Band (20, 2.0) Upper Limit** (to avoid buying at resistance).
  * *Scoring*: Rank stocks by distance to the upper band: `(BB_Upper - Price) / Price` (targeting mean-reversion).
* **In a Bearish Regime**:
  * *No trades are made* inside the core stock selection pool.

### C. Softmax Capital Allocation
Once scored, the strategy distributes capital using a **Softmax Weighting** algorithm. This ensures that capital is concentrated in the highest-scoring stocks while preventing single-stock risk by distributing minor fractions of capital to other high-ranking candidates.

---

## 2. Risk Management (The Nifty 50-EMA Circuit Breaker)

While the GMM handles stock rotation, the **EMA-50 Switch** is our structural safety belt:

* **Trigger**: Every day at market close, the script compares the close price of the **Nifty 50 Index (`^NSEI`)** to its **50-day Exponential Moving Average (EMA)**.
* **Emergency Exit (Below 50-EMA)**:
  * The portfolio immediately sells all active stock holdings at the market close, rotating **100% of capital into Cash**.
  * No new buy orders are allowed until the index climbs back above the 50-day EMA.
* **Risk-On (Above 50-EMA)**:
  * The strategy runs its normal weekly GMM rebalancing.

---

## 3. Daily Execution Schedule

Both strategies run sequentially inside GitHub Actions every Monday through Friday at **3:45 PM IST (10:15 AM UTC)**, immediately after the Indian market closes.
* **`paper_trader.py`** executes the V2_A strategy without the safety switch.
* **`paper_trader_strat_bullet_proof.py`** executes the V2_A strategy with the Nifty 50-EMA circuit breaker.
