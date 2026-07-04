import os, json, csv, datetime, warnings
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from sklearn.mixture import GaussianMixture
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

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


# Blending parameters
TEMPERATURE           = 0.15
MAX_STOCK_CAP         = 0.20
BEAR_GUARD            = True

# 70% Heuristic (V4) + 30% GMM ML (V3)
MIX_V4                = 0.70
MIX_V3                = 0.30

STATE_FILE  = "states/portfolio_ensemble_70_30.json"
PNL_FILE    = "data/pnl_ensemble_70_30.csv"
LOG_FILE    = "data/trades_ensemble_70_30.csv"
CHART_FILE  = "charts/pnl_ensemble_70_30.png"
REPORT_FILE = "reports/report_ensemble_70_30.md"

# ─────────────────────────────────────────────────────────────────────────────
#  INDICATORS & FEATURE EXTRACTORS
# ─────────────────────────────────────────────────────────────────────────────
def _adx(df, window=50):
    temp = df.copy()
    high = temp['High']
    low = temp['Low']
    close_prev = temp['Close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    high_diff = high - high.shift(1)
    low_diff = low.shift(1) - low
    
    plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
    minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
    
    tr_smooth = tr.ewm(alpha=1/window, adjust=False).mean()
    plus_dm_smooth = pd.Series(plus_dm, index=df.index).ewm(alpha=1/window, adjust=False).mean()
    minus_dm_smooth = pd.Series(minus_dm, index=df.index).ewm(alpha=1/window, adjust=False).mean()
    
    plus_di = 100 * (plus_dm_smooth / tr_smooth)
    minus_di = 100 * (minus_dm_smooth / tr_smooth)
    
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = 100 * np.where(di_sum == 0, 0, di_diff / di_sum)
    return pd.Series(dx, index=df.index).ewm(alpha=1/window, adjust=False).mean()

def _rolling_slope(series, window=50):
    n = window
    x = np.arange(n)
    x_mean = x.mean()
    x_var = ((x - x_mean)**2).sum()
    
    def get_slope(y):
        if len(y) < n or np.any(np.isnan(y)):
            return np.nan
        y_mean = np.mean(y)
        if y_mean == 0:
            return 0.0
        cov = np.sum((x - x_mean) * (y - np.mean(y)))
        raw_slope = cov / x_var
        return raw_slope / y_mean
        
    return series.rolling(window=window).apply(get_slope, raw=True)

# ─────────────────────────────────────────────────────────────────────────────
#  HEURISTIC PROBABILITY MAPPING (V4)
# ─────────────────────────────────────────────────────────────────────────────
def calculate_heuristic_probabilities(row):
    ret_mean = row['Return_Mean_Slow']
    slope = row['Slope_Slow']
    adx = row['ADX_Slow']
    vol = row['Volatility_Slow']
    
    s_ret = 1.0 / (1.0 + np.exp(-500.0 * ret_mean))
    s_slope = 1.0 / (1.0 + np.exp(-100.0 * slope))
    s_direction = (s_ret + s_slope) / 2.0
    s_adx = min(1.0, adx / 50.0)
    s_vol = max(0.0, 1.0 - vol)
    
    p_bull = s_direction * s_adx * s_vol
    p_bear = (1.0 - s_direction) * s_adx * s_vol
    return p_bull, p_bear

# ─────────────────────────────────────────────────────────────────────────────
#  CAPPED SOFTMAX WEIGHTS (Iterative redistribution)
# ─────────────────────────────────────────────────────────────────────────────
def capped_temperature_softmax(scores_dict, T=TEMPERATURE, cap=MAX_STOCK_CAP):
    ticks = list(scores_dict.keys())
    vals  = np.array([scores_dict[t] for t in ticks]) / T
    exp_v = np.exp(vals - np.max(vals))
    w     = exp_v / exp_v.sum()

    for _ in range(20):
        overflow = 0.0
        capped   = np.zeros(len(w), dtype=bool)
        for i in range(len(w)):
            if w[i] > cap:
                overflow  += w[i] - cap
                w[i]       = cap
                capped[i]  = True
        if overflow < 1e-9:
            break
        free = ~capped
        if free.sum() == 0:
            break
        w[free] += overflow / free.sum()

    return {t: w[i] for i, t in enumerate(ticks)}

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
    print(f"  Live Version 5.0 Ensemble 70-30 | {today}")
    print(f"==================================================")

    state = load_state()
    end_dt = datetime.date.today() + datetime.timedelta(days=1)
    start_dt = datetime.date.today() - datetime.timedelta(days=400) # 400 days for stable indicators

    # 1. Check Nifty 50 Index & Macro Switch
    print("Checking Nifty 50 index state...")
    nifty = yf.download(INDEX_TICKER, start=str(start_dt), end=str(end_dt), auto_adjust=False, progress=False)
    if nifty.empty:
        print("  [WARN] Failed to download index data. Defaulting to Bullish regime.")
        is_nifty_bullish = True
    else:
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        nifty['Close'] = nifty['Adj Close']
        nifty['EMA_50'] = nifty['Close'].ewm(span=50, adjust=False).mean()
        
        last_row = nifty.iloc[-1]
        is_nifty_bullish = last_row['Close'] >= last_row['EMA_50']

    print(f"  Nifty 50 Status: {'ABOVE EMA-50' if is_nifty_bullish else 'BELOW EMA-50 (Emergency Exit)'}")

    # 2. Download stock database and extract features
    print("Downloading stock database...")
    stock_dfs = {}
    current_prices = {}
    pooled_data = []
    
    for t in TICKERS:
        df = yf.download(t, start=str(start_dt), end=str(end_dt), auto_adjust=False, progress=False)
        if df.empty or len(df) < 100:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Scale OHLC to use Adj Close
        adj_ratio = df['Adj Close'] / df['Close']
        df['Open'] = df['Open'] * adj_ratio
        df['High'] = df['High'] * adj_ratio
        df['Low'] = df['Low'] * adj_ratio
        df['Close'] = df['Adj Close']
        
        # Calculate features
        df['Log_Return'] = np.log(df['Close'] / df['Close'].shift(1))
        df['Return_Mean_Slow'] = df['Log_Return'].rolling(window=50).mean()
        df['Volatility_Slow'] = df['Log_Return'].rolling(window=50).std() * np.sqrt(252)
        df['ADX_Slow'] = _adx(df, window=50)
        df['Slope_Slow'] = _rolling_slope(df['Close'], window=50)
        
        df_clean = df.dropna()
        if df_clean.empty:
            continue
            
        stock_dfs[t] = df
        current_prices[t] = df['Close'].iloc[-1]
        
        # Collect historical feature vectors for GMM (excluding the last 5 days to avoid target leakage)
        hist_features = df_clean.iloc[:-5][['Return_Mean_Slow', 'Volatility_Slow', 'ADX_Slow', 'Slope_Slow']].values
        pooled_data.append(hist_features)

    # 3. Fit Pooled GMM Model (V3 component)
    if not pooled_data:
        print("  [ERROR] No data available for GMM fitting.")
        return

    all_pooled_features = np.vstack(pooled_data)
    scaler = StandardScaler()
    scaled_pooled = scaler.fit_transform(all_pooled_features)
    
    gmm = GaussianMixture(n_components=3, covariance_type='full', random_state=42)
    gmm.fit(scaled_pooled)
    
    preds = gmm.predict(scaled_pooled)
    component_returns = []
    for c in range(3):
        avg_ret = all_pooled_features[preds == c, 0].mean()
        component_returns.append((c, avg_ret))
    component_returns.sort(key=lambda x: x[1])
    
    bearish_idx = component_returns[0][0]
    bullish_idx = component_returns[2][0]

    # 4. Process Trades
    trade_rows = []
    
    assets_val = sum(info['shares'] * current_prices.get(t, info['avg_price']) for t, info in state['holdings'].items())
    equity = state['cash'] + assets_val
    print(f"  Current cash: INR {state['cash']:,.2f}   Assets: INR {assets_val:,.2f}   Equity: INR {equity:,.2f}")

    # Handle Macro Switch Emergency liquidation
    if BEAR_GUARD and not is_nifty_bullish:
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
        # Calculate individual model weights
        scores_v3 = {}
        scores_v4 = {}
        
        for t, df in stock_dfs.items():
            row = df.iloc[-1]
            
            if pd.isna(row['Return_Mean_Slow']) or pd.isna(row['Volatility_Slow']) or pd.isna(row['ADX_Slow']) or pd.isna(row['Slope_Slow']):
                continue
                
            # A. Model V3 (GMM ML)
            feat_vec = row[['Return_Mean_Slow', 'Volatility_Slow', 'ADX_Slow', 'Slope_Slow']].values.reshape(1, -1)
            scaled_feat = scaler.transform(feat_vec)
            probs = gmm.predict_proba(scaled_feat)[0]
            p_bull_v3 = probs[bullish_idx]
            p_bear_v3 = probs[bearish_idx]
            if p_bull_v3 > p_bear_v3 and p_bear_v3 < 0.35:
                scores_v3[t] = p_bull_v3 - p_bear_v3

            # B. Model V4 (Heuristics)
            p_bull_v4, p_bear_v4 = calculate_heuristic_probabilities(row)
            if p_bull_v4 > p_bear_v4 and p_bear_v4 < 0.35:
                scores_v4[t] = p_bull_v4 - p_bear_v4

        # Convert to individual target weights
        w_v3 = capped_temperature_softmax(scores_v3) if scores_v3 else {}
        w_v4 = capped_temperature_softmax(scores_v4) if scores_v4 else {}

        # Blend weights (70% V4 + 30% V3)
        target_weights = {t: 0.0 for t in TICKERS}
        for t in TICKERS:
            wt_v3 = w_v3.get(t, 0.0)
            wt_v4 = w_v4.get(t, 0.0)
            target_weights[t] = MIX_V4 * wt_v4 + MIX_V3 * wt_v3

        # Execute Rebalance Trades
        target_shares = {
            t: int(equity * target_weights.get(t, 0.0) / current_prices[t])
            for t in TICKERS if t in current_prices and current_prices[t] > 0
        }

        # 1. Sells First
        for t in TICKERS:
            if t in current_prices:
                price = current_prices[t]
                tgt = target_shares.get(t, 0)
                cur = int(state['holdings'].get(t, {}).get('shares', 0))
                
                if tgt < cur:
                    shares_to_sell = cur - tgt
                    val_to_sell = shares_to_sell * price
                    state['cash'] += val_to_sell - calculate_fee(val_to_sell)
                    
                    state['holdings'][t]['shares'] = tgt
                    trade_rows.append({
                        'date': today, 'ticker': t, 'action': 'SELL',
                        'shares': int(shares_to_sell), 'price': round(price, 2),
                        'value': round(val_to_sell, 2), 'reason': f'Ensemble Rebalance to target weight={target_weights.get(t,0.0):.3f}'
                    })
                    print(f"    [SELL] {t} @ INR {price:.2f} (reducing exposure)")
                    if state['holdings'][t]['shares'] <= 0:
                        del state['holdings'][t]

        # 2. Buys Second
        for t in TICKERS:
            if t in current_prices:
                price = current_prices[t]
                tgt = target_shares.get(t, 0)
                cur = int(state['holdings'].get(t, {}).get('shares', 0))
                
                if tgt > cur:
                    shares_to_buy = tgt - cur
                    cost = (shares_to_buy * price) + calculate_fee(shares_to_buy * price)
                    
                    # Check for cash constraints
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
                            'value': round(shares_to_buy * price, 2), 'reason': f'Ensemble Rebalance to target weight={target_weights.get(t,0.0):.3f}'
                        })
                        print(f"    [BUY] {t} @ INR {price:.2f} (acquiring exposure)")

    # 5. Save States & Log PNL
    assets_final = sum(info['shares'] * current_prices.get(t, info['avg_price']) for t, info in state['holdings'].items())
    equity_final = state['cash'] + assets_final
    state['last_run'] = today
    
    save_state(state)
    append_trades(trade_rows)
    append_pnl(today, equity_final, state['cash'])

    # 6. Generate daily chart
    pnl_df = pd.read_csv(PNL_FILE, parse_dates=['date'])
    if len(pnl_df) >= 2:
        fig, ax = plt.subplots(figsize=(13, 4.5))
        dates = pd.to_datetime(pnl_df['date'])
        vals = pnl_df['portfolio_value'].values
        ax.plot(dates, vals, color='#2c3e50', linewidth=2.2, label='V5.0 70-30 Ensemble Portfolio (100k)')
        ax.axhline(START_CAPITAL, color='#e74c3c', linestyle=':', alpha=0.6)
        ax.set_title(f"Version 5.0 Ensemble Live PnL | as of {today}", fontsize=12, fontweight='bold')
        ax.set_ylabel("Portfolio Value (INR)", fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.legend(loc='upper left', fontsize=9)
        plt.tight_layout()
        plt.savefig(CHART_FILE, dpi=150)
        plt.close()

    # 7. Generate detailed markdown report
    days_live = len(pnl_df)
    report_rows = []
    report_rows.append(f"# Live Version 5.0 Ensemble (70-30) Portfolio Report\n")
    report_rows.append(f"> **Date**: {today}  |  **Days Live**: {days_live}  |  **Nifty Index Switch**: {'Risk-On' if (not BEAR_GUARD or is_nifty_bullish) else 'Risk-Off (Cash)'}\n")
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
            
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_rows))

    print(f"Daily update done. Current value: INR {equity_final:,.2f}")

if __name__ == '__main__':
    main()
