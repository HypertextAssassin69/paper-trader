import os
import json
import csv
import datetime
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
LARGE_BASKET = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "LT.NS", "SBIN.NS", "MARUTI.NS", "BHARTIARTL.NS", "ITC.NS",
    "BAJFINANCE.NS", "SUNPHARMA.NS", "HINDUNILVR.NS", "AXISBANK.NS",
    "M&M.NS", "WIPRO.NS", "TATASTEEL.NS", "HCLTECH.NS", "GRASIM.NS",
    "HINDALCO.NS",
]

COINT_PAIRS = [
    ("ICICIBANK.NS", "SBIN.NS"),
    ("TITAN.NS", "SBILIFE.NS"),
    ("KOTAKBANK.NS", "BAJFINANCE.NS"),
    ("ASIANPAINT.NS", "BAJFINANCE.NS"),
    ("NTPC.NS", "COALINDIA.NS"),
    ("TCS.NS", "APOLLOHOSP.NS"),
    ("WIPRO.NS", "SUNPHARMA.NS"),
    ("JSWSTEEL.NS", "EICHERMOT.NS"),
    ("BHARTIARTL.NS", "JSWSTEEL.NS"),
    ("LT.NS", "AXISBANK.NS")
]

INDEX_TICKER = "^NSEI"
VIX_TICKER = "^INDIAVIX"
START_CAPITAL = 100000.0

STATE_FILE = "states/portfolio_v7_large.json"
PNL_FILE = "data/pnl_v7_large.csv"
LOG_FILE = "data/trades_v7_large.csv"
CHART_FILE = "charts/pnl_v7_large.png"
REPORT_FILE = "reports/report_v7_large.md"
TRANSITION_COST_PCT = 0.0010

def calculate_fee(val):
    return min(0.0005 * val, 20.0)

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
        "holdings": {},  # Stock holdings
        "pairs": {},     # Active pairs L/S positions
        "regime": "SAFE",
        "start_date": str(datetime.date.today()),
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

def _adx(df, window=14):
    high = df['High']
    low = df['Low']
    close_prev = df['Close'].shift(1)
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    tr_smooth = tr.ewm(alpha=1/window, adjust=False).mean()
    high_diff = high - high.shift(1)
    low_diff = low.shift(1) - low
    plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0)
    minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0)
    plus_dm_smooth = pd.Series(plus_dm, index=df.index).ewm(alpha=1/window, adjust=False).mean()
    minus_dm_smooth = pd.Series(minus_dm, index=df.index).ewm(alpha=1/window, adjust=False).mean()
    plus_di = 100 * (plus_dm_smooth / tr_smooth)
    minus_di = 100 * (minus_dm_smooth / tr_smooth)
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = 100 * np.where(di_sum == 0, 0, di_diff / di_sum)
    return pd.Series(dx, index=df.index).ewm(alpha=1/window, adjust=False).mean()

def main():
    state = load_state()
    today = str(datetime.date.today())
    
    if state['last_run'] == today:
        print(f"V7 Large strategy already ran today ({today}). Skipping.")
        return
        
    print(f"Running V7 Large-Cap daily paper trader for {today}...")
    
    # 1. Download Data
    all_tickers = LARGE_BASKET + [INDEX_TICKER, VIX_TICKER]
    for p1, p2 in COINT_PAIRS:
        if p1 not in all_tickers: all_tickers.append(p1)
        if p2 not in all_tickers: all_tickers.append(p2)
        
    data = yf.download(all_tickers, period="60d", group_by="ticker", threads=True, progress=False)
    
    # Clean prices
    current_prices = {}
    for t in all_tickers:
        if t in data.columns.levels[0] if isinstance(data.columns, pd.MultiIndex) else t in data.columns:
            df = data[t].dropna(subset=['Close'])
            if not df.empty:
                current_prices[t] = float(df['Close'].iloc[-1])
                
    nifty_df = data[INDEX_TICKER].dropna(subset=['Close'])
    nifty_close = nifty_df['Close'].iloc[-1]
    nifty_ema = nifty_df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    nifty_adx = _adx(nifty_df, 14).iloc[-1]
    
    vix_df = data[VIX_TICKER].dropna(subset=['Close'])
    vix_val = vix_df['Close'].iloc[-1] if not vix_df.empty else 15.0
    
    is_safe_regime = nifty_close > nifty_ema
    target_regime = "SAFE" if is_safe_regime else "UNSAFE"
    
    trade_rows = []
    
    # Portfolio Valuation before trades
    assets_val = 0.0
    for t, info in state['holdings'].items():
        assets_val += info['shares'] * current_prices.get(t, info['avg_price'])
        
    pairs_val = 0.0
    for name, p_info in state['pairs'].items():
        t1, t2 = name.split('/')
        p_a = current_prices.get(t1)
        p_b = current_prices.get(t2)
        if p_info['type'] == 'long_spread':
            pairs_val += p_info['shares_a'] * p_a - p_info['shares_b'] * p_b
        else:
            pairs_val += p_info['shares_b'] * p_b - p_info['shares_a'] * p_a
            
    portfolio_equity = state['cash'] + assets_val + pairs_val
    print(f"  Pre-Trade Valuation: INR {portfolio_equity:,.2f}")
    
    # 2. Crossover Transition Check
    if target_regime != state['regime']:
        print(f"  !!! REGIME CROSSOVER: Switching from {state['regime']} to {target_regime} !!!")
        
        # Apply 0.1% transition cost
        crossover_fee = portfolio_equity * TRANSITION_COST_PCT
        state['cash'] -= crossover_fee
        portfolio_equity -= crossover_fee
        
        # Liquidate All Stock Holdings (V5)
        for t, info in list(state['holdings'].items()):
            price = current_prices.get(t, info['avg_price'])
            val = info['shares'] * price
            state['cash'] += val - calculate_fee(val)
            trade_rows.append({
                'date': today, 'ticker': t, 'action': 'SELL',
                'shares': info['shares'], 'price': round(price, 2), 'value': round(val, 2),
                'reason': 'Regime Switch Crossover Liquidation'
            })
            del state['holdings'][t]
            
        # Liquidate All Pairs Holdings (V6)
        for name, p_info in list(state['pairs'].items()):
            t1, t2 = name.split('/')
            p_a = current_prices.get(t1)
            p_b = current_prices.get(t2)
            if p_info['type'] == 'long_spread':
                val = p_info['shares_a'] * p_a - p_info['shares_b'] * p_b
            else:
                val = p_info['shares_b'] * p_b - p_info['shares_a'] * p_a
            state['cash'] += val - calculate_fee(abs(val))
            trade_rows.append({
                'date': today, 'ticker': name, 'action': 'LIQUIDATE_PAIR',
                'shares': 0, 'price': 0, 'value': round(val, 2),
                'reason': 'Regime Switch Crossover Pairs Liquidation'
            })
            del state['pairs'][name]
            
        state['regime'] = target_regime

    # 3. Regime Execution
    if state['regime'] == "SAFE":
        # RUN V5 ENSEMBLE SATELLITE (Large-Caps Momentum)
        # Rank by 126-day momentum, buy top 5
        mom_scores = {}
        for t in LARGE_BASKET:
            if t in data.columns.levels[0] if isinstance(data.columns, pd.MultiIndex) else t in data.columns:
                close_series = data[t]['Close'].dropna()
                if len(close_series) >= 50:
                    mom = (close_series.iloc[-1] - close_series.iloc[-50]) / close_series.iloc[-50]
                    mom_scores[t] = mom
                    
        # Sort and select top 5
        top_5 = sorted(mom_scores.keys(), key=lambda x: mom_scores[x], reverse=True)[:5]
        
        # Capital Allocation: 5 slots of 20%
        slot_size = portfolio_equity * 0.20
        target_shares = {}
        for t in top_5:
            price = current_prices.get(t)
            if price and price > 0:
                target_shares[t] = int(slot_size / price)
                
        # Rebalance: Sell non-targets
        for t in list(state['holdings'].keys()):
            if t not in target_shares:
                price = current_prices.get(t)
                val = state['holdings'][t]['shares'] * price
                state['cash'] += val - calculate_fee(val)
                trade_rows.append({
                    'date': today, 'ticker': t, 'action': 'SELL',
                    'shares': state['holdings'][t]['shares'], 'price': round(price, 2), 'value': round(val, 2),
                    'reason': 'V5 Satellite Rebalance: dropped from top momentum'
                })
                del state['holdings'][t]
                
        # Rebalance: Buy targets
        for t, target_qty in target_shares.items():
            current_qty = state['holdings'].get(t, {}).get('shares', 0)
            if target_qty > current_qty:
                qty_to_buy = target_qty - current_qty
                price = current_prices.get(t)
                cost = qty_to_buy * price + calculate_fee(qty_to_buy * price)
                if state['cash'] >= cost:
                    state['cash'] -= cost
                    if t not in state['holdings']:
                        state['holdings'][t] = {'shares': 0, 'avg_price': price, 'entry_date': today}
                    state['holdings'][t]['shares'] += qty_to_buy
                    state['holdings'][t]['avg_price'] = price
                    trade_rows.append({
                        'date': today, 'ticker': t, 'action': 'BUY',
                        'shares': qty_to_buy, 'price': round(price, 2), 'value': round(qty_to_buy * price, 2),
                        'reason': 'V5 Satellite Rebalance: top momentum entry'
                    })
    else:
        # RUN V6 PAIRS (Market-Neutral Cointegrated Pairs)
        # Volatility Sizing (VIX Matrix)
        if vix_val < 15.0:
            leverage = 6.0
        elif vix_val < 22.0:
            leverage = 6.0 - (vix_val - 15.0) * (5.0 / 7.0)
        elif vix_val < 25.0:
            leverage = 1.0
        else:
            leverage = 0.0  # Halt new entries
            
        pair_allocation = portfolio_equity / len(COINT_PAIRS)
        
        for t1, t2 in COINT_PAIRS:
            name = f"{t1}/{t2}"
            if t1 in current_prices and t2 in current_prices:
                p_a = current_prices[t1]
                p_b = current_prices[t2]
                
                # Fetch rolling spread (50-day OLS)
                df1 = data[t1]['Close'].dropna()
                df2 = data[t2]['Close'].dropna()
                
                # Align dates
                common_dates = df1.index.intersection(df2.index)
                y = df1.loc[common_dates].values
                x = df2.loc[common_dates].values
                
                # Simple OLS coefficients estimate
                X = np.vstack([np.ones(len(x)), x]).T
                beta, alpha = np.linalg.lstsq(X, y, rcond=None)[0][1], np.linalg.lstsq(X, y, rcond=None)[0][0]
                
                spreads = y - beta * x - alpha
                mean_s = spreads[-50:].mean()
                std_s = spreads[-50:].std()
                z_score = (spreads[-1] - mean_s) / std_s if std_s > 0 else 0.0
                
                # Check Exits
                is_exiting = False
                if name in state['pairs']:
                    pos_type = state['pairs'][name]['type']
                    if (pos_type == 'short_spread' and z_score <= 0.5) or (pos_type == 'long_spread' and z_score >= -0.5) or abs(z_score) >= 5.0:
                        is_exiting = True
                        
                if is_exiting:
                    p_info = state['pairs'][name]
                    if p_info['type'] == 'long_spread':
                        val = p_info['shares_a'] * p_a - p_info['shares_b'] * p_b
                    else:
                        val = p_info['shares_b'] * p_b - p_info['shares_a'] * p_a
                    state['cash'] += val - calculate_fee(abs(val))
                    trade_rows.append({
                        'date': today, 'ticker': name, 'action': 'CLOSE_PAIR',
                        'shares': 0, 'price': 0, 'value': round(val, 2),
                        'reason': f'V6 Pairs Exit: Z-Score={z_score:.2f}'
                    })
                    del state['pairs'][name]
                    
                # Check Entries
                if name not in state['pairs'] and leverage > 0.0:
                    if z_score >= 1.5:
                        # Short spread: sell A, buy B
                        shares_a = int((pair_allocation * leverage) / p_a)
                        shares_b = int(shares_a * beta)
                        val = shares_b * p_b - shares_a * p_a
                        cost_fee = calculate_fee(shares_a * p_a + shares_b * p_b)
                        
                        state['cash'] += val - cost_fee
                        state['pairs'][name] = {
                            'type': 'short_spread', 'shares_a': shares_a, 'shares_b': shares_b,
                            'entry_price_a': p_a, 'entry_price_b': p_b, 'entry_date': today
                        }
                        trade_rows.append({
                            'date': today, 'ticker': name, 'action': 'OPEN_SHORT_PAIR',
                            'shares': shares_a, 'price': round(z_score, 2), 'value': round(val, 2),
                            'reason': f'V6 Pairs Entry: Z-Score={z_score:.2f}'
                        })
                    elif z_score <= -1.5:
                        # Long spread: buy A, sell B
                        shares_a = int((pair_allocation * leverage) / p_a)
                        shares_b = int(shares_a * beta)
                        val = shares_a * p_a - shares_b * p_b
                        cost_fee = calculate_fee(shares_a * p_a + shares_b * p_b)
                        
                        state['cash'] -= val + cost_fee
                        state['pairs'][name] = {
                            'type': 'long_spread', 'shares_a': shares_a, 'shares_b': shares_b,
                            'entry_price_a': p_a, 'entry_price_b': p_b, 'entry_date': today
                        }
                        trade_rows.append({
                            'date': today, 'ticker': name, 'action': 'OPEN_LONG_PAIR',
                            'shares': shares_a, 'price': round(z_score, 2), 'value': round(val, 2),
                            'reason': f'V6 Pairs Entry: Z-Score={z_score:.2f}'
                        })

    # 4. Final Valuation & Save
    assets_final = sum(info['shares'] * current_prices.get(t, info['avg_price']) for t, info in state['holdings'].items())
    pairs_final = 0.0
    for name, p_info in state['pairs'].items():
        t1, t2 = name.split('/')
        p_a = current_prices.get(t1)
        p_b = current_prices.get(t2)
        if p_info['type'] == 'long_spread':
            pairs_final += p_info['shares_a'] * p_a - p_info['shares_b'] * p_b
        else:
            pairs_final += p_info['shares_b'] * p_b - p_info['shares_a'] * p_a
            
    equity_final = state['cash'] + assets_final + pairs_final
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
        ax.plot(dates, vals, color='#4f46e5', linewidth=2.2, label='V7 Apex Large-Cap Portfolio (100k)')
        ax.axhline(START_CAPITAL, color='#ef4444', linestyle=':', alpha=0.6)
        ax.set_title(f"Version 7.0 Apex Large-Cap Live PnL | as of {today}", fontsize=12, fontweight='bold')
        ax.set_ylabel("Portfolio Value (INR)", fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.legend(loc='upper left', fontsize=9)
        plt.tight_layout()
        plt.savefig(CHART_FILE, dpi=150)
        plt.close()
        
    # 6. Generate detailed report
    days_live = len(pnl_df)
    report_rows = [
        f"# Live Version 7.0 Apex Large-Cap Portfolio Report\n",
        f"> **Date**: {today}  |  **Days Live**: {days_live}  |  **Market Regime**: {state['regime']}\n",
        f"## Summary Stats",
        f"| Metric | Value |",
        f"| :--- | :---: |",
        f"| Starting Capital | INR {START_CAPITAL:,.2f} |",
        f"| Current Portfolio Value | **INR {equity_final:,.2f}** |",
        f"| Cash Balance | INR {state['cash']:,.2f} |",
        f"| Active Stock Asset Exposure | INR {assets_final:,.2f} |",
        f"| Active Pairs Spread Exposure | INR {pairs_final:,.2f} |",
        f"| Total Return Since Start | {((equity_final - START_CAPITAL)/START_CAPITAL * 100):.3f}% |",
        f"\n## Active Holdings"
    ]
    
    if state['regime'] == "SAFE":
        report_rows.append("| Stock Ticker | Shares | Avg Price | Current Price | Market Value | Allocation |")
        report_rows.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for t, info in state['holdings'].items():
            cp = current_prices.get(t, info['avg_price'])
            mv = info['shares'] * cp
            alloc = (mv / equity_final) * 100
            report_rows.append(f"| {t} | {int(info['shares'])} | INR {info['avg_price']:.2f} | INR {cp:.2f} | INR {mv:.2f} | {alloc:.2f}% |")
    else:
        if not state['pairs']:
            report_rows.append("*Pairs trading portfolio is currently flat.*")
        else:
            report_rows.append("| Pair | Type | Shares A | Shares B | Entry Spread | Current Spread | Net Value |")
            report_rows.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
            for name, p_info in state['pairs'].items():
                t1, t2 = name.split('/')
                cp_a = current_prices.get(t1)
                cp_b = current_prices.get(t2)
                cur_v = (p_info['shares_a'] * cp_a - p_info['shares_b'] * cp_b) if p_info['type'] == 'long_spread' else (p_info['shares_b'] * cp_b - p_info['shares_a'] * cp_a)
                report_rows.append(f"| {name} | {p_info['type']} | {p_info['shares_a']} | {p_info['shares_b']} | ₹{(p_info['shares_a']*p_info['entry_price_a'] - p_info['shares_b']*p_info['entry_price_b']):,.2f} | ₹{(p_info['shares_a']*cp_a - p_info['shares_b']*cp_b):,.2f} | INR {cur_v:,.2f} |")
                
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_rows))
        
    print(f"Daily update done. Current value: INR {equity_final:,.2f}")

if __name__ == '__main__':
    main()
