import os
import numpy as np
import pandas as pd
import warnings
from datetime import datetime
from dateutil.relativedelta import relativedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

warnings.filterwarnings('ignore')

# 50 Highly Liquid Indian Midcap Tickers representing the Nifty Midcap/500 space
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

BENCHMARK_TICKER = "^NSEI"
INITIAL_CAPITAL = 100_000.0
DATA_DIR = "d:\\strats\\data"
OUTPUT_DIR = "d:\\strats\\combined_breakout_strategy"
os.makedirs(OUTPUT_DIR, exist_ok=True)

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

def score_combined_universe(closes_df, universe, as_of):
    scores = {}
    lookback_start = as_of - pd.Timedelta(days=365)
    
    for t in universe:
        if t not in closes_df.columns: continue
        series = closes_df[t][closes_df.index <= as_of].dropna()
        if len(series) < 252: continue
        
        # 1-Year price momentum
        series_1y = series[series.index >= lookback_start]
        if len(series_1y) < 100: continue
        ret_1y = (series_1y.iloc[-1] - series_1y.iloc[0]) / series_1y.iloc[0]
        
        # 3-Year rolling high proximity
        rolling_max_3y = series.rolling(min(len(series), 756)).max().iloc[-1]
        curr_price = series.iloc[-1]
        proximity = curr_price / rolling_max_3y
        
        # Proximity threshold: stock must be within 15% of 3-year high
        if proximity >= 0.85:
            scores[t] = ret_1y * 0.50 + proximity * 0.50
            
    return scores

def run_combined_backtest(closes_df, dates, nifty_df, rebal_days=126):
    nifty_close = get_series(nifty_df, 'Close')
    nifty_ema50 = ema(nifty_close, 50)

    capital = INITIAL_CAPITAL
    equity_curve = [(dates[0], capital)]

    universe = MIDCAP_TICKERS
    start_idx = list(closes_df.index).index(dates[0])
    hist_slice = closes_df.iloc[:start_idx]
    scores = score_combined_universe(hist_slice, universe, dates[0])
    active_portfolio = sorted(scores, key=scores.get, reverse=True)[:5]

    rebalance_counter = 0
    SLIPPAGE = 0.0035
    CASH_YIELD_ANNUAL = 0.06

    for i in range(1, len(dates)):
        curr_date = dates[i]
        prev_date = dates[i-1]

        if rebalance_counter >= rebal_days:
            rebalance_counter = 0
            curr_idx = list(closes_df.index).index(prev_date)
            hist_slice = closes_df.iloc[:curr_idx]
            new_scores = score_combined_universe(hist_slice, universe, prev_date)
            new_top_5 = sorted(new_scores, key=new_scores.get, reverse=True)[:5]
            
            if len(new_top_5) < 5:
                fallback_scores = {}
                lookback_start = prev_date - pd.Timedelta(days=365)
                for t in universe:
                    if t in new_top_5: continue
                    if t not in closes_df.columns: continue
                    series = closes_df[t][(closes_df.index >= lookback_start) & (closes_df.index <= prev_date)].dropna()
                    if len(series) < 100: continue
                    fallback_scores[t] = (series.iloc[-1] - series.iloc[0]) / series.iloc[0]
                
                sorted_fallback = sorted(fallback_scores, key=fallback_scores.get, reverse=True)
                for t in sorted_fallback:
                    if len(new_top_5) >= 5: break
                    new_top_5.append(t)
            
            updated = []
            for t in active_portfolio:
                if t in new_top_5:
                    updated.append(t)
            for t in new_top_5:
                if len(updated) >= 5: break
                if t not in updated:
                    updated.append(t)
            
            if set(updated) != set(active_portfolio):
                capital *= (1.0 - SLIPPAGE)
                active_portfolio = updated

        rebalance_counter += 1

        nv = nifty_close.loc[prev_date]
        nev = nifty_ema50.loc[prev_date]
        if isinstance(nv, pd.Series): nv = nv.iloc[0]
        if isinstance(nev, pd.Series): nev = nev.iloc[0]
        
        bull = nv > nev

        if bull:
            w = 0.20
            daily_ret = 0.0
            for t in active_portfolio:
                p_curr = closes_df.loc[curr_date, t]
                p_prev = closes_df.loc[prev_date, t]
                if np.isnan(p_curr) or np.isnan(p_prev) or p_prev <= 0:
                    daily_ret += w * (CASH_YIELD_ANNUAL / 252)
                else:
                    daily_ret += w * (p_curr - p_prev) / p_prev
        else:
            daily_ret = CASH_YIELD_ANNUAL / 252

        capital *= (1.0 + daily_ret)
        equity_curve.append((curr_date, capital))

    eq = pd.DataFrame(equity_curve, columns=['Date','Value']).set_index('Date')
    return eq

def main():
    print("Loading data for Combined Breakout-Momentum strategy...")
    all_data = load_data()
    nifty = all_data[BENCHMARK_TICKER]

    today = datetime.today()
    start_ts = pd.Timestamp((today - relativedelta(years=10)).date())
    end_ts = pd.Timestamp(today.date())
    dates = nifty[(nifty.index >= start_ts) & (nifty.index <= end_ts)].index

    closes_df = pd.DataFrame()
    for t in MIDCAP_TICKERS:
        if t in all_data:
            closes_df[t] = get_series(all_data[t], 'Close')
    closes_df = closes_df.ffill().bfill()

    print("Running Combined Breakout-Momentum Strategy...")
    eq = run_combined_backtest(closes_df, dates, nifty, rebal_days=126)
    
    # Plotting
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(eq.index, eq['Value'].values, color='#00d09c', lw=2)
    ax.set_title("Combined Multi-Year Breakout + Momentum (10-Year)", fontsize=12, fontweight='bold')
    ax.set_ylabel("Capital (INR)")
    ax.set_yscale('log')
    ax.grid(True, which="both", alpha=0.3)
    
    plt.tight_layout()
    chart_out = os.path.join(OUTPUT_DIR, "pnl_chart.png")
    plt.savefig(chart_out, dpi=150)
    plt.close()
    print(f"Backtest curve saved to: {chart_out}")

if __name__ == "__main__":
    main()
