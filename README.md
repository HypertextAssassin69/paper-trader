# Paper Trader — Version 2.0 Option A
### Regime-Aware Softmax Portfolio · Live on Real NSE Data · Starting Capital: ₹1,00,000

---

## What This Does
Every weekday at **3:45 PM IST**, a GitHub Actions cloud server automatically:
1. Downloads today's closing prices for your 10 stocks from NSE.
2. Runs the **Version 2.0 Option A** strategy (Supertrend + HMA Hugging Bollinger Bands).
3. Determines which stocks to buy/sell and at what size.
4. Updates the portfolio state, trade log, and performance report.
5. Commits everything back to this repo.

You just open `paper_trade_report.md` to see how you would have done today — no laptop needed.

---

## Your Stock Universe
| Ticker | Company | Sector |
|:---|:---|:---|
| RELIANCE.NS | Reliance Industries | Conglomerate |
| TCS.NS | Tata Consultancy Services | IT |
| HDFCBANK.NS | HDFC Bank | Banking |
| HINDUNILVR.NS | Hindustan Unilever | FMCG |
| MARUTI.NS | Maruti Suzuki | Auto |
| SUNPHARMA.NS | Sun Pharmaceutical | Pharma |
| LT.NS | Larsen & Toubro | Infrastructure |
| TATASTEEL.NS | Tata Steel | Metals |
| ULTRACEMCO.NS | UltraTech Cement | Cement |
| BHARTIARTL.NS | Bharti Airtel | Telecom |

---

## Files in This Repo
| File | What It Contains |
|:---|:---|
| `paper_trader.py` | Main strategy script (runs daily) |
| `portfolio_state.json` | Live holdings, cash, entry prices |
| `paper_trade_log.csv` | Every BUY/SELL ever made since Day 1 |
| `daily_pnl.csv` | Daily portfolio value history |
| `paper_trade_report.md` | **Human-readable daily report (open this!)** |
| `pnl_chart.png` | Portfolio growth chart |
| `.github/workflows/run_paper_trader.yml` | Auto-schedule config |

---

## One-Time Setup (Do This Once)

### Step 1: Create a GitHub Account
Go to [github.com](https://github.com) and sign up for a free account.

### Step 2: Create a New Repository
- Click **New repository**
- Name it `paper-trader` (or anything you like)
- Set it to **Public** (required for free GitHub Actions minutes)
- Do NOT initialise with README (we already have one)

### Step 3: Push This Folder to GitHub
Open Command Prompt inside `D:\AIML\stock\paper_trader\` and run:
```cmd
git init
git add .
git commit -m "Initial paper trader setup"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/paper-trader.git
git push -u origin main
```
Replace `YOUR_USERNAME` with your actual GitHub username.

### Step 4: Enable GitHub Actions
- Go to your repo on GitHub
- Click the **Actions** tab
- If prompted, click **"I understand my workflows, go ahead and enable them"**

### Step 5: Do a Manual Test Run
- In the Actions tab, click **"Paper Trader — Daily Run"**
- Click **"Run workflow"** → **"Run workflow"**
- Wait ~2 minutes, then refresh the repo
- You should see `paper_trade_report.md` updated with today's signals!

### Step 6: Sit Back — It Runs Itself From Now On
Every weekday at 3:45 PM IST, GitHub runs it automatically. You just check the report.

---

## Running Locally (Optional)
If you want to run it manually on your PC:
```cmd
cd D:\AIML\stock\paper_trader
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python paper_trader.py
```

---

## Strategy Parameters (Edit in paper_trader.py)
| Parameter | Default | What It Controls |
|:---|:---:|:---|
| `START_CAPITAL` | 100,000 | Starting paper money (INR) |
| `TICKERS` | 10 NSE stocks | Your stock universe |
| `SUPERTREND_PERIOD` | 10 | Supertrend lookback period |
| `SUPERTREND_MULT` | 3.0 | Supertrend ATR multiplier |
| `HMA_PERIOD` | 20 | HMA center line period |
| `CHOPPY_RSI_LIMIT` | 45 | Max RSI for choppy buy signal |
| `FEE_RATE` | 0.001 | Simulated brokerage (0.1%) |
