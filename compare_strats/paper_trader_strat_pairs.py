"""
paper_trader_strat_pairs.py  —  Nifty 10-Pair Institutional Statistical Arbitrage (V6 Pairs)
Daily Automated Paper Trader running on GitHub Actions
"""

import os
import json
import csv
import datetime
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
import statsmodels.api as sm
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker

warnings.filterwarnings('ignore')

# Allow date override for backfill runs: DATE_OVERRIDE=2026-07-06
_DATE_OVERRIDE = os.environ.get('DATE_OVERRIDE', '')
def _today():
    if _DATE_OVERRIDE:
        return datetime.date.fromisoformat(_DATE_OVERRIDE)
    return _today()

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
PAIRS = [
    ("ASIANPAINT.NS", "BAJFINANCE.NS"),
    ("ICICIBANK.NS", "SBIN.NS"),
    ("TCS.NS", "APOLLOHOSP.NS"),
    ("NTPC.NS", "COALINDIA.NS"),
    ("TITAN.NS", "SBILIFE.NS"),
    ("RELIANCE.NS", "CIPLA.NS"),
    ("SBIN.NS", "SBILIFE.NS"),
    ("HINDUNILVR.NS", "JSWSTEEL.NS"),
    ("KOTAKBANK.NS", "BAJFINANCE.NS"),
    ("GRASIM.NS", "APOLLOHOSP.NS")
]

# Extract all distinct tickers needed
TICKERS = list(set([t for p in PAIRS for t in p]))
INDEX_TICKER = "^NSEI"
VIX_TICKER = "^INDIAVIX"
START_CAPITAL = 100_000.0

def calculate_fee(trade_value):
    return min(0.0005 * trade_value, 20.0)

STATE_FILE  = "states/portfolio_pairs.json"
PNL_FILE    = "data/pnl_pairs.csv"
LOG_FILE    = "data/trades_pairs.csv"
CHART_FILE  = "charts/pnl_pairs.png"
REPORT_FILE = "reports/report_pairs.md"

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
        "start_date": str(_today()),
        "start_capital": START_CAPITAL,
        "last_run": None,
        "peak_equity": START_CAPITAL,
        "active_trading": True
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
    today = str(_today())
    print(f"\n==================================================")
    print(f"  Live Pairs Trading Institutional Broker | {today}")
    print(f"==================================================")

    state = load_state()
    if not state.get('active_trading', True):
        print("Strategy is HALTED due to historical Drawdown Circuit Breaker.")
        return

    # Check Nifty VIX for regime scaling
    print("Checking India VIX levels...")
    end_dt = _today() + datetime.timedelta(days=1)
    start_dt = _today() - datetime.timedelta(days=15)
    vix = yf.download(VIX_TICKER, start=str(start_dt), end=str(end_dt), auto_adjust=False, progress=False)
    
    vix_val = 15.0
    if not vix.empty:
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        vix_val = vix['Adj Close'].iloc[-1]
        if pd.isna(vix_val):
            vix_val = 15.0
    print(f"  Current India VIX: {vix_val:.2f}")

    # Set leverage scaling parameters
    leverage = 6.0
    current_leverage = leverage
    allow_new_entries = True

    if vix_val >= 25.0:
        current_leverage = 1.0
        allow_new_entries = False
        print("  Regime: CRITICAL VOLATILITY. Entries halted. Leverage 1.0x.")
    elif vix_val >= 22.0:
        current_leverage = 1.0
        print("  Regime: HIGH VOLATILITY. Leverage restricted to 1.0x.")
    elif vix_val >= 15.0:
        ratio = (22.0 - vix_val) / (22.0 - 15.0)
        current_leverage = 1.0 + (leverage - 1.0) * ratio
        print(f"  Regime: MEDIUM VOLATILITY. Leverage scaled to {current_leverage:.2f}x.")
    else:
        print(f"  Regime: LOW VOLATILITY. Leverage at full capacity {current_leverage:.2f}x.")

    # Download tickers history (need last 100 days to compute rolling spreads)
    ticker_start = _today() - datetime.timedelta(days=180)
    print("Downloading constituents price database...")
    ticker_data = {}
    current_prices = {}
    
    for t in TICKERS:
        df = yf.download(t, start=str(ticker_start), end=str(end_dt), auto_adjust=False, progress=False)
        if df.empty or len(df) < 60:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['Close'] = df['Adj Close']
        ticker_data[t] = df
        current_prices[t] = df['Close'].iloc[-1]

    # Calculate active positions market value & unrealized PnL
    current_pos_value = 0.0
    unrealized_pnl = 0.0
    open_pos_count = 0
    trade_rows = []

    for pair_name, pos in list(state['holdings'].items()):
        t1, t2 = pair_name.split('/')
        price_a = current_prices.get(t1)
        price_b = current_prices.get(t2)
        if price_a is None or price_b is None:
            continue
            
        open_pos_count += 1
        if pos['status'] == 'long_spread':
            current_pos_value += pos['shares_a'] * price_a - pos['shares_b'] * price_b
            unrealized_pnl += pos['shares_a'] * (price_a - pos['entry_price_a']) + pos['shares_b'] * (pos['entry_price_b'] - price_b)
        elif pos['status'] == 'short_spread':
            current_pos_value += pos['shares_b'] * price_b - pos['shares_a'] * price_a
            unrealized_pnl += pos['shares_a'] * (pos['entry_price_a'] - price_a) + pos['shares_b'] * (price_b - pos['entry_price_b'])

    total_equity = state['cash'] + current_pos_value
    print(f"  Current Cash: INR {state['cash']:,.2f}   Positions Value: INR {current_pos_value:,.2f}   Equity: INR {total_equity:,.2f}")

    # Check Portfolio Heat Stop (-5.0%)
    if open_pos_count > 0 and unrealized_pnl <= -0.05 * total_equity:
        print(f"  !!! PORTFOLIO HEAT STOP TRIGGERED ({unrealized_pnl / total_equity * 100:.2f}%). Squaring off all positions.")
        for pair_name, pos in list(state['holdings'].items()):
            t1, t2 = pair_name.split('/')
            price_a = current_prices[t1]
            price_b = current_prices[t2]
            
            if pos['status'] == 'long_spread':
                pnl_a = pos['shares_a'] * (price_a - pos['entry_price_a'])
                pnl_b = pos['shares_b'] * (pos['entry_price_b'] - price_b)
                state['cash'] += (pos['shares_a'] * price_a)
                state['cash'] -= (pos['shares_b'] * price_b)
            else:
                pnl_a = pos['shares_a'] * (pos['entry_price_a'] - price_a)
                pnl_b = pos['shares_b'] * (price_b - pos['entry_price_b'])
                state['cash'] -= (pos['shares_a'] * price_a)
                state['cash'] += (pos['shares_b'] * price_b)
                
            net_pnl = pnl_a + pnl_b
            fee = (pos['shares_a'] * price_a + pos['shares_b'] * price_b) * 0.0005 * 2
            state['cash'] -= fee
            
            trade_rows.append({
                'date': today, 'ticker': pair_name, 'action': 'LIQ_HEAT',
                'shares': int(pos['shares_a'] + pos['shares_b']), 'price': round((price_a + price_b)/2, 2),
                'value': round(pos['shares_a']*price_a + pos['shares_b']*price_b, 2), 'reason': 'Global Portfolio Heat Stop'
            })
            del state['holdings'][pair_name]
            
        current_pos_value = 0.0
        total_equity = state['cash']
        allow_new_entries = False

    # Check Trailing Drawdown Cap (-20.0%)
    if total_equity > state['peak_equity']:
        state['peak_equity'] = total_equity
        
    drawdown = (state['peak_equity'] - total_equity) / state['peak_equity']
    if drawdown >= 0.20:
        print(f"  !!! HARD CIRCUIT BREAKER TRIGGERED: Drawdown {drawdown*100:.2f}% hit limit.")
        state['active_trading'] = False
        # Liquidate everything
        for pair_name, pos in list(state['holdings'].items()):
            t1, t2 = pair_name.split('/')
            price_a = current_prices[t1]
            price_b = current_prices[t2]
            
            if pos['status'] == 'long_spread':
                state['cash'] += (pos['shares_a'] * price_a)
                state['cash'] -= (pos['shares_b'] * price_b)
            else:
                state['cash'] -= (pos['shares_a'] * price_a)
                state['cash'] += (pos['shares_b'] * price_b)
                
            fee = (pos['shares_a'] * price_a + pos['shares_b'] * price_b) * 0.0005 * 2
            state['cash'] -= fee
            
            trade_rows.append({
                'date': today, 'ticker': pair_name, 'action': 'LIQ_DRAWDOWN',
                'shares': int(pos['shares_a'] + pos['shares_b']), 'price': round((price_a + price_b)/2, 2),
                'value': round(pos['shares_a']*price_a + pos['shares_b']*price_b, 2), 'reason': 'Trailing Drawdown Breaker'
            })
            del state['holdings'][pair_name]
            
        save_state(state)
        append_trades(trade_rows)
        append_pnl(today, state['cash'], state['cash'])
        return

    # Check Signals on Active Pairs
    for t1, t2 in PAIRS:
        pair_name = f"{t1}/{t2}"
        if t1 not in ticker_data or t2 not in ticker_data:
            continue
            
        df1 = ticker_data[t1]
        df2 = ticker_data[t2]
        
        # Pull OLS preceding 50 days (excluding today for training stats)
        # Verify length
        if len(df1) < 52 or len(df2) < 52:
            continue
            
        s1_hist = df1['Close'].iloc[-51:-1].values
        s2_hist = df2['Close'].iloc[-51:-1].values
        
        cov = np.cov(s1_hist, s2_hist)[0, 1]
        var = np.var(s2_hist, ddof=1)
        beta = cov / var if var > 0 else 1.0
        alpha = np.mean(s1_hist) - beta * np.mean(s2_hist)
        
        spreads = s1_hist - beta * s2_hist - alpha
        mean_spread = np.mean(spreads)
        std_spread = np.std(spreads)
        
        price_a = current_prices[t1]
        price_b = current_prices[t2]
        current_spread = price_a - beta * price_b - alpha
        z = (current_spread - mean_spread) / std_spread if std_spread > 0 else 0.0
        
        pos = state['holdings'].get(pair_name)
        
        if pos is not None:
            # Check exits
            is_exit = False
            exit_reason = ""
            
            if pos['status'] == 'short_spread' and z <= 0.5:
                is_exit = True
                exit_reason = "Mean Reversion Reached"
            elif pos['status'] == 'long_spread' and z >= -0.5:
                is_exit = True
                exit_reason = "Mean Reversion Reached"
            elif abs(z) >= 5.0:
                is_exit = True
                exit_reason = "Divergence Stop-Loss"
                
            if is_exit:
                if pos['status'] == 'long_spread':
                    pnl_a = pos['shares_a'] * (price_a - pos['entry_price_a'])
                    pnl_b = pos['shares_b'] * (pos['entry_price_b'] - price_b)
                    state['cash'] += (pos['shares_a'] * price_a)
                    state['cash'] -= (pos['shares_b'] * price_b)
                else:
                    pnl_a = pos['shares_a'] * (pos['entry_price_a'] - price_a)
                    pnl_b = pos['shares_b'] * (price_b - pos['entry_price_b'])
                    state['cash'] -= (pos['shares_a'] * price_a)
                    state['cash'] += (pos['shares_b'] * price_b)
                    
                net_pnl = pnl_a + pnl_b
                fee = (pos['shares_a'] * price_a + pos['shares_b'] * price_b) * 0.0005 * 2
                state['cash'] -= fee
                
                trade_rows.append({
                    'date': today, 'ticker': pair_name, 'action': 'COVER',
                    'shares': int(pos['shares_a'] + pos['shares_b']), 'price': round((price_a + price_b)/2, 2),
                    'value': round(pos['shares_a']*price_a + pos['shares_b']*price_b, 2), 'reason': exit_reason
                })
                print(f"    [COVER] {pair_name} exit reason: {exit_reason} (Net PnL: INR {net_pnl:.2f})")
                del state['holdings'][pair_name]
                
        else:
            # Check entries
            if allow_new_entries:
                is_entry = False
                side = ""
                
                if z >= 1.5:
                    is_entry = True
                    side = "short_spread"
                elif z <= -1.5:
                    is_entry = True
                    side = "long_spread"
                    
                if is_entry:
                    alloc = (total_equity * current_leverage) / 10.0
                    leg_size = alloc / 2.0
                    
                    shares_a = int(leg_size // price_a)
                    shares_b = int(leg_size // price_b)
                    
                    if shares_a > 0 and shares_b > 0:
                        cost_a = shares_a * price_a
                        cost_b = shares_b * price_b
                        fee = (cost_a + cost_b) * 0.0005 * 2
                        
                        # Check margin safety
                        if side == "long_spread":
                            # Pay A, receive B
                            required_cash = cost_a - cost_b + fee
                        else:
                            # Pay B, receive A
                            required_cash = cost_b - cost_a + fee
                            
                        if state['cash'] >= required_cash:
                            state['cash'] -= required_cash
                            state['holdings'][pair_name] = {
                                "status": side,
                                "shares_a": shares_a,
                                "shares_b": shares_b,
                                "entry_price_a": price_a,
                                "entry_price_b": price_b,
                                "entry_date": today,
                                "beta": beta,
                                "alpha": alpha
                            }
                            
                            trade_rows.append({
                                'date': today, 'ticker': pair_name, 'action': side.upper(),
                                'shares': int(shares_a + shares_b), 'price': round((price_a + price_b)/2, 2),
                                'value': round(cost_a + cost_b, 2), 'reason': f"Entry Spread Z-Score = {z:.2f}"
                            })
                            print(f"    [ENTRY] {side.upper()} on {pair_name} | Z-Score: {z:.2f}")

    # Re-calculate final assets value after trades
    assets_final = 0.0
    for pair_name, pos in state['holdings'].items():
        t1, t2 = pair_name.split('/')
        price_a = current_prices[t1]
        price_b = current_prices[t2]
        if pos['status'] == 'long_spread':
            assets_final += pos['shares_a'] * price_a - pos['shares_b'] * price_b
        elif pos['status'] == 'short_spread':
            assets_final += pos['shares_b'] * price_b - pos['shares_a'] * price_a
            
    equity_final = state['cash'] + assets_final
    state['last_run'] = today

    save_state(state)
    append_trades(trade_rows)
    append_pnl(today, equity_final, state['cash'])

    # 5. Generate daily chart
    try:
        df_pnl = pd.read_csv(PNL_FILE)
        df_pnl['date'] = pd.to_datetime(df_pnl['date'])
        plt.figure(figsize=(10, 5))
        plt.plot(df_pnl['date'], df_pnl['portfolio_value'], label='Institutional Pairs Portfolio', color='#ff3366', linewidth=2)
        plt.title("Institutional Cointegrated Pairs Strategy Equity Curve", fontsize=12, fontweight='bold', pad=15)
        plt.xlabel("Date", fontsize=10)
        plt.ylabel("Portfolio Value (INR)", fontsize=10)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.gcf().autofmt_xdate()
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.legend(loc='upper left')
        plt.tight_layout()
        plt.savefig(CHART_FILE, dpi=300)
        plt.close()
    except Exception as e:
        print(f"  [ERROR] Chart generation failed: {str(e)}")

    # 6. Generate Markdown Report
    try:
        report_content = f"""# Paper Portfolio: Institutional Cointegrated Pairs Strategy (V6 Pairs)

**Last Updated:** `{today}`  
**Current Net Portfolio Equity:** `INR {equity_final:,.2f}`  
**Current Free Cash Balance:** `INR {state['cash']:,.2f}`  
**Trailing Peak Equity:** `INR {state['peak_equity']:,.2f}`  
**Status:** `{"ONLINE" if state['active_trading'] else "HALTED (CIRCUIT_BREAKER_TRIGGERED)"}`

---

## Performance Summary

* **Starting Capital:** `INR {START_CAPITAL:,.2f}`
* **Total Return:** `{(equity_final / START_CAPITAL - 1)*100:.2f}%`
* **Current Volatility Regime (India VIX):** `{vix_val:.2f}` (Current Leverage Multiplier: `{current_leverage:.2f}x`)

---

## Active Positions

| Pair | Direction | Shares Leg A | Shares Leg B | Entry Value | Current Value | Net PnL (INR) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
        if not state['holdings']:
            report_content += "| No active positions | | | | | | |\n"
        else:
            for pair_name, pos in state['holdings'].items():
                t1, t2 = pair_name.split('/')
                price_a = current_prices[t1]
                price_b = current_prices[t2]
                
                entry_val = pos['shares_a'] * pos['entry_price_a'] + pos['shares_b'] * pos['entry_price_b']
                curr_val = pos['shares_a'] * price_a + pos['shares_b'] * price_b
                
                if pos['status'] == 'long_spread':
                    pnl = pos['shares_a'] * (price_a - pos['entry_price_a']) + pos['shares_b'] * (pos['entry_price_b'] - price_b)
                else:
                    pnl = pos['shares_a'] * (pos['entry_price_a'] - price_a) + pos['shares_b'] * (price_b - pos['entry_price_b'])
                    
                report_content += f"| {pair_name} | {pos['status'].upper()} | {pos['shares_a']} | {pos['shares_b']} | INR {entry_val:,.2f} | INR {curr_val:,.2f} | INR {pnl:,.2f} |\n"

        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"Pairs report written to: {REPORT_FILE}")

    except Exception as e:
        print(f"  [ERROR] Report generation failed: {str(e)}")

if __name__ == "__main__":
    main()
