"""
paper_trader_strat_v7_cheap_20k.py
==================================
Automated daily execution script for "Cheap V7" (v7_cheap_20k) strategy.
Capital: ₹20,000.
Regime:
- SAFE: Curated Cheap Basket Momentum (6 slots, ~₹3,333 per slot).
- UNSAFE: Curated Cheap Pairs (3 pairs, 100% deployment, ~₹6,666 per pair slot).
"""

import os
import json
import csv
import datetime
import numpy as np
import pandas as pd
import yfinance as yf
import sqlite3

# Curated Cheap Momentum Basket (prices under ~₹600)
CHEAP_BASKET = [
    "TATASTEEL.NS", "BEL.NS", "NTPC.NS", "COALINDIA.NS", "TATAPOWER.NS",
    "ITC.NS", "GAIL.NS", "ONGC.NS", "WIPRO.NS", "IOC.NS",
    "NATIONALUM.NS", "HINDALCO.NS", "PNB.NS", "NHPC.NS", "SAIL.NS"
]

# Cointegrated Cheap Pairs (prices under ~₹500)
CHEAP_PAIRS = [
    ("NTPC.NS", "COALINDIA.NS"),
    ("IOC.NS", "ONGC.NS"),
    ("TATASTEEL.NS", "HINDALCO.NS")
]

INDEX_TICKER = "^NSEI"
START_CAPITAL = 20000.0
STRATEGY_ID = "v7_cheap_20k"

STATE_FILE = "states/portfolio_v7_cheap_20k.json"
PNL_FILE = "data/pnl_v7_cheap_20k.csv"
LOG_FILE = "data/trades_v7_cheap_20k.csv"
DB_PATH = "../data/trading_journal.db"
FEE_RATE = 0.0008
TRANSITION_COST_PCT = 0.0015
SLOTS = 6
PAIRS_ALLOCATION = 1.0

def calculate_fee(val):
    return min(0.0005 * val, 20.0)

def main():
    print(f"Running daily execution for Strategy: {STRATEGY_ID}...")
    
    # Load state
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    else:
        state = {
            "cash": START_CAPITAL,
            "holdings": {},
            "pairs": {},
            "regime": "SAFE",
            "start_date": "2026-07-05",
            "last_run": None,
            "start_capital": START_CAPITAL
        }
        
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    
    # Download data
    all_tickers = list(set(CHEAP_BASKET + [INDEX_TICKER]))
    for p1, p2 in CHEAP_PAIRS:
        if p1 not in all_tickers: all_tickers.append(p1)
        if p2 not in all_tickers: all_tickers.append(p2)
        
    data = yf.download(all_tickers, period="90d", group_by="ticker", progress=False)
    
    nifty_close = data[INDEX_TICKER]['Close'].dropna()
    nifty_ema = nifty_close.ewm(span=50, adjust=False).mean()
    
    n_c = float(nifty_close.iloc[-1])
    n_e = float(nifty_ema.iloc[-1])
    
    target_regime = "SAFE" if n_c > n_e else "UNSAFE"
    
    # Current prices lookup
    current_prices = {}
    for t in all_tickers:
        closes = data[t]['Close'].dropna()
        if not closes.empty:
            current_prices[t] = float(closes.iloc[-1])
            
    # Portfolio valuation pre-trades
    assets_val = sum(h_info['shares'] * current_prices.get(t, h_info['avg_price']) for t, h_info in state['holdings'].items())
    pairs_val = 0.0
    for name, p_info in state['pairs'].items():
        t1, t2 = name.split('/')
        p_a = current_prices.get(t1)
        p_b = current_prices.get(t2)
        if p_a and p_b:
            if p_info['type'] == 'long':
                pairs_val += p_info['shares_a'] * p_a - p_info['shares_b'] * p_b
            else:
                pairs_val += p_info['shares_b'] * p_b - p_info['shares_a'] * p_a
                
    portfolio_equity = state['cash'] + assets_val + pairs_val
    trade_rows = []
    
    # Regime transition liquidation
    if target_regime != state['regime']:
        crossover_fee = portfolio_equity * TRANSITION_COST_PCT
        state['cash'] -= crossover_fee
        portfolio_equity -= crossover_fee
        
        # Liquidate stocks
        for t, h_info in list(state['holdings'].items()):
            p = current_prices.get(t)
            val = h_info['shares'] * p
            state['cash'] += val - calculate_fee(val)
            trade_rows.append({
                'date': today_str, 'ticker': t, 'action': 'SELL',
                'shares': h_info['shares'], 'price': round(p, 2), 'value': round(val, 2),
                'reason': 'Regime Switch Crossover Liquidation'
            })
            del state['holdings'][t]
            
        # Liquidate pairs
        for name, p_info in list(state['pairs'].items()):
            t1, t2 = name.split('/')
            p_a = current_prices.get(t1)
            p_b = current_prices.get(t2)
            if p_a and p_b:
                val = (p_info['shares_a'] * p_a - p_info['shares_b'] * p_b) if p_info['type'] == 'long' else (p_info['shares_b'] * p_b - p_info['shares_a'] * p_a)
                state['cash'] += val - calculate_fee(abs(val))
                trade_rows.append({
                    'date': today_str, 'ticker': name, 'action': 'LIQUIDATE_PAIR',
                    'shares': 0, 'price': 0, 'value': round(val, 2),
                    'reason': 'Regime Switch Crossover Pairs Liquidation'
                })
            del state['pairs'][name]
            
        state['regime'] = target_regime
        
    # Execute regime logic
    if state['regime'] == "SAFE":
        closes_df = pd.DataFrame({t: data[t]['Close'] for t in CHEAP_BASKET if t in data.columns.levels[0]}).ffill()
        momentum_ratios = (closes_df - closes_df.shift(50)) / closes_df.shift(50)
        
        cheap_pool = [t for t in CHEAP_BASKET if t in current_prices]
        target_basket = sorted(cheap_pool, key=lambda x: momentum_ratios[x].iloc[-1], reverse=True)[:6]
        
        slot_size = portfolio_equity / SLOTS
        target_shares = {}
        for t in target_basket:
            p = current_prices.get(t)
            if p and not pd.isna(p) and p > 0:
                target_shares[t] = int(slot_size / p)
                
        # Sell
        for t in list(state['holdings'].keys()):
            if t not in target_shares:
                p = current_prices.get(t)
                val = state['holdings'][t]['shares'] * p
                state['cash'] += val - calculate_fee(val)
                trade_rows.append({
                    'date': today_str, 'ticker': t, 'action': 'SELL',
                    'shares': state['holdings'][t]['shares'], 'price': round(p, 2), 'value': round(val, 2),
                    'reason': 'Satellite Rebalance: momentum drop'
                })
                del state['holdings'][t]
                
        # Buy
        for t, target_qty in target_shares.items():
            current_qty = state['holdings'].get(t, {}).get('shares', 0)
            if target_qty > current_qty:
                qty = target_qty - current_qty
                p = current_prices.get(t)
                cost = qty * p + calculate_fee(qty * p)
                if state['cash'] >= cost:
                    state['cash'] -= cost
                    if t not in state['holdings']:
                        state['holdings'][t] = {'shares': 0, 'avg_price': p, 'entry_date': today_str}
                    state['holdings'][t]['shares'] += qty
                    state['holdings'][t]['avg_price'] = p
                    trade_rows.append({
                        'date': today_str, 'ticker': t, 'action': 'BUY',
                        'shares': qty, 'price': round(p, 2), 'value': round(qty * p, 2),
                        'reason': 'Satellite Rebalance: momentum entry'
                    })
    else:
        # UNSAFE regime: Cointegrated Pairs (100% deployment)
        pairs_cap = portfolio_equity * PAIRS_ALLOCATION
        pair_slot = pairs_cap / len(CHEAP_PAIRS)
        
        # Calculate daily z-scores
        closes_df = pd.DataFrame()
        for p1, p2 in CHEAP_PAIRS:
            closes_df[p1] = data[p1]['Close']
            closes_df[p2] = data[p2]['Close']
        closes_df = closes_df.ffill()
        
        for p_idx, (p1, p2) in enumerate(CHEAP_PAIRS):
            name = f"{p1}/{p2}"
            ratio_series = closes_df[p1] / closes_df[p2]
            sma = ratio_series.rolling(20).mean()
            std = ratio_series.rolling(20).std()
            z_series = (ratio_series - sma) / std
            
            z = z_series.iloc[-1]
            ratio = ratio_series.iloc[-1]
            p_a = current_prices.get(p1)
            p_b = current_prices.get(p2)
            
            if pd.isna(z) or not p_a or not p_b: continue
            
            if name not in state['pairs']:
                # Enter Position
                if z > 2.0:
                    shares_b = int(pair_slot / p_b)
                    shares_a = int((shares_b * p_b) / p_a)
                    cost = calculate_fee(shares_b * p_b) + calculate_fee(shares_a * p_a)
                    if state['cash'] >= cost:
                        state['cash'] -= cost
                        state['pairs'][name] = {
                            'type': 'short', 'entry_ratio': ratio,
                            'shares_a': shares_a, 'shares_b': shares_b
                        }
                        trade_rows.append({
                            'date': today_str, 'ticker': name, 'action': 'SHORT_PAIR',
                            'shares': shares_a, 'price': round(ratio, 4), 'value': round(pair_slot, 2),
                            'reason': f'Pairs Entry: Z={z:.2f}'
                        })
                elif z < -2.0:
                    shares_a = int(pair_slot / p_a)
                    shares_b = int((shares_a * p_a) / p_b)
                    cost = calculate_fee(shares_a * p_a) + calculate_fee(shares_b * p_b)
                    if state['cash'] >= cost:
                        state['cash'] -= cost
                        state['pairs'][name] = {
                            'type': 'long', 'entry_ratio': ratio,
                            'shares_a': shares_a, 'shares_b': shares_b
                        }
                        trade_rows.append({
                            'date': today_str, 'ticker': name, 'action': 'LONG_PAIR',
                            'shares': shares_a, 'price': round(ratio, 4), 'value': round(pair_slot, 2),
                            'reason': f'Pairs Entry: Z={z:.2f}'
                        })
            else:
                # Exit Position
                p_state = state['pairs'][name]
                is_exit = False
                if p_state['type'] == 'short' and z <= 0.0:
                    is_exit = True
                elif p_state['type'] == 'long' and z >= 0.0:
                    is_exit = True
                    
                if is_exit:
                    val = (p_state['shares_a'] * p_a - p_state['shares_b'] * p_b) if p_state['type'] == 'long' else (p_state['shares_b'] * p_b - p_state['shares_a'] * p_a)
                    state['cash'] += val - calculate_fee(abs(val))
                    trade_rows.append({
                        'date': today_str, 'ticker': name, 'action': 'EXIT_PAIR',
                        'shares': 0, 'price': round(ratio, 4), 'value': round(val, 2),
                        'reason': f'Pairs Exit: Z={z:.2f}'
                    })
                    del state['pairs'][name]
                    
    # Post-trade valuation
    assets_final = sum(h_info['shares'] * current_prices.get(t, h_info['avg_price']) for t, h_info in state['holdings'].items())
    pairs_final = 0.0
    for name, p_info in state['pairs'].items():
        t1, t2 = name.split('/')
        p_a = current_prices.get(t1)
        p_b = current_prices.get(t2)
        if p_a and p_b:
            if p_info['type'] == 'long':
                pairs_final += p_info['shares_a'] * p_a - p_info['shares_b'] * p_b
            else:
                pairs_final += p_info['shares_b'] * p_b - p_info['shares_a'] * p_a
                
    portfolio_equity = state['cash'] + assets_final + pairs_final
    state['last_run'] = today_str
    
    # Save State
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
        
    # Append to daily PnL log
    with open(PNL_FILE, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['date', 'portfolio_value', 'cash'])
        w.writerow({'date': today_str, 'portfolio_value': round(portfolio_equity, 2), 'cash': round(state['cash'], 2)})
        
    # Append to trade log
    if trade_rows:
        exists_log = os.path.exists(LOG_FILE)
        with open(LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['date', 'ticker', 'action', 'shares', 'price', 'value', 'reason'])
            if not exists_log: w.writeheader()
            w.writerows(trade_rows)
            
    # Write to transactional SQLite database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR REPLACE INTO portfolio_states (strategy_id, cash, holdings, start_date, start_capital, last_run)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (STRATEGY_ID, float(state['cash']), json.dumps(state['holdings']), state['start_date'], state['start_capital'], state['last_run']))
    
    cursor.execute("""
    INSERT OR REPLACE INTO pnl_records (strategy_id, date, portfolio_value, cash)
    VALUES (?, ?, ?, ?)
    """, (STRATEGY_ID, today_str, float(portfolio_equity), float(state['cash'])))
    
    for row in trade_rows:
        cursor.execute("""
        INSERT INTO trades (strategy_id, date, ticker, action, shares, price, value, regime, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (STRATEGY_ID, today_str, row['ticker'], row['action'], float(row['shares']), float(row['price']), float(row['value']), target_regime, row['reason']))
        
    conn.commit()
    conn.close()
    print(f"Daily execution complete for {STRATEGY_ID}. Portfolio Value: {portfolio_equity:.2f}")

if __name__ == '__main__':
    main()
