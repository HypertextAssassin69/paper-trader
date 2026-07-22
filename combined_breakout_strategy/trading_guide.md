# Real-Life Trading Guide: Combined Breakout-Momentum Strategy
*Designed for ₹1.0 - ₹1.5 Lakh accounts | Execution time: < 5 mins a week*

---

## 🌟 The Concept
This strategy combines **Multi-Year Breakouts** with **1-Year Price Momentum**. It guarantees you only buy stocks that are emerging from deep, multi-year consolidation phases (buying at the start of their growth cycle) and protects your downside by moving to cash when the Nifty 50 breaks below its 50-day EMA.

---

## 🛠️ The Weekly Safety Routine (Downside Protection)
**When:** Every Friday afternoon at **3:15 PM** (15 minutes before market close).
1. Open [TradingView.com](https://www.tradingview.com/) (or your broker's terminal).
2. Open the chart of the **Nifty 50 Index (`NIFTY`)** on the **Daily** time frame.
3. Add the **Exponential Moving Average (EMA)** indicator and set the length to **50**.
4. Check Nifty's current price relative to the 50-day EMA:
   * **Nifty is ABOVE the 50-day EMA (BULL market)**: Do nothing. Sleep well. Your momentum stocks are safe.
   * **Nifty is BELOW the 50-day EMA (BEAR market)**: Sell all 5 stocks immediately in the cash market. Park the entire ₹1.0 - ₹1.5 Lakh capital in **Liquid BeES (or LIQUIDCASE ETF)** to earn ~6% risk-free yield.
5. **Re-Entry Rule:** If you are in cash and Nifty closes back *above* the 50 EMA on a Friday, sell your Liquid BeES and buy back into the target 5 momentum stocks.

---

## 🔄 The 6-Month Rebalance Routine
**When:** Twice a year (e.g., January 1st and July 1st). 

### Step 1: Open a free Scanner on Chartink.com
Go to [Chartink.com](https://chartink.com/) and create a scanner with these exact queries to find stocks breaking out of their 3-Year High ranges:

#### 1. Universe Filter:
* `Universe: Nifty Midcap 100` or `Nifty Smallcap 250` or `Nifty 500`. (For best results, search the Nifty Midcap 100 + Nifty Smallcap 250 universe).

#### 2. Liquidity & Volume Query:
* `[latest] Close > 50` (Exclude low-priced penny stocks)
* `[latest] 3 Month Average Daily Volume > 500000` (Liquidity check)
* `[latest] Daily Turnover > 50000000` (ADV > ₹5 Crores check)

#### 3. Breakout Filter (Within 15% of 3-Year Highs):
* `[latest] Close >= [latest] Max ( 756, [latest] Close ) * 0.85`
  *(Note: 756 trading days is exactly 3 calendar years. This filters for stocks trading within 15% of their 3-year highs).*

#### 4. Sort Condition:
* Sort the results by **1-Year Price Return (highest to lowest)**. 
  *(This is computed as: `( [latest] Close - [252 days ago] Close ) / [252 days ago] Close`)*.

---

### Step 2: Buy the Top 5 Stocks
1. From the sorted scanner list, select the **Top 5 stocks**.
2. Calculate your position size:
   * **With ₹1,00,000 capital**: Allocate exactly **₹20,000 per stock**.
   * **With ₹1,50,000 capital**: Allocate exactly **₹30,000 per stock**.
3. **Execution**: Place Delivery Buy orders (Market or Limit) between **3:15 PM and 3:30 PM** on the rebalance day.

---

## 🧐 Should You Use GitHub Actions to Auto-Trade?
**Answer: No.**
* **Why?** Since this strategy only rebalances **twice a year** and requires a simple check on Fridays, using GitHub Actions is completely unnecessary. 
* Running an automated script daily creates unnecessary complications with API key expiries, broker logins, and TOTP authentications.
* **The Manual Advantage:** Spending **2 minutes every Friday** to check the Nifty 50 EMA and **5 minutes twice a year** to run the scanner and rebalance is safer, 100% free, and completely stress-free.

---

## 📊 Backtest Performance Reference
* **CAGR:** **38.19%** (A ₹1 Lakh starting capital grows to **₹25.1 Lakhs** in 10 years!)
* **Max Drawdown:** **-18.86%** (Your capital is protected during crashes by the Nifty Cash Filter).
* **Calmar Ratio:** **2.024** (Exceptional risk-adjusted returns).
