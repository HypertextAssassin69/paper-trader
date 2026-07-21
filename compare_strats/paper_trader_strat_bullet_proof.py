import os, json, csv, datetime, warnings
import numpy as np
import pandas as pd
import yfinance as yf
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

STATE_FILE  = "states/portfolio_bulletproof.json"
PNL_FILE    = "data/pnl_bulletproof.csv"
LOG_FILE    = "data/trades_bulletproof.csv"
CHART_FILE  = "charts/pnl_bulletproof.png"
REPORT_FILE = "reports/report_bulletproof.md"

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
    print(f"  Live Bulletproof Systematic Trader | {today}")
    print(f"==================================================")

    state = load_state()
    end_dt = datetime.date.today() + datetime.timedelta(days=1)
    start_dt = datetime.date.today() - datetime.timedelta(days=400) # Increased to 400 days for stable EMA-200 calculation

    # 1. Check Nifty 50 Index & Macro Switch
    print("Checking Nifty 50 index state...")
    nifty = yf.download(INDEX_TICKER, start=str(start_dt), end=str(end_dt), auto_adjust=False, progress=False)
    if not nifty.empty:
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        nifty = nifty.dropna(subset=['Adj Close'])
        
    if nifty.empty:
        print("  [WARN] Failed to download index data. Defaulting to Bullish regime.")
        is_nifty_bullish = True
        regime = "Bullish"
    else:
        nifty['Close'] = nifty['Adj Close']
        
        # Calculate Heuristic Features
        nifty['EMA_50'] = nifty['Close'].ewm(span=50, adjust=False).mean()
        nifty['EMA_200'] = nifty['Close'].ewm(span=200, adjust=False).mean()
        
        # Calculate ADX (14)
        nifty_high = nifty['High']
        nifty_low = nifty['Low']
        nifty_close = nifty['Close']
        nifty_close_prev = nifty_close.shift(1)
        
        tr1 = nifty_high - nifty_low
        tr2 = (nifty_high - nifty_close_prev).abs()
        tr3 = (nifty_low - nifty_close_prev).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        high_diff = nifty_high - nifty_high.shift(1)
        low_diff = nifty_low.shift(1) - nifty_low
        
        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
        
        tr_smooth = tr.ewm(alpha=1/14, adjust=False).mean()
        plus_dm_smooth = pd.Series(plus_dm, index=nifty.index).ewm(alpha=1/14, adjust=False).mean()
        minus_dm_smooth = pd.Series(minus_dm, index=nifty.index).ewm(alpha=1/14, adjust=False).mean()
        
        plus_di = 100 * (plus_dm_smooth / tr_smooth)
        minus_di = 100 * (minus_dm_smooth / tr_smooth)
        
        di_sum = plus_di + minus_di
        di_diff = (plus_di - minus_di).abs()
        dx = 100 * np.where(di_sum == 0, 0, di_diff / di_sum)
        nifty['ADX_Fast'] = pd.Series(dx, index=nifty.index).ewm(alpha=1/14, adjust=False).mean()
        
        # Classify raw regimes daily
        raw_regimes = []
        for idx, row in nifty.iterrows():
            adx_val = row['ADX_Fast']
            ema_50_val = row['EMA_50']
            ema_200_val = row['EMA_200']
            close_val = row['Close']
            
            if adx_val < 18.0:
                raw_regimes.append('Choppy')
            else:
                if close_val > ema_50_val and ema_50_val > ema_200_val:
                    raw_regimes.append('Bullish')
                elif close_val < ema_50_val and ema_50_val < ema_200_val:
                    raw_regimes.append('Bearish')
                else:
                    raw_regimes.append('Choppy')
                    
        nifty['Raw_Regime'] = raw_regimes
        
        # Apply 51-day rolling mode smoothing (center=False for real-time live execution)
        mapping = {'Choppy': 0, 'Bullish': 1, 'Bearish': 2}
        inv_mapping = {0: 'Choppy', 1: 'Bullish', 2: 'Bearish'}
        temp_int = nifty['Raw_Regime'].map(mapping)
        
        def get_mode(x):
            vals, counts = np.unique(x, return_counts=True)
            return vals[np.argmax(counts)]
            
        smoothed_int = temp_int.rolling(window=51, min_periods=1, center=False).apply(get_mode, raw=True)
        nifty['Regime'] = smoothed_int.map(inv_mapping)
        
        regime = nifty['Regime'].iloc[-1]
        last_row = nifty.iloc[-1]
        is_nifty_bullish = last_row['Close'] >= last_row['EMA_50']

    print(f"  Nifty 50 Status: {'ABOVE EMA-50' if is_nifty_bullish else 'BELOW EMA-50 (Emergency Exit)'}")
    print(f"  Predicted Market Regime (Heuristic): {regime}")

    # 2. Download ticker database
    ticker_data = {}
    current_prices = {}
    for t in TICKERS:
        df = yf.download(t, start=str(start_dt), end=str(end_dt), auto_adjust=False, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=['Adj Close'])
            
        if df.empty or len(df) < 50:
            continue
            
        # Scale OHLC to use Adj Close
        adj_ratio = df['Adj Close'] / df['Close']
        df['Open'] = df['Open'] * adj_ratio
        df['High'] = df['High'] * adj_ratio
        df['Low'] = df['Low'] * adj_ratio
        df['Close'] = df['Adj Close']
        
        # Add core indicators
        df['Ret_20'] = df['Close'].pct_change(20)
        df['ST_Val'], df['ST_Dir'] = _supertrend(df, 10, 3.0)
        df['BB_Upper'], df['BB_Lower'] = _bollinger_bands(df, 20, 2.0)
        
        ticker_data[t] = df
        current_prices[t] = df['Close'].iloc[-1]

    # 3. Process Trades
    trade_rows = []
    
    # Calculate current holdings asset value
    assets_val = sum(info['shares'] * current_prices.get(t, info['avg_price']) for t, info in state['holdings'].items())
    equity = state['cash'] + assets_val
    print(f"  Current cash: INR {state['cash']:,.2f}   Assets: INR {assets_val:,.2f}   Equity: INR {equity:,.2f}")

    # Handle Macro Switch Emergency liquidation
    if not is_nifty_bullish:
        print("  [ALERT] Nifty 50 broke below 50-EMA! Flushing all holdings to Cash.")
        for t, info in list(state['holdings'].items()):
            price = current_prices.get(t, info['avg_price'])
            trade_val = int(info['shares']) * price
            val = trade_val - calculate_fee(trade_val)
            state['cash'] += val
            trade_rows.append({
                'date': today, 'ticker': t, 'action': 'SELL',
                'shares': int(info['shares']), 'price': round(price, 2),
                'value': round(val, 2), 'reason': 'Nifty EMA-50 Circuit Breaker'
            })
            print(f"    [SELL] {t} @ INR {price:.2f}")
        state['holdings'] = {}

    else:
        # Calculate target weights via Softmax normally
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
                    
                    # Check for cash constraints and adjust buy shares down if necessary
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
        ax.plot(dates, vals, color='#1abc9c', linewidth=2.2, label='Bulletproof Portfolio (100k)')
        ax.axhline(START_CAPITAL, color='#e74c3c', linestyle=':', alpha=0.6)
        ax.set_title(f"Bulletproof Live PnL | as of {today}", fontsize=12, fontweight='bold')
        ax.set_ylabel("Portfolio Value (INR)", fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.legend(loc='upper left', fontsize=9)
        plt.tight_layout()
        plt.savefig(CHART_FILE, dpi=150)
        plt.close()

    # 6. Generate detailed markdown report
    days_live = len(pnl_df)
    report_rows = []
    report_rows.append(f"# Live Bulletproof Systematic Portfolio Report (EMA-50 Switch)\n")
    report_rows.append(f"> **Date**: {today}  |  **Days Live**: {days_live}  |  **Nifty Index Switch**: {'Risk-On' if is_nifty_bullish else 'Risk-Off (Cash)'}\n")
    report_rows.append(f"## Summary Stats")
    report_rows.append(f"| Metric | Value |")
    report_rows.append(f"| :--- | :---: |")
    report_rows.append(f"| Starting Capital | INR {START_CAPITAL:,.2f} |")
    report_rows.append(f"| Current Portfolio Value | INR {equity_final:,.2f} |")
    report_rows.append(f"| Cash Balance | INR {state['cash']:,.2f} |")
    report_rows.append(f"| Active Asset Exposure | INR {assets_final:,.2f} |")
    report_rows.append(f"| Total Return Since Start | {((equity_final - START_CAPITAL)/START_CAPITAL * 100):.3f}% |")
    report_rows.append(f"\n## Active Stock Holdings")
    if not state['holdings']:
        report_rows.append("*Portfolio is currently 100% in Cash.*")
    else:
        report_rows.append("| Ticker | Shares | Avg Price | Current Price | Market Value | Allocation |")
        report_rows.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for t, info in state['holdings'].items():
            cp = current_prices.get(t, info['avg_price'])
            mv = info['shares'] * cp
            alloc = (mv / equity_final) * 100
            report_rows.append(f"| {t} | {int(info['shares'])} | INR {info['avg_price']:.2f} | INR {cp:.2f} | INR {mv:.2f} | {alloc:.2f}% |")
            
    with open(REPORT_FILE, 'w') as f:
        f.write("\n".join(report_rows))

    print(f"Daily update done. Current value: INR {equity_final:,.2f}")

if __name__ == '__main__':
    main()
