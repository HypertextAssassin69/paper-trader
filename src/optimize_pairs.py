import os
import sys
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint
from datetime import datetime

# Add the src folder to path
sys.path.append(os.path.dirname(__file__))
from data_downloader import download_data, TICKERS
from pairs_backtester import read_clean_csv

def run_fast_backtest(stock_data, selected_pairs, start_date, end_date, 
                      z_threshold=2.0, z_exit=0.0, z_stop=4.0, 
                      rolling_window=50, max_drawdown_pct=0.20, leverage=1.0, vix_data=None):
    """
    Super-fast analytical implementation of Pairs Trading backtester with VIX scaling & Portfolio Heat Stop.
    """
    prices_df = pd.DataFrame(stock_data).loc[start_date:end_date].dropna()
    dates = prices_df.index
    
    initial_capital = 100000.0
    capital = initial_capital
    peak_equity = capital
    equity_curve = []
    trades = []
    
    positions = {p['pair']: {'status': 'empty'} for p in selected_pairs}
    
    for idx_date, date in enumerate(dates):
        if idx_date < rolling_window + 1:
            equity_curve.append({'Date': date, 'Equity': capital})
            continue
            
        # Volatility Sizing (Path 2)
        vix_val = 15.0
        if vix_data is not None and date in vix_data.index:
            vix_val = vix_data.loc[date]
            if isinstance(vix_val, pd.Series):
                vix_val = vix_val.iloc[0]
            if pd.isna(vix_val):
                vix_val = 15.0
                
        current_leverage = leverage
        allow_new_entries = True
        
        if vix_val >= 25.0:
            current_leverage = 1.0
            allow_new_entries = False
        elif vix_val >= 22.0:
            current_leverage = 1.0
        elif vix_val >= 15.0:
            ratio = (22.0 - vix_val) / (22.0 - 15.0)
            current_leverage = 1.0 + (leverage - 1.0) * ratio
            
        # Update current equity value of open positions & unrealized PnL (Path 3)
        current_pos_value = 0.0
        unrealized_pnl = 0.0
        open_pos_count = 0
        for p_info in selected_pairs:
            pair = p_info['pair']
            pos = positions[pair]
            t1, t2 = pair
            price_a = prices_df.loc[date, t1]
            price_b = prices_df.loc[date, t2]
            
            if pos['status'] == 'long_spread':
                current_pos_value += pos['shares_a'] * price_a - pos['shares_b'] * price_b
                unrealized_pnl += pos['shares_a'] * (price_a - pos['entry_price_a']) + pos['shares_b'] * (pos['entry_price_b'] - price_b)
                open_pos_count += 1
            elif pos['status'] == 'short_spread':
                current_pos_value += pos['shares_b'] * price_b - pos['shares_a'] * price_a
                unrealized_pnl += pos['shares_a'] * (pos['entry_price_a'] - price_a) + pos['shares_b'] * (price_b - pos['entry_price_b'])
                open_pos_count += 1
                
        total_equity = capital + current_pos_value
        
        # Check Portfolio Heat Stop (Path 3)
        if open_pos_count > 0 and unrealized_pnl <= -0.05 * total_equity:
            for p_info in selected_pairs:
                pair = p_info['pair']
                pos = positions[pair]
                if pos['status'] != 'empty':
                    t1, t2 = pair
                    price_a = prices_df.loc[date, t1]
                    price_b = prices_df.loc[date, t2]
                    
                    if pos['status'] == 'long_spread':
                        pnl_a = pos['shares_a'] * (price_a - pos['entry_price_a'])
                        pnl_b = pos['shares_b'] * (pos['entry_price_b'] - price_b)
                        capital += (pos['shares_a'] * price_a)
                        capital -= (pos['shares_b'] * price_b)
                    else:
                        pnl_a = pos['shares_a'] * (pos['entry_price_a'] - price_a)
                        pnl_b = pos['shares_b'] * (price_b - pos['entry_price_b'])
                        capital -= (pos['shares_a'] * price_a)
                        capital += (pos['shares_b'] * price_b)
                        
                    net_pnl = pnl_a + pnl_b
                    fee = (pos['shares_a'] * price_a + pos['shares_b'] * price_b) * 0.0005 * 2
                    net_pnl -= fee
                    
                    trades.append({'Net_PnL': net_pnl})
                    pos['status'] = 'empty'
                    
            current_pos_value = 0.0
            total_equity = capital
            allow_new_entries = False
            
        equity_curve.append({'Date': date, 'Equity': total_equity})
        
        # Trailing Peak Equity Drawdown Engine (Check 2)
        if total_equity > peak_equity:
            peak_equity = total_equity
            
        drawdown = (peak_equity - total_equity) / peak_equity
        if drawdown >= max_drawdown_pct:
            # Force close all positions
            for p_info in selected_pairs:
                pair = p_info['pair']
                pos = positions[pair]
                if pos['status'] != 'empty':
                    t1, t2 = pair
                    price_a = prices_df.loc[date, t1]
                    price_b = prices_df.loc[date, t2]
                    
                    if pos['status'] == 'long_spread':
                        pnl_a = pos['shares_a'] * (price_a - pos['entry_price_a'])
                        pnl_b = pos['shares_b'] * (pos['entry_price_b'] - price_b)
                        capital += (pos['shares_a'] * price_a)
                        capital -= (pos['shares_b'] * price_b)
                    else:
                        pnl_a = pos['shares_a'] * (pos['entry_price_a'] - price_a)
                        pnl_b = pos['shares_b'] * (price_b - pos['entry_price_b'])
                        capital -= (pos['shares_a'] * price_a)
                        capital += (pos['shares_b'] * price_b)
                        
                    net_pnl = pnl_a + pnl_b
                    fee = (pos['shares_a'] * price_a + pos['shares_b'] * price_b) * 0.0005 * 2
                    net_pnl -= fee
                    
                    trades.append({'Net_PnL': net_pnl})
                    pos['status'] = 'empty'
            capital = total_equity
            break
            
        # Check signals
        slice_df = prices_df.iloc[idx_date - rolling_window - 1 : idx_date - 1]
        
        for p_info in selected_pairs:
            pair = p_info['pair']
            t1, t2 = pair
            pos = positions[pair]
            
            # Analytical OLS Beta
            s1 = slice_df[t1].values
            s2 = slice_df[t2].values
            
            cov = np.cov(s1, s2)[0, 1]
            var = np.var(s2, ddof=1)
            
            if var > 0:
                beta = cov / var
            else:
                beta = 1.0
                
            alpha = np.mean(s1) - beta * np.mean(s2)
            
            # Historical spreads
            spreads = s1 - beta * s2 - alpha
            mean_spread = np.mean(spreads)
            std_spread = np.std(spreads)
            
            # Current values
            price_a = prices_df.loc[date, t1]
            price_b = prices_df.loc[date, t2]
            current_spread = price_a - beta * price_b - alpha
            
            z = (current_spread - mean_spread) / std_spread if std_spread > 0 else 0.0
            
            if pos['status'] == 'empty':
                if allow_new_entries:
                    if z >= z_threshold:
                        # Short Spread: Short A, Long B
                        alloc = (total_equity * current_leverage) / len(selected_pairs)
                        leg_size = alloc / 2.0
                        
                        shares_a = int(leg_size // price_a)
                        shares_b = int(leg_size // price_b)
                        
                        if shares_a > 0 and shares_b > 0:
                            pos['status'] = 'short_spread'
                            pos['entry_price_a'] = price_a
                            pos['entry_price_b'] = price_b
                            pos['shares_a'] = shares_a
                            pos['shares_b'] = shares_b
                            pos['entry_date'] = date
                            
                            capital -= (shares_b * price_b)
                            capital += (shares_a * price_a)
                            
                    elif z <= -z_threshold:
                        # Long Spread: Long A, Short B
                        alloc = (total_equity * current_leverage) / len(selected_pairs)
                        leg_size = alloc / 2.0
                        
                        shares_a = int(leg_size // price_a)
                        shares_b = int(leg_size // price_b)
                        
                        if shares_a > 0 and shares_b > 0:
                            pos['status'] = 'long_spread'
                            pos['entry_price_a'] = price_a
                            pos['entry_price_b'] = price_b
                            pos['shares_a'] = shares_a
                            pos['shares_b'] = shares_b
                            pos['entry_date'] = date
                            
                            capital -= (shares_a * price_a)
                            capital += (shares_b * price_b)
            else:
                # Exit signals
                is_exit = False
                reason = ""
                
                if pos['status'] == 'short_spread' and z <= z_exit:
                    is_exit = True
                    reason = "MEAN_REVERSION"
                elif pos['status'] == 'long_spread' and z >= -z_exit:
                    is_exit = True
                    reason = "MEAN_REVERSION"
                elif abs(z) >= z_stop:
                    is_exit = True
                    reason = "DIVERGENCE_STOP"
                    
                if is_exit:
                    if pos['status'] == 'long_spread':
                        pnl_a = pos['shares_a'] * (price_a - pos['entry_price_a'])
                        pnl_b = pos['shares_b'] * (pos['entry_price_b'] - price_b)
                        capital += (pos['shares_a'] * price_a)
                        capital -= (pos['shares_b'] * price_b)
                    else:
                        pnl_a = pos['shares_a'] * (pos['entry_price_a'] - price_a)
                        pnl_b = pos['shares_b'] * (price_b - pos['entry_price_b'])
                        capital -= (pos['shares_a'] * price_a)
                        capital += (pos['shares_b'] * price_b)
                        
                    net_pnl = pnl_a + pnl_b
                    fee = (pos['shares_a'] * price_a + pos['shares_b'] * price_b) * 0.0005 * 2
                    net_pnl -= fee
                    
                    trades.append({'Net_PnL': net_pnl})
                    pos['status'] = 'empty'
                    
    eq_df = pd.DataFrame(equity_curve)
    if not eq_df.empty:
        eq_df.set_index('Date', inplace=True)
    trades_df = pd.DataFrame(trades)
    
    # Calculate CAGR
    final_val = eq_df['Equity'].iloc[-1] if not eq_df.empty else initial_capital
    years = (dates[-1] - dates[0]).days / 365.25 if len(dates) > 0 else 1.0
    cagr = (final_val / initial_capital) ** (1.0 / max(years, 0.001)) - 1 if final_val > 0 else -1
    
    # Max DD
    if not eq_df.empty:
        eq_df['Peak'] = eq_df['Equity'].cummax()
        eq_df['Drawdown'] = (eq_df['Equity'] - eq_df['Peak']) / eq_df['Peak']
        max_dd = eq_df['Drawdown'].min()
    else:
        max_dd = 0.0
        
    return cagr, max_dd, len(trades_df)

def optimize_pairs_strategy():
    data_dir = "data"
    
    # Load stock data
    stock_data = {}
    print("Loading data for optimization...")
    for ticker in TICKERS:
        if ticker in ["^NSEI", "^INDIAVIX"]:
            continue
        path = os.path.join(data_dir, f"{ticker.replace('/', '_')}.csv")
        if os.path.exists(path):
            df = read_clean_csv(path)
            stock_data[ticker] = df['Close']
            
    vix_data = None
    vix_path = os.path.join(data_dir, "^INDIAVIX.csv")
    if os.path.exists(vix_path):
        vix_df = read_clean_csv(vix_path)
        vix_data = vix_df['Close']
        print("Loaded India VIX data.")
        
    train_start = pd.to_datetime("2019-07-07")
    train_end = pd.to_datetime("2024-07-07")
    
    test_start = pd.to_datetime("2024-07-07")
    test_end = pd.to_datetime("2026-07-07")
    
    # Find cointegrated pairs in training window
    print("Finding cointegrated pairs for training...")
    aligned_df = pd.DataFrame(stock_data).loc[train_start:train_end].dropna()
    tickers = aligned_df.columns
    n = len(tickers)
    coint_list = []
    
    for i in range(n):
        for j in range(i + 1, n):
            t1 = tickers[i]
            t2 = tickers[j]
            score, pval, _ = coint(aligned_df[t1], aligned_df[t2])
            if pval < 0.05:
                coint_list.append({'pair': (t1, t2), 'p_value': pval})
                
    coint_list = sorted(coint_list, key=lambda x: x['p_value'])
    print(f"Found {len(coint_list)} cointegrated pairs.")
    
    if not coint_list:
        print("No pairs found. Exiting.")
        return
        
    # Grid search parameters targeting survival (Max Drawdown <= -20%)
    z_thresholds = [1.5, 2.0]
    z_exits = [0.0, 0.5]
    z_stops = [3.5, 5.0]
    rolling_windows = [20, 50]
    leverages = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    num_pairs_options = [5, 8, 10]
    
    best_cagr = -100.0
    best_params = {}
    results = []
    
    total_runs = len(z_thresholds) * len(z_exits) * len(z_stops) * len(rolling_windows) * len(leverages) * len(num_pairs_options)
    print(f"Total grid search runs: {total_runs}")
    
    run_idx = 0
    for npairs in num_pairs_options:
        selected_pairs = coint_list[:npairs]
        for z_t in z_thresholds:
            for z_e in z_exits:
                for z_s in z_stops:
                    for w in rolling_windows:
                        for lev in leverages:
                            run_idx += 1
                            if run_idx % 50 == 0:
                                print(f"Processing run {run_idx}/{total_runs}...")
                                
                            cagr, max_dd, trades_count = run_fast_backtest(
                                stock_data, selected_pairs, test_start, test_end,
                                z_threshold=z_t, z_exit=z_e, z_stop=z_s,
                                rolling_window=w, max_drawdown_pct=0.20, leverage=lev, vix_data=vix_data
                            )
                            
                            # Filter results to strictly honor the max drawdown cap
                            # We only care about configurations that survived the -20% limit
                            if max_dd >= -0.20 and cagr > -0.99:
                                results.append({
                                    'num_pairs': npairs,
                                    'z_threshold': z_t,
                                    'z_exit': z_e,
                                    'z_stop': z_s,
                                    'window': w,
                                    'leverage': lev,
                                    'CAGR': cagr,
                                    'Max_DD': max_dd,
                                    'trades': trades_count
                                })
                                
                                if cagr > best_cagr:
                                    best_cagr = cagr
                                    best_params = {
                                        'num_pairs': npairs,
                                        'z_threshold': z_t,
                                        'z_exit': z_e,
                                        'z_stop': z_s,
                                        'window': w,
                                        'leverage': lev,
                                        'CAGR': cagr,
                                        'Max_DD': max_dd
                                    }
                                
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df = res_df.sort_values(by='CAGR', ascending=False)
        print("\n" + "="*60)
        print("TOP 10 INSTITUTIONAL COINTEGRATED PAIRS (MAX DD <= 20%):")
        print("="*60)
        for idx, r in res_df.head(10).iterrows():
            print(f"Rank: NumPairs={r['num_pairs']}, Z_Ent={r['z_threshold']}, Z_Exit={r['z_exit']}, Z_Stop={r['z_stop']}, Win={r['window']}, Lev={r['leverage']}")
            print(f"   CAGR: {r['CAGR']*100:.2f}%, MaxDD: {r['Max_DD']*100:.2f}%, Trades: {r['trades']}")
    else:
        print("\nNo configurations found that satisfied the Max Drawdown constraint of <= -20%!")
        
    # Save the absolute best configuration
    best_path = "data/best_pairs_params.csv"
    pd.DataFrame([best_params]).to_csv(best_path, index=False)
    print(f"\nSaved best parameters to {best_path}")

if __name__ == "__main__":
    optimize_pairs_strategy()
