"""
paper_trader.py  —  Nifty 40-Stock Systematic Portfolio (V2 Option A - No Stops)
Daily Automated Paper Trader running on GitHub Actions
"""

import os, json, csv, datetime, warnings
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.mixture import GaussianMixture
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "HINDUNILVR.NS", "MARUTI.NS", 
    "SUNPHARMA.NS", "LT.NS", "TATASTEEL.NS", "ULTRACEMCO.NS", "BHARTIARTL.NS",
    "NTPC.NS", "DLF.NS", "BEL.NS", "TRENT.NS", "PIDILITIND.NS", 
    "HAL.NS", "TITAN.NS", "COALINDIA.NS", "CONCOR.NS", "DIXON.NS",
    "SBIN.NS", "INDIGO.NS", "BPCL.NS", "IREDA.NS", "LTIM.NS", 
    "APOLLOHOSP.NS", "ZOMATO.NS", "POLYCAB.NS", "LALPATHLAB.NS", "VOLTAS.NS",
    "ICICIBANK.NS", "M&M.NS", "JSWSTEEL.NS", "ADANIENT.NS", "MUTHOOTFIN.NS",
    "PAGEIND.NS", "CIPLA.NS", "BRITANNIA.NS", "AUBANK.NS", "TATACOMM.NS"
]

INDEX_TICKER          = "^NSEI" # Nifty 50 Index
START_CAPITAL         = 100_000.0
def calculate_fee(trade_value):
    return min(0.0005 * trade_value, 20.0)

WARMUP_DAYS           = 280

STATE_FILE  = "states/portfolio_nostops.json"
PNL_FILE    = "data/pnl_nostops.csv"
LOG_FILE    = "data/trades_nostops.csv"
CHART_FILE  = "charts/pnl_nostops.png"
REPORT_FILE = "reports/report_nostops.md"

# ─────────────────────────────────────────────────────────────────────────────
#  INDICATORS
# ─────────────────────────────────────────────────────────────────────────────
def _atr(df, n=14):
    c = df['Close'].shift(1)
    tr = pd.concat([df['High'] - df['Low'],
                    (df['High'] - c).abs(),
                    (df['Low'] - c).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def _supertrend(df, n=10, m=3.0):
    atr = _atr(df, n)
    hl2 = (df['High'] + df['Low']) / 2
    bu = hl2 + m * atr
    bl = hl2 - m * atr
    fu, fl = bu.copy(), bl.copy()
    close = df['Close']
    for i in range(n, len(df)):
        fu.iloc[i] = bu.iloc[i] if (bu.iloc[i] < fu.iloc[i-1] or close.iloc[i-1] > fu.iloc[i-1]) else fu.iloc[i-1]
        fl.iloc[i] = bl.iloc[i] if (bl.iloc[i] > fl.iloc[i-1] or close.iloc[i-1] < fl.iloc[i-1]) else fl.iloc[i-1]
    st = pd.Series(np.nan, index=df.index)
    dir_ = pd.Series(1, index=df.index)
    for i in range(n, len(df)):
        if close.iloc[i] > fu.iloc[i-1]:
            dir_.iloc[i] = 1
        elif close.iloc[i] < fl.iloc[i-1]:
            dir_.iloc[i] = -1
        else:
            dir_.iloc[i] = dir_.iloc[i-1]
        st.iloc[i] = fl.iloc[i] if dir_.iloc[i] == 1 else fu.iloc[i]
    return st, dir_

def _hma(s, n):
    w1 = s.ewm(span=n//2, adjust=False).mean()
    w2 = s.ewm(span=n, adjust=False).mean()
    diff = 2 * w1 - w2
    return diff.ewm(span=int(np.sqrt(n)), adjust=False).mean()

def _bollinger_bands(df, n=20, m=2.0):
    mid = _hma(df['Close'], n)
    std = df['Close'].rolling(n).std()
    upper = mid + m * std
    lower = mid - m * std
    return upper, lower

def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

# ─────────────────────────────────────────────────────────────────────────────
#  STATE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
def load_state():
    os.makedirs("states", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    os.makedirs("charts", exist_ok=True)
    
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "cash": START_CAPITAL,
        "holdings": {},
        "start_date": str(datetime.date.today()),
        "start_capital": START_CAPITAL,
        "last_run": None
    }

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def append_pnl(date, val, cash):
    exists = os.path.exists(PNL_FILE)
    with open(PNL_FILE, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['date', 'portfolio_value', 'cash'])
        if not exists: w.writeheader()
        w.writerow({'date': date, 'portfolio_value': round(val, 2), 'cash': round(cash, 2)})

def append_trades(rows):
    if not rows: return
    exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['date', 'ticker', 'action', 'shares', 'price', 'value', 'reason'])
        if not exists: w.writeheader()
        w.writerows(rows)

# ─────────────────────────────────────────────────────────────────────────────
#  RUNNER
# ─────────────────────────────────────────────────────────────────────────────
def main():
    today = str(datetime.date.today())
    print(f"\n==================================================")
    print(f"  Live Baseline No-Stops Systematic Trader | {today}")
    print(f"==================================================")

    state = load_state()
    end_dt = datetime.date.today() + datetime.timedelta(days=1)
    start_dt = datetime.date.today() - datetime.timedelta(days=WARMUP_DAYS+30)

    # 1. Check Nifty 50 Index for Regime classification
    print("Checking Nifty 50 index state...")
    nifty = yf.download(INDEX_TICKER, start=str(start_dt), end=str(end_dt), auto_adjust=False, progress=False)
    if not nifty.empty:
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        nifty = nifty.dropna(subset=['Adj Close'])
        
    if nifty.empty:
        print("  [WARN] Failed to download index data. Defaulting to Bullish regime.")
        regime = "Bullish"

    else:
        nifty['Close'] = nifty['Adj Close']
        nifty['Ret_20'] = nifty['Close'].pct_change(20)
        nifty['Vol_20'] = nifty['Close'].pct_change().rolling(20).std()
        
        last_row = nifty.iloc[-1]
        
        # Train GMM on the warmup slice to determine current regime
        nifty_clean = nifty[['Ret_20', 'Vol_20']].dropna()
        gmm = GaussianMixture(n_components=3, random_state=42)
        gmm.fit(nifty_clean)
        
        means = gmm.means_
        bull_state = np.argmax(means[:, 0])
        bear_state = np.argmin(means[:, 0])
        
        state_pred = gmm.predict([[last_row['Ret_20'], last_row['Vol_20']]])[0]
        regime = "Bullish" if state_pred == bull_state else ("Bearish" if state_pred == bear_state else "Choppy")

    print(f"  Predicted Market Regime: {regime}")

    # 2. Download ticker database
    ticker_data = {}
    current_prices = {}
    for t in TICKERS:
        df = yf.download(t, start=str(start_dt), end=str(end_dt), auto_adjust=False, progress=False)
        if df.empty or len(df) < 50:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Adj Close'])
        if df.empty or len(df) < 50:
            continue
            
        # Scale OHLC to use Adj Close
        adj_ratio = df['Adj Close'] / df['Close']
        df['Open'] *= adj_ratio
        df['High'] *= adj_ratio
        df['Low'] *= adj_ratio
        df['Close'] = df['Adj Close']
        
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df['ST_Dir'] = _supertrend(df)[1]
        df['BB_Upper'], df['BB_Lower'] = _bollinger_bands(df)
        df['Ret_20'] = df['Close'].pct_change(20)
        
        ticker_data[t] = df
        current_prices[t] = df['Close'].iloc[-1]

    # 3. Process Trades
    trade_rows = []
    
    # Calculate current holdings asset value
    assets_val = sum(info['shares'] * current_prices.get(t, info['avg_price']) for t, info in state['holdings'].items())
    equity = state['cash'] + assets_val
    print(f"  Current cash: INR {state['cash']:,.2f}   Assets: INR {assets_val:,.2f}   Equity: INR {equity:,.2f}")

    # Calculate target weights via Softmax normally (No Stops Circuit Breaker is active here)
    scores = {}
    for t, df in ticker_data.items():
        row = df.iloc[-1]
        price = row['Close']
        
        if regime == "Bullish":
            if row['ST_Dir'] == 1:
                scores[t] = row['Ret_20']
        elif regime == "Choppy":
            if price < row['BB_Upper']:
                scores[t] = (row['BB_Upper'] - price) / price

    target_weights = {t: 0.0 for t in TICKERS}
    if scores:
        ticks = list(scores.keys())
        vals = np.array([scores[x] for x in ticks])
        exp_vals = np.exp(vals - np.max(vals))
        weights = exp_vals / np.sum(exp_vals)
        for t, w in zip(ticks, weights):
            target_weights[t] = w

    # Execute Rebalance Trades
    # 1. Sells First (to free up cash)
    for t in TICKERS:
        df = ticker_data.get(t)
        if df is not None:
            price = current_prices[t]
            target_shares = int(equity * target_weights.get(t, 0.0) / price)
            current_shares = int(state['holdings'].get(t, {}).get('shares', 0))
            
            if target_shares < current_shares:
                shares_to_sell = current_shares - target_shares
                val_to_sell = shares_to_sell * price
                state['cash'] += val_to_sell - calculate_fee(val_to_sell)
                
                state['holdings'][t]['shares'] = target_shares
                trade_rows.append({
                    'date': today, 'ticker': t, 'action': 'SELL',
                    'shares': int(shares_to_sell), 'price': round(price, 2),
                    'value': round(val_to_sell, 2), 'reason': f'Rebalance to target weight={target_weights.get(t,0.0):.3f}'
                })
                print(f"    [SELL] {t} @ INR {price:.2f} (reducing exposure)")
                if state['holdings'][t]['shares'] <= 0:
                    del state['holdings'][t]

    # 2. Buys Second (to acquire positions using available cash)
    for t in TICKERS:
        df = ticker_data.get(t)
        if df is not None:
            price = current_prices[t]
            target_shares = int(equity * target_weights.get(t, 0.0) / price)
            current_shares = int(state['holdings'].get(t, {}).get('shares', 0))
            
            if target_shares > current_shares:
                shares_to_buy = target_shares - current_shares
                cost = (shares_to_buy * price) + calculate_fee(shares_to_buy * price)
                
                # Check for cash constraints and adjust shares down if necessary
                while cost > state['cash'] and shares_to_buy > 0:
                    shares_to_buy -= 1
                    cost = (shares_to_buy * price) + calculate_fee(shares_to_buy * price)
                
                if shares_to_buy > 0:
                    state['cash'] -= cost
                    
                    if t not in state['holdings']:
                        state['holdings'][t] = {'shares': 0, 'avg_price': price, 'entry_date': today}
                    
                    old_shares = state['holdings'][t]['shares']
                    old_price = state['holdings'][t]['avg_price']
                    state['holdings'][t]['shares'] += shares_to_buy
                    state['holdings'][t]['avg_price'] = (old_shares * old_price + shares_to_buy * price) / state['holdings'][t]['shares']
                    
                    trade_rows.append({
                        'date': today, 'ticker': t, 'action': 'BUY',
                        'shares': int(shares_to_buy), 'price': round(price, 2),
                        'value': round(shares_to_buy * price, 2), 'reason': f'Rebalance to target weight={target_weights.get(t,0.0):.3f}'
                    })
                    print(f"    [BUY] {t} @ INR {price:.2f} (acquiring exposure)")


    # 4. Save States & Log PNL
    assets_final = sum(info['shares'] * current_prices.get(t, info['avg_price']) for t, info in state['holdings'].items())
    equity_final = state['cash'] + assets_final
    state['last_run'] = today
    
    save_state(state)
    append_trades(trade_rows)
    append_pnl(today, equity_final, state['cash'])

    # 5. Generate daily chart
    pnl_df = pd.read_csv(PNL_FILE, parse_dates=['date'])
    if len(pnl_df) >= 2:
        fig, ax = plt.subplots(figsize=(13, 4.5))
        dates = pd.to_datetime(pnl_df['date'])
        vals = pnl_df['portfolio_value'].values
        ax.plot(dates, vals, color='#3498db', linewidth=2.2, label='No-Stops Portfolio (100k)')
        ax.axhline(START_CAPITAL, color='#e74c3c', linestyle=':', alpha=0.6)
        ax.set_title(f"No-Stops Live PnL | as of {today}", fontsize=12, fontweight='bold')
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"INR {x:,.0f}"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        ax.grid(True, linestyle=':', alpha=0.5)
        plt.tight_layout()
        plt.savefig(CHART_FILE, dpi=150)
        plt.close()

    # 6. Generate report
    total_ret = (equity_final - START_CAPITAL) / START_CAPITAL * 100
    days_live = (pd.to_datetime(today) - pd.to_datetime(state['start_date'])).days
    
    lines = []
    lines.append(f"# Live Baseline No-Stops Systematic Portfolio Report\n")
    lines.append(f"> **Date**: {today}  |  **Days Live**: {days_live}  |  **Portfolio Mode**: Always Fully Invested\n")

    lines.append(f"## Summary Stats")
    lines.append(f"| Metric | Value |")
    lines.append(f"| :--- | :---: |")
    lines.append(f"| Starting Capital | **INR {START_CAPITAL:,.2f}** |")
    lines.append(f"| Current Value | **INR {equity_final:,.2f}** |")
    lines.append(f"| Total Return | **{total_ret:+.2f}%** |\n")
    
    lines.append(f"## Current Active Holdings")
    lines.append(f"| Ticker | Shares | Entry Price | Current Price | Unrealised PnL |")
    lines.append(f"| :--- | :---: | :---: | :---: | :---: |")
    for t, info in state['holdings'].items():
        curr_p = current_prices.get(t, info['avg_price'])
        pnl = (curr_p - info['avg_price']) / info['avg_price'] * 100
        lines.append(f"| {t} | {info['shares']:.4f} | INR {info['avg_price']:.2f} | INR {curr_p:.2f} | **{pnl:+.2f}%** |")
    lines.append(f"\n**Cash on hand**: INR {state['cash']:,.2f}\n")
    
    if os.path.exists(CHART_FILE):
        lines.append(f"## Live PnL Chart")
        lines.append(f"![No-Stops PnL Chart](../{CHART_FILE})\n")
        
    if os.path.exists(LOG_FILE):
        tdf = pd.read_csv(LOG_FILE)
        lines.append(f"## Recent Trade Log (Last 15)")
        lines.append(f"| Date | Ticker | Action | Shares | Price | Value | Reason |")
        lines.append(f"| :--- | :--- | :--- | :---: | :---: | :---: | :--- |")
        for _, r in tdf.tail(15).iloc[::-1].iterrows():
            lines.append(f"| {r['date']} | {r['ticker']} | **{r['action']}** | {r['shares']:.4f} | INR {r['price']:.2f} | INR {r['value']:.2f} | {r['reason']} |")
            
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
        
    print(f"Daily update done. Current value: INR {equity_final:,.2f}")

if __name__ == "__main__":
    main()
