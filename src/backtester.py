import os
import numpy as np
import pandas as pd

def softmax(x, temp=0.15):
    e_x = np.exp((x - np.max(x)) / temp)
    return e_x / e_x.sum()

def cap_weights(weights, max_cap=0.20):
    n = len(weights)
    if n == 0:
        return weights
    w = np.array(weights, dtype=float)
    if n * max_cap < 1.0:
        return np.minimum(w, max_cap)
    for _ in range(100):
        over_indices = w > max_cap
        if not np.any(over_indices):
            break
        excess = np.sum(w[over_indices] - max_cap)
        w[over_indices] = max_cap
        under_indices = w < max_cap
        if not np.any(under_indices):
            break
        under_sum = np.sum(w[under_indices])
        if under_sum > 0:
            w[under_indices] += excess * (w[under_indices] / under_sum)
        else:
            w[under_indices] += excess / np.sum(under_indices)
    return w

def read_clean_csv(file_path):
    df = pd.read_csv(file_path, index_col=0)
    df = df.drop('Ticker', errors='ignore')
    df = df.drop('Date', errors='ignore')
    df = df[df.index.notna()]
    df.index = pd.to_datetime(df.index, errors='coerce')
    df = df[df.index.notna()]
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df.sort_index(inplace=True)
    df = df.dropna(subset=['Close', 'High', 'Low', 'Open'])
    return df

class TradingBacktester:
    def __init__(self, data_dir="data", initial_capital=100000.0, fee_pct=0.0005, fee_cap=20.0):
        self.data_dir = data_dir
        self.initial_capital = initial_capital
        self.fee_pct = fee_pct
        self.fee_cap = fee_cap
        self.stock_data = {}
        self.nifty_data = None
        
    def load_data(self, tickers, entry_window=20):
        # Load Nifty 50
        nifty_path = os.path.join(self.data_dir, "^NSEI.csv")
        if not os.path.exists(nifty_path):
            raise FileNotFoundError(f"Nifty 50 data not found at {nifty_path}")
            
        nifty_df = read_clean_csv(nifty_path)
        nifty_df['EMA_50'] = nifty_df['Close'].ewm(span=50, adjust=False).mean()
        nifty_df['SMA_200'] = nifty_df['Close'].rolling(window=200).mean()
        self.nifty_data = nifty_df
        
        # Load stocks
        self.stock_data = {}
        for ticker in tickers:
            if ticker == "^NSEI":
                continue
            path = os.path.join(self.data_dir, f"{ticker}.csv")
            if not os.path.exists(path):
                continue
                
            df = read_clean_csv(path)
            
            # Recalculate indicators based on search parameters
            df['High_Window'] = df['High'].shift(1).rolling(window=entry_window).max()
            df['ROC_20'] = df['Close'].pct_change(periods=20).shift(1)
            
            # 10-day ATR (shift 1 so we have it ready at Open)
            high = df['High']
            low = df['Low']
            prev_close = df['Close'].shift(1)
            tr1 = high - low
            tr2 = (high - prev_close).abs()
            tr3 = (low - prev_close).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['ATR_10'] = tr.rolling(window=10).mean().shift(1)
            
            self.stock_data[ticker] = df

    def run_backtest(self, start_date, end_date, style='swing', entry_window=20, atr_mult=2.5, nifty_regime='EMA_50', max_cap=0.20, temp=0.15):
        # Reload data with current entry_window
        self.load_data(list(self.stock_data.keys()) + ["^NSEI"], entry_window=entry_window)
        
        # Filter Nifty for timeline
        nifty_sub = self.nifty_data.loc[start_date:end_date]
        dates = nifty_sub.index
        
        capital = self.initial_capital
        equity_curve = []
        trades = []
        
        # Positions tracking: ticker -> {shares, entry_price, entry_date, highest_close, stop_price}
        open_positions = {}
        
        for date in dates:
            # 1. Update Nifty regime (from t-1 to prevent lookahead)
            if date not in self.nifty_data.index:
                equity_curve.append((date, capital + self._get_positions_value(open_positions, date)))
                continue
                
            idx = self.nifty_data.index.get_loc(date)
            if idx == 0:
                equity_curve.append((date, capital))
                continue
                
            prev_nifty_date = self.nifty_data.index[idx - 1]
            nifty_row = self.nifty_data.loc[prev_nifty_date]
            
            # Check regime
            if nifty_regime == 'EMA_50':
                is_bullish_regime = nifty_row['Close'] > nifty_row['EMA_50']
            elif nifty_regime == 'SMA_200':
                is_bullish_regime = nifty_row['Close'] > nifty_row['SMA_200']
            else:
                is_bullish_regime = True
                
            # 2. Check exits for open swing positions
            stopped_tickers = []
            if style == 'swing':
                for ticker, pos in list(open_positions.items()):
                    df = self.stock_data[ticker]
                    if date not in df.index:
                        continue
                    current_row = df.loc[date]
                    
                    # Stop out check
                    if current_row['Low'] <= pos['stop_price']:
                        # Exit order filled at stop price (or Open if it gapped below stop)
                        exit_price = min(pos['stop_price'], current_row['Open'])
                        exit_value = pos['shares'] * exit_price
                        exit_fee = min(exit_value * self.fee_pct, self.fee_cap)
                        
                        gross_pnl = exit_value - (pos['shares'] * pos['entry_price'])
                        net_pnl = gross_pnl - pos['entry_fee'] - exit_fee
                        
                        capital += (exit_value - exit_fee)
                        stopped_tickers.append(ticker)
                        
                        trades.append({
                            'Date': date.strftime('%Y-%m-%d'),
                            'Ticker': ticker,
                            'Entry_Date': pos['entry_date'].strftime('%Y-%m-%d'),
                            'Shares': pos['shares'],
                            'Entry': pos['entry_price'],
                            'Exit': exit_price,
                            'Gross_PnL': gross_pnl,
                            'Fees': pos['entry_fee'] + exit_fee,
                            'Net_PnL': net_pnl,
                            'Outcome': 'STOP'
                        })
                    else:
                        # Update trailing stop based on new highest close
                        pos['highest_close'] = max(pos['highest_close'], current_row['Close'])
                        # Recalculate trailing stop
                        new_stop = pos['highest_close'] - atr_mult * current_row['ATR_10']
                        pos['stop_price'] = max(pos['stop_price'], new_stop)
                        
                # Remove stopped positions
                for t in stopped_tickers:
                    del open_positions[t]
                    
            # 3. Identify new buy signals
            active_signals = []
            # Max positions we can hold
            max_positions = max(1, int(1.0 / max_cap))
            free_slots = max_positions - len(open_positions)
            
            if is_bullish_regime and free_slots > 0:
                for ticker, df in self.stock_data.items():
                    if ticker in open_positions:
                        continue
                    if date not in df.index:
                        continue
                    
                    s_idx = df.index.get_loc(date)
                    if s_idx == 0:
                        continue
                        
                    prev_row = df.iloc[s_idx - 1]
                    current_row = df.iloc[s_idx]
                    
                    if pd.isna(prev_row['High_Window']) or pd.isna(prev_row['ATR_10']) or pd.isna(prev_row['ROC_20']):
                        continue
                        
                    # Breakout condition
                    is_breakout = prev_row['Close'] > prev_row['High_Window']
                    
                    if is_breakout:
                        active_signals.append({
                            'ticker': ticker,
                            'open': float(current_row['Open']),
                            'high': float(current_row['High']),
                            'low': float(current_row['Low']),
                            'close': float(current_row['Close']),
                            'atr': float(prev_row['ATR_10']),
                            'roc': float(prev_row['ROC_20'])
                        })
            
            # 4. Handle Entries
            if len(active_signals) > 0 and free_slots > 0:
                # Rank signals by 20-day ROC using softmax
                rocs = np.array([s['roc'] for s in active_signals])
                raw_weights = softmax(rocs, temp=temp)
                # Keep top signals to fill slots
                ranked_indices = np.argsort(raw_weights)[::-1]
                
                # We can enter at most free_slots positions
                slots_to_fill = min(free_slots, len(active_signals))
                
                # Calculate capital available per new trade
                total_equity = capital + self._get_positions_value(open_positions, date)
                trade_size = total_equity * max_cap
                
                for idx_rank in range(slots_to_fill):
                    sig = active_signals[ranked_indices[idx_rank]]
                    ticker = sig['ticker']
                    open_price = sig['open']
                    
                    if open_price <= 0 or total_equity <= 0:
                        continue
                        
                    shares = int(trade_size // open_price)
                    if shares <= 0:
                        continue
                        
                    entry_value = shares * open_price
                    entry_fee = min(entry_value * self.fee_pct, self.fee_cap)
                    
                    capital -= (entry_value + entry_fee)
                    
                    if style == 'swing':
                        # Initial stop price
                        stop_price = open_price - atr_mult * sig['atr']
                        open_positions[ticker] = {
                            'shares': shares,
                            'entry_price': open_price,
                            'entry_date': date,
                            'entry_fee': entry_fee,
                            'highest_close': sig['close'],
                            'stop_price': stop_price
                        }
                    else:
                        # Intraday holding style (close on same day)
                        stop_price = open_price - 1.5 * sig['atr']
                        target_price = open_price + 3.0 * sig['atr']
                        
                        exit_price = sig['close']
                        outcome = "CLOSE"
                        
                        if sig['low'] <= stop_price and sig['high'] >= target_price:
                            exit_price = stop_price
                            outcome = "WHIPSAW_STOP"
                        elif sig['low'] <= stop_price:
                            exit_price = stop_price
                            outcome = "STOP"
                        elif sig['high'] >= target_price:
                            exit_price = target_price
                            outcome = "TARGET"
                            
                        exit_value = shares * exit_price
                        exit_fee = min(exit_value * self.fee_pct, self.fee_cap)
                        
                        gross_pnl = exit_value - entry_value
                        total_fees = entry_fee + exit_fee
                        net_pnl = gross_pnl - total_fees
                        
                        capital += (exit_value - exit_fee)
                        
                        trades.append({
                            'Date': date.strftime('%Y-%m-%d'),
                            'Ticker': ticker,
                            'Entry_Date': date.strftime('%Y-%m-%d'),
                            'Shares': shares,
                            'Entry': open_price,
                            'Exit': exit_price,
                            'Gross_PnL': gross_pnl,
                            'Fees': total_fees,
                            'Net_PnL': net_pnl,
                            'Outcome': outcome
                        })
            
            # Calculate total daily equity
            pos_val = self._get_positions_value(open_positions, date)
            equity_curve.append((date, capital + pos_val))
            
        # End of backtest: Force close all open positions
        if style == 'swing' and len(open_positions) > 0:
            final_date = dates[-1]
            for ticker, pos in list(open_positions.items()):
                df = self.stock_data[ticker]
                current_row = df.loc[final_date]
                exit_price = current_row['Close']
                exit_value = pos['shares'] * exit_price
                exit_fee = min(exit_value * self.fee_pct, self.fee_cap)
                
                gross_pnl = exit_value - (pos['shares'] * pos['entry_price'])
                net_pnl = gross_pnl - pos['entry_fee'] - exit_fee
                
                capital += (exit_value - exit_fee)
                trades.append({
                    'Date': final_date.strftime('%Y-%m-%d'),
                    'Ticker': ticker,
                    'Entry_Date': pos['entry_date'].strftime('%Y-%m-%d'),
                    'Shares': pos['shares'],
                    'Entry': pos['entry_price'],
                    'Exit': exit_price,
                    'Gross_PnL': gross_pnl,
                    'Fees': pos['entry_fee'] + exit_fee,
                    'Net_PnL': net_pnl,
                    'Outcome': 'CLOSE_EOF'
                })
            open_positions.clear()
            
        # Update last equity curve point
        if len(dates) > 0:
            equity_curve[-1] = (dates[-1], capital)
        
        eq_df = pd.DataFrame(equity_curve, columns=['Date', 'Equity']).set_index('Date')
        trades_df = pd.DataFrame(trades)
        return eq_df, trades_df
        
    def _get_positions_value(self, open_positions, date):
        val = 0.0
        for ticker, pos in open_positions.items():
            df = self.stock_data[ticker]
            if date in df.index:
                val += pos['shares'] * df.loc[date, 'Close']
            else:
                val += pos['shares'] * pos['entry_price']
        return val

def calculate_metrics(eq_df, trades_df, initial_capital):
    if eq_df.empty:
        return {}
        
    final_val = eq_df['Equity'].iloc[-1]
    total_return = (final_val / initial_capital) - 1
    
    # CAGR
    years = (eq_df.index[-1] - eq_df.index[0]).days / 365.25
    cagr = (final_val / initial_capital) ** (1.0 / max(years, 0.001)) - 1 if final_val > 0 else -1
    
    # Daily Returns
    eq_df['Daily_Return'] = eq_df['Equity'].pct_change()
    
    # Max Drawdown
    eq_df['Peak'] = eq_df['Equity'].cummax()
    eq_df['Drawdown'] = (eq_df['Equity'] - eq_df['Peak']) / eq_df['Peak']
    max_dd = eq_df['Drawdown'].min()
    
    # Volatility & Sharpe/Sortino
    daily_std = eq_df['Daily_Return'].std()
    ann_std = daily_std * np.sqrt(252) if not pd.isna(daily_std) else 0.0
    sharpe = (cagr / ann_std) if ann_std > 0 else 0.0
    
    downside_returns = eq_df['Daily_Return'][eq_df['Daily_Return'] < 0]
    downside_std = downside_returns.std()
    ann_downside_std = downside_std * np.sqrt(252) if not pd.isna(downside_std) else 0.0
    sortino = (cagr / ann_downside_std) if ann_downside_std > 0 else 0.0
    
    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Net_PnL'] > 0]) / len(trades_df)
        total_trades = len(trades_df)
        
        # Calculate Profit Factor (Gross Profits / Gross Losses)
        gross_profits = trades_df[trades_df['Net_PnL'] > 0]['Net_PnL'].sum()
        gross_losses = abs(trades_df[trades_df['Net_PnL'] < 0]['Net_PnL'].sum())
        profit_factor = gross_profits / gross_losses if gross_losses > 0 else (float('inf') if gross_profits > 0 else 1.0)
    else:
        win_rate = 0.0
        total_trades = 0
        profit_factor = 0.0
        
    return {
        'Final_Value': final_val,
        'Total_Return': total_return,
        'CAGR': cagr,
        'Max_DD': max_dd,
        'Sharpe': sharpe,
        'Sortino': sortino,
        'Win_Rate': win_rate,
        'Total_Trades': total_trades,
        'Profit_Factor': profit_factor
    }
