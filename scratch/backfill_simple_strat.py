import os
import sqlite3
import json
import csv
import pandas as pd
import numpy as np
from datetime import datetime

# Configurations
DATA_DIR = "d:\\strats\\data"
STATES_DIR = "d:\\strats\\states"
DB_PATH = os.path.join(DATA_DIR, "trading_journal.db")

BENCHMARK_TICKER = "^NSEI"
START_CAPITAL = 100_000.0
CASH_YIELD_ANNUAL = 0.06
FEE_RATE = 0.001
SLIPPAGE = 0.0035

MIDCAP_TICKERS = [
    "TATAELXSI.NS", "VOLTAS.NS", "BEL.NS", "HAL.NS", "POLYCAB.NS", 
    "KEI.NS", "CHOLAFIN.NS", "SRF.NS", "AUBANK.NS", "MPHASIS.NS", 
    "COFORGE.NS", "PERSISTENT.NS", "DIXON.NS", "RELAXO.NS", "IRCTC.NS", 
    "CONCOR.NS", "BALKRISIND.NS", "TRENT.NS", "KAYNES.NS", "MAZDOCK.NS", 
    "RVNL.NS", "IRFC.NS", "PFC.NS", "RECLTD.NS", "GMRINFRA.NS", 
    "FEDERALBNK.NS", "IDFCFIRSTB.NS", "BATAINDIA.NS", "CUMMINSIND.NS", "ASHOKLEY.NS", 
    "APOLLOTYRE.NS", "LICHSGFIN.NS", "TATAPOWER.NS", "SAIL.NS", "NMDC.NS", 
    "NATIONALUM.NS", "TATACOMM.NS", "MAXHEALTH.NS", "IPCALAB.NS", "SYNGENE.NS",
    "METROPOLIS.NS", "LALPATHLAB.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "DEEPAKNTR.NS",
    "JINDALSTEL.NS", "APARINDS.NS", "SUPREMEIND.NS", "BHARATFORG.NS", "MRF.NS"
]

def get_series(df, col):
    if df is None or df.empty:
        return pd.Series(dtype=float)
    for c in df.columns:
        if isinstance(c, tuple):
            if c[0].lower() == col.lower():
                return df[c].squeeze()
        else:
            if c.lower() == col.lower():
                return df[c].squeeze()
    return pd.Series(dtype=float)

def load_data():
    all_data = {}
    for t in [BENCHMARK_TICKER] + MIDCAP_TICKERS:
        path = os.path.join(DATA_DIR, f"{t}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path, header=[0, 1], index_col=0)
            df.index = pd.to_datetime(df.index)
            all_data[t] = df
    return all_data

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def score_universe(all_data, universe, as_of):
    scores = {}
    lookback_start = as_of - pd.Timedelta(days=365)
    for t in universe:
        if t not in all_data: continue
        close_ser = get_series(all_data[t], 'Close')
        series = close_ser[(close_ser.index >= lookback_start) & (close_ser.index <= as_of)].dropna()
        if len(series) < 100: continue
        
        # Calculate 1-Year Price Return
        ret_1y = (series.iloc[-1] - series.iloc[0]) / series.iloc[0]
        
        # Calculate stock trend relative to its own 50 EMA
        stk_ema50 = series.ewm(span=50, adjust=False).mean()
        trend = (series > stk_ema50).mean()
        
        scores[t] = ret_1y * 0.60 + trend * 0.40
    return scores

def main():
    print("Loading data for simple_strat backfill...")
    all_data = load_data()
    nifty = all_data[BENCHMARK_TICKER]
    nifty_close = get_series(nifty, 'Close')
    nifty_ema50 = ema(nifty_close, 50)

    # Filter dates between July 5, 2026 and today (inclusive)
    backfill_start = pd.Timestamp("2026-07-05")
    backfill_end = nifty_close.index[-1] # Today's last date in CSV
    
    dates = nifty_close[(nifty_close.index >= backfill_start) & (nifty_close.index <= backfill_end)].index
    if len(dates) == 0:
        print("No backfill dates found between 2026-07-05 and now.")
        return

    print(f"Backfilling from {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')} ({len(dates)} days)...")

    # Initial state
    capital = START_CAPITAL
    cash = START_CAPITAL
    holdings = {}
    last_rebal = "2026-07-05"
    
    # Calculate initial momentum rank on 2026-07-05 using preceding data
    initial_scores = score_universe(all_data, MIDCAP_TICKERS, dates[0] - pd.Timedelta(days=1))
    target_portfolio = sorted(initial_scores, key=initial_scores.get, reverse=True)[:5]
    print(f"Initial Target Portfolio (as of July 5): {target_portfolio}")

    trade_records = []
    pnl_records = []

    # Daily simulation loop
    for i, date in enumerate(dates):
        curr_str = date.strftime('%Y-%m-%d')
        nv = nifty_close.loc[date]
        nev = nifty_ema50.loc[date]
        
        # If Nifty close is MultiIndexed, get first element
        if isinstance(nv, pd.Series): nv = nv.iloc[0]
        if isinstance(nev, pd.Series): nev = nev.iloc[0]
        
        bull = nv > nev
        regime = "Bullish" if bull else "Bearish"

        # Calculate portfolio value at the start of the day (before any trades)
        equity = cash
        for t, info in holdings.items():
            if t in all_data:
                close_ser = get_series(all_data[t], 'Close')
                if date in close_ser.index:
                    equity += info['shares'] * float(close_ser.loc[date])
                else:
                    prior = close_ser[close_ser.index < date]
                    equity += info['shares'] * float(prior.iloc[-1])

        # Signal execution check
        target_shares = {}
        if bull:
            # We want to hold target_portfolio (equal weighted)
            w = 0.20
            for t in target_portfolio:
                if t in all_data:
                    close_ser = get_series(all_data[t], 'Close')
                    price = float(close_ser.loc[date]) if date in close_ser.index else float(close_ser[close_ser.index < date].iloc[-1])
                    target_shares[t] = (equity * w * (1.0 - FEE_RATE)) / price
        else:
            # Safe regime is false: hold cash
            pass

        # Execute trades to align holdings to target_shares
        trade_rows = []
        new_holdings = {}
        all_tickers = set(list(holdings.keys()) + list(target_shares.keys()))
        
        for t in all_tickers:
            cur_sh = holdings.get(t, {}).get('shares', 0.0)
            tgt_sh = target_shares.get(t, 0.0)
            close_ser = get_series(all_data[t], 'Close')
            price = float(close_ser.loc[date]) if date in close_ser.index else float(close_ser[close_ser.index < date].iloc[-1])
            diff = tgt_sh - cur_sh

            if abs(diff) < 0.001:
                if cur_sh > 0:
                    new_holdings[t] = {'shares': cur_sh, 'avg_price': holdings[t]['avg_price']}
                continue

            if diff > 0:
                old_avg = holdings.get(t, {}).get('avg_price', price)
                new_avg = (cur_sh*old_avg + diff*price)/(cur_sh+diff) if (cur_sh+diff)>0 else price
                new_holdings[t] = {'shares': tgt_sh, 'avg_price': new_avg}
                cash -= diff * price
                action = 'BUY'
            else:
                if tgt_sh > 0:
                    new_holdings[t] = {'shares': tgt_sh, 'avg_price': holdings[t]['avg_price']}
                cash += abs(diff) * price * (1.0 - FEE_RATE)
                action = 'SELL'

            trade_rows.append({
                'strategy_id': 'simple_strat',
                'date': curr_str,
                'ticker': t,
                'action': action,
                'shares': round(abs(diff), 6),
                'price': round(price, 2),
                'value': round(abs(diff) * price, 2),
                'regime': regime,
                'reason': 'Regime Switch' if not bull else 'Momentum Buy'
            })

        holdings = new_holdings
        
        # Calculate daily ending equity after trades
        ending_equity = cash
        for t, info in holdings.items():
            close_ser = get_series(all_data[t], 'Close')
            price = float(close_ser.loc[date]) if date in close_ser.index else float(close_ser[close_ser.index < date].iloc[-1])
            ending_equity += info['shares'] * price

        trade_records.extend(trade_rows)
        pnl_records.append({
            'strategy_id': 'simple_strat',
            'date': curr_str,
            'portfolio_value': round(ending_equity, 2),
            'cash': round(cash, 2)
        })

    # Clear old records in database for simple_strat to avoid duplicates
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portfolio_states WHERE strategy_id = 'simple_strat'")
    cursor.execute("DELETE FROM trades WHERE strategy_id = 'simple_strat'")
    cursor.execute("DELETE FROM pnl_records WHERE strategy_id = 'simple_strat'")
    conn.commit()

    # Save to SQLite DB
    # 1. State
    state_json = {
        "cash": float(cash),
        "holdings": holdings,
        "start_date": "2026-07-05",
        "start_capital": START_CAPITAL,
        "last_run": dates[-1].strftime('%Y-%m-%d'),
        "last_rebalance_date": last_rebal,
        "target_portfolio": target_portfolio
    }
    
    cursor.execute("""
    INSERT INTO portfolio_states (strategy_id, cash, holdings, start_date, start_capital, last_run)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        'simple_strat',
        float(cash),
        json.dumps(holdings),
        '2026-07-05',
        START_CAPITAL,
        dates[-1].strftime('%Y-%m-%d')
    ))

    # 2. Trades
    for tr in trade_records:
        cursor.execute("""
        INSERT INTO trades (strategy_id, date, ticker, action, shares, price, value, regime, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'simple_strat',
            tr['date'],
            tr['ticker'],
            tr['action'],
            tr['shares'],
            tr['price'],
            tr['value'],
            tr['regime'],
            tr['reason']
        ))

    # 3. PnL
    for pr in pnl_records:
        cursor.execute("""
        INSERT INTO pnl_records (strategy_id, date, portfolio_value, cash)
        VALUES (?, ?, ?, ?)
        """, (
            'simple_strat',
            pr['date'],
            pr['portfolio_value'],
            pr['cash']
        ))

    conn.commit()
    conn.close()

    # Save to JSON state fallback
    state_json_path = os.path.join(STATES_DIR, "portfolio_simple_strat.json")
    os.makedirs(STATES_DIR, exist_ok=True)
    with open(state_json_path, 'w') as f:
        json.dump(state_json, f, indent=2)

    # Save to CSV files
    pnl_csv_path = os.path.join(DATA_DIR, "pnl_simple_strat.csv")
    with open(pnl_csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['date','portfolio_value','cash'])
        w.writeheader()
        for r in pnl_records:
            w.writerow({'date': r['date'], 'portfolio_value': r['portfolio_value'], 'cash': r['cash']})

    trades_csv_path = os.path.join(DATA_DIR, "trades_simple_strat.csv")
    with open(trades_csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['date','ticker','action','shares','price','value','regime','reason'])
        w.writeheader()
        for r in trade_records:
            w.writerow({
                'date': r['date'],
                'ticker': r['ticker'],
                'action': r['action'],
                'shares': r['shares'],
                'price': r['price'],
                'value': r['value'],
                'regime': r['regime'],
                'reason': r['reason']
            })

    print("="*60)
    print("BACKFILL COMPLETED SUCCESSFULLY FOR simple_strat")
    print(f"Final Portfolio Value (as of today): INR {ending_equity:,.2f}")
    print(f"Final Cash: INR {cash:,.2f}")
    print(f"Current Holdings: {holdings}")
    print(f"Written state JSON, CSV logs and SQLite database records.")
    print("="*60)

if __name__ == "__main__":
    main()
