import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

# Add the src folder to path
sys.path.append(os.path.dirname(__file__))

from data_downloader import TICKERS
from backtester import TradingBacktester, calculate_metrics

def run_grid_search():
    print("Initializing backtester for optimization search...")
    bt = TradingBacktester(data_dir="data", initial_capital=100000.0) # Starting capital 1 Lakh (100,000 INR)
    
    # Pre-load data with maximum window size to calculate rolling metrics
    bt.load_data(TICKERS, entry_window=100)
    
    # 7-Year timeline dates for optimization
    start_date = pd.to_datetime("2019-07-07")
    end_date = pd.to_datetime("2026-07-07")
    
    # Parameter grid
    styles = ['swing']  # Focus on swing style since intraday causes heavy fee drag
    entry_windows = [20, 50, 100]
    atr_multipliers = [1.5, 2.5, 3.5, 5.0]
    nifty_regimes = ['EMA_50', 'SMA_200', 'None']
    max_caps = [1.0, 2.0, 3.0, 4.0]  # Portfolio leverage options
    
    results = []
    
    total_runs = len(styles) * len(entry_windows) * len(atr_multipliers) * len(nifty_regimes) * len(max_caps)
    print(f"Starting Grid Search across {total_runs} combinations on the 7-Year timeline (2019-2026)...")
    
    run_idx = 0
    for style in styles:
        for ew in entry_windows:
            for am in atr_multipliers:
                for reg in nifty_regimes:
                    for mc in max_caps:
                        run_idx += 1
                        print(f"Run {run_idx}/{total_runs} | style={style}, window={ew}, atr_mult={am}, regime={reg}, max_cap={mc}...", end="")
                        
                        try:
                            # Run backtest
                            eq_df, trades_df = bt.run_backtest(
                                start_date=start_date,
                                end_date=end_date,
                                style=style,
                                entry_window=ew,
                                atr_mult=am,
                                nifty_regime=reg,
                                max_cap=mc,
                                temp=0.15
                            )
                            
                            # Calculate metrics
                            m = calculate_metrics(eq_df, trades_df, bt.initial_capital)
                            
                            results.append({
                                'style': style,
                                'entry_window': ew,
                                'atr_mult': am,
                                'nifty_regime': reg,
                                'max_cap': mc,
                                'Final_Value': m.get('Final_Value', 0.0),
                                'CAGR': m.get('CAGR', 0.0),
                                'Max_DD': m.get('Max_DD', 0.0),
                                'Sharpe': m.get('Sharpe', 0.0),
                                'Sortino': m.get('Sortino', 0.0),
                                'Win_Rate': m.get('Win_Rate', 0.0),
                                'Total_Trades': m.get('Total_Trades', 0),
                                'Profit_Factor': m.get('Profit_Factor', 0.0)
                            })
                            print(f" Done. CAGR = {m.get('CAGR', 0.0)*100:.1f}%, DD = {m.get('Max_DD', 0.0)*100:.1f}%, PF = {m.get('Profit_Factor', 0.0):.2f}, Trades = {m.get('Total_Trades', 0)}")
                        except Exception as e:
                            print(f" FAILED: {str(e)}")
                            
    # Sort and display top 10 results by CAGR
    res_df = pd.DataFrame(results)
    if res_df.empty:
        print("No successful runs.")
        return
        
    res_df = res_df.sort_values(by='CAGR', ascending=False)
    print("\n" + "="*50)
    print("TOP 10 STRATEGY CONFIGURATIONS BY CAGR (7-Year Timeline):")
    print("="*50)
    for i, row in res_df.head(10).iterrows():
        print(f"Rank {i+1}: Style={row['style']}, Win={row['entry_window']}, ATR={row['atr_mult']}, Regime={row['nifty_regime']}, Cap={row['max_cap']}")
        print(f"   CAGR: {row['CAGR']*100:.2f}%, MaxDD: {row['Max_DD']*100:.2f}%, Sharpe: {row['Sharpe']:.2f}, PF: {row['Profit_Factor']:.2f}, Trades: {row['Total_Trades']}")
        print(f"   Final Portfolio Value: INR {row['Final_Value']:,.2f}\n")
        
    # Save optimized parameters to file so run_backtests.py can read it
    best = res_df.iloc[0]
    best_params_path = "data/best_params.csv"
    res_df.to_csv("data/optimization_results.csv")
    pd.DataFrame([best]).to_csv(best_params_path, index=False)
    print(f"Optimization complete. Saved top configuration to {best_params_path}")

if __name__ == "__main__":
    run_grid_search()
