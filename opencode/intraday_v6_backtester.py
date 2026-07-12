import os
import sys
import numpy as np
import pandas as pd
import yfinance as yf
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

NSE_TICKERS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "KOTAKBANK.NS", "SBIN.NS", "LT.NS", "ITC.NS", "HINDUNILVR.NS",
    "AXISBANK.NS", "BHARTIARTL.NS", "MARUTI.NS", "TATASTEEL.NS", "WIPRO.NS",
    "HCLTECH.NS", "SUNPHARMA.NS", "ASIANPAINT.NS", "TITAN.NS", "ULTRACEMCO.NS",
    "ADANIENT.NS", "BAJFINANCE.NS", "NTPC.NS", "ONGC.NS", "COALINDIA.NS",
    "POWERGRID.NS", "JSWSTEEL.NS", "HEROMOTOCO.NS", "NESTLEIND.NS", "HDFCLIFE.NS",
    "SBILIFE.NS", "GRASIM.NS", "INDUSINDBK.NS", "BAJAJFINSV.NS", "BPCL.NS",
    "CIPLA.NS", "DIVISLAB.NS", "EICHERMOT.NS", "M&M.NS", "APOLLOHOSP.NS"
]

VIX_TICKER = "^INDIAVIX"

def pad_multindex(df):
    cols = []
    for c in df.columns:
        if isinstance(c, tuple):
            cols.append(c[0])
        else:
            cols.append(c)
    df.columns = cols
    return df

class IntradayPairsBacktester:
    def __init__(self, interval="15m", period="60d", initial_capital=100000.0):
        self.interval = interval
        self.period = period
        self.initial_capital = initial_capital
        self.stock_data = {}
        self.vix_data = None

    def download_data(self):
        print(f"Downloading {self.interval} intraday data (period={self.period})...")
        for ticker in NSE_TICKERS:
            df = yf.download(ticker, period=self.period, interval=self.interval, progress=False)
            if df.empty or len(df) < 100:
                print(f"  {ticker}: SKIPPED ({len(df)} rows)")
                continue
            df = pad_multindex(df)
            self.stock_data[ticker] = df
            print(f"  {ticker}: {len(df)} rows")

        vix = yf.download(VIX_TICKER, period="6mo", interval="1d", progress=False)
        if not vix.empty:
            vix = pad_multindex(vix)
            self.vix_data = vix['Close']
            print(f"\nVIX data: {len(vix)} daily rows")

        print(f"\nLoaded {len(self.stock_data)} tickers with intraday data.")

    def find_cointegrated_pairs(self, start_idx, end_idx):
        print(f"\nScanning for cointegrated pairs (rows {start_idx} to {end_idx})...")
        tickers = list(self.stock_data.keys())
        closes = pd.DataFrame({t: self.stock_data[t]['Close'] for t in tickers})
        aligned = closes.iloc[start_idx:end_idx].dropna()
        print(f"Aligned shape: {aligned.shape}")

        if aligned.shape[0] < 100:
            print("Not enough data.")
            return []

        pairs = []
        n = len(tickers)
        for i in range(n):
            for j in range(i + 1, n):
                t1, t2 = tickers[i], tickers[j]
                s1, s2 = aligned[t1], aligned[t2]
                score, pvalue, _ = coint(s1, s2)
                if pvalue < 0.05:
                    X = sm.add_constant(s2)
                    model = sm.OLS(s1, X).fit()
                    beta = model.params.iloc[1]
                    alpha = model.params.iloc[0]
                    spread = s1 - beta * s2 - alpha
                    pairs.append({
                        'pair': (t1, t2),
                        'p_value': pvalue,
                        'beta': beta,
                        'alpha': alpha,
                        'mean_spread': spread.mean(),
                        'std_spread': spread.std()
                    })
        pairs = sorted(pairs, key=lambda x: x['p_value'])
        print(f"Found {len(pairs)} cointegrated pairs.")
        return pairs

    def run_backtest(self, selected_pairs, start_idx, end_idx,
                     z_threshold=1.5, z_exit=0.5, z_stop=5.0,
                     rolling_window=30, max_drawdown_pct=0.20, leverage=6.0):
        closes = pd.DataFrame({t: self.stock_data[t]['Close'] for t in NSE_TICKERS if t in self.stock_data})
        closes = closes.iloc[start_idx:end_idx].dropna()
        dates = closes.index

        capital = self.initial_capital
        peak_equity = capital
        equity_curve = []
        trades = []
        positions = {p['pair']: {'status': 'empty'} for p in selected_pairs}
        pair_alloc = capital / len(selected_pairs)

        print(f"\nBacktesting {len(selected_pairs)} pairs over {len(dates)} bars...")
        print(f"Pair allocation: {pair_alloc:.2f} INR")

        for idx, date in enumerate(dates):
            vix_val = 15.0
            trade_date = date.date() if hasattr(date, 'date') else date
            if self.vix_data is not None:
                vix_vals = self.vix_data[self.vix_data.index.date == trade_date]
                if not vix_vals.empty:
                    vix_val = float(vix_vals.iloc[0])

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

            current_pos_value = 0.0
            unrealized_pnl = 0.0
            open_pos_count = 0

            for p_info in selected_pairs:
                pair = p_info['pair']
                pos = positions[pair]
                t1, t2 = pair
                if t1 not in closes.columns or t2 not in closes.columns:
                    continue
                price_a = closes.loc[date, t1]
                price_b = closes.loc[date, t2]

                if pos['status'] == 'long_spread':
                    current_pos_value += pos['shares_a'] * price_a - pos['shares_b'] * price_b
                    unrealized_pnl += pos['shares_a'] * (price_a - pos['entry_price_a']) + pos['shares_b'] * (pos['entry_price_b'] - price_b)
                    open_pos_count += 1
                elif pos['status'] == 'short_spread':
                    current_pos_value += pos['shares_b'] * price_b - pos['shares_a'] * price_a
                    unrealized_pnl += pos['shares_a'] * (pos['entry_price_a'] - price_a) + pos['shares_b'] * (price_b - pos['entry_price_b'])
                    open_pos_count += 1

            total_equity = capital + current_pos_value

            if open_pos_count > 0 and unrealized_pnl <= -0.05 * total_equity:
                for p_info in selected_pairs:
                    pair = p_info['pair']
                    pos = positions[pair]
                    if pos['status'] != 'empty':
                        t1, t2 = pair
                        pa = closes.loc[date, t1]
                        pb = closes.loc[date, t2]
                        if pos['status'] == 'long_spread':
                            pnl_a = pos['shares_a'] * (pa - pos['entry_price_a'])
                            pnl_b = pos['shares_b'] * (pos['entry_price_b'] - pb)
                            capital += (pos['shares_a'] * pa) - (pos['shares_b'] * pb)
                        else:
                            pnl_a = pos['shares_a'] * (pos['entry_price_a'] - pa)
                            pnl_b = pos['shares_b'] * (pb - pos['entry_price_b'])
                            capital -= (pos['shares_a'] * pa) - (pos['shares_b'] * pb)
                        net_pnl = pnl_a + pnl_b
                        fee = (pos['shares_a'] * pa + pos['shares_b'] * pb) * 0.0005 * 2
                        net_pnl -= fee
                        trades.append({
                            'Pair': f"{t1}/{t2}", 'Type': pos['status'],
                            'Entry_Date': pos['entry_date'], 'Exit_Date': date,
                            'Entry_Val': pos['shares_a'] * pos['entry_price_a'] + pos['shares_b'] * pos['entry_price_b'],
                            'Net_PnL': net_pnl, 'Outcome': 'LOSS' if net_pnl < 0 else 'WIN',
                            'Reason': 'PORTFOLIO_HEAT_STOP'
                        })
                        pos['status'] = 'empty'
                current_pos_value = 0.0
                total_equity = capital
                allow_new_entries = False

            equity_curve.append({'Date': date, 'Equity': total_equity})

            if total_equity > peak_equity:
                peak_equity = total_equity
            drawdown = (peak_equity - total_equity) / peak_equity
            if drawdown >= max_drawdown_pct:
                print(f"!!! Drawdown {drawdown*100:.2f}% hit limit. Liquidating.")
                for p_info in selected_pairs:
                    pos = positions[p_info['pair']]
                    if pos['status'] != 'empty':
                        t1, t2 = p_info['pair']
                        pa = closes.loc[date, t1]
                        pb = closes.loc[date, t2]
                        self._record_exit(trades, pos, pa, pb, date, "RISK_DRAWDOWN_LIQ")
                        pos['status'] = 'empty'
                capital = total_equity
                break

            for p_info in selected_pairs:
                pair = p_info['pair']
                t1, t2 = pair
                pos = positions[pair]
                if t1 not in closes.columns or t2 not in closes.columns:
                    continue

                pair_df = closes[[t1, t2]].iloc[:idx+1].dropna()
                if len(pair_df) < rolling_window + 1:
                    continue
                hist = pair_df.iloc[-rolling_window-1:-1]
                s1h, s2h = hist[t1], hist[t2]

                try:
                    Xh = sm.add_constant(s2h)
                    model = sm.OLS(s1h, Xh).fit()
                    beta = model.params.iloc[1]
                    alpha = model.params.iloc[0]
                except Exception:
                    continue

                spread_hist = s1h - beta * s2h - alpha
                mean_s = spread_hist.mean()
                std_s = spread_hist.std()

                price_a = closes.loc[date, t1]
                price_b = closes.loc[date, t2]
                current_spread = price_a - beta * price_b - alpha
                z = (current_spread - mean_s) / std_s if std_s > 0 else 0.0

                if pos['status'] == 'empty':
                    if allow_new_entries and z >= z_threshold:
                        alloc = (total_equity * current_leverage) / len(selected_pairs)
                        leg = alloc / 2.0
                        sa = int(leg // price_a)
                        sb = int(leg // price_b)
                        if sa > 0 and sb > 0:
                            pos['status'] = 'short_spread'
                            pos['entry_price_a'] = price_a
                            pos['entry_price_b'] = price_b
                            pos['shares_a'] = sa
                            pos['shares_b'] = sb
                            pos['entry_date'] = date
                            capital -= (sb * price_b)
                            capital += (sa * price_a)
                    elif allow_new_entries and z <= -z_threshold:
                        alloc = (total_equity * current_leverage) / len(selected_pairs)
                        leg = alloc / 2.0
                        sa = int(leg // price_a)
                        sb = int(leg // price_b)
                        if sa > 0 and sb > 0:
                            pos['status'] = 'long_spread'
                            pos['entry_price_a'] = price_a
                            pos['entry_price_b'] = price_b
                            pos['shares_a'] = sa
                            pos['shares_b'] = sb
                            pos['entry_date'] = date
                            capital -= (sa * price_a)
                            capital += (sb * price_b)
                else:
                    is_exit = False
                    reason = ""
                    if pos['status'] == 'short_spread' and z <= z_exit:
                        is_exit, reason = True, "MEAN_REVERSION"
                    elif pos['status'] == 'long_spread' and z >= -z_exit:
                        is_exit, reason = True, "MEAN_REVERSION"
                    elif abs(z) >= z_stop:
                        is_exit, reason = True, "DIVERGENCE_STOP"

                    if is_exit:
                        if pos['status'] == 'long_spread':
                            pnl_a = pos['shares_a'] * (price_a - pos['entry_price_a'])
                            pnl_b = pos['shares_b'] * (pos['entry_price_b'] - price_b)
                            capital += (pos['shares_a'] * price_a) - (pos['shares_b'] * price_b)
                        else:
                            pnl_a = pos['shares_a'] * (pos['entry_price_a'] - price_a)
                            pnl_b = pos['shares_b'] * (price_b - pos['entry_price_b'])
                            capital -= (pos['shares_a'] * price_a) - (pos['shares_b'] * price_b)
                        net_pnl = pnl_a + pnl_b
                        fee = (pos['shares_a'] * price_a + pos['shares_b'] * price_b) * 0.0005 * 2
                        net_pnl -= fee
                        trades.append({
                            'Pair': f"{t1}/{t2}", 'Type': pos['status'],
                            'Entry_Date': pos['entry_date'], 'Exit_Date': date,
                            'Entry_Val': pos['shares_a'] * pos['entry_price_a'] + pos['shares_b'] * pos['entry_price_b'],
                            'Net_PnL': net_pnl, 'Outcome': 'PROFIT' if net_pnl > 0 else 'LOSS',
                            'Reason': reason
                        })
                        pos['status'] = 'empty'

        eq_df = pd.DataFrame(equity_curve)
        if not eq_df.empty:
            eq_df.set_index('Date', inplace=True)
        trades_df = pd.DataFrame(trades)
        return eq_df, trades_df

    def _record_exit(self, trades, pos, pa, pb, date, reason):
        if pos['status'] == 'long_spread':
            pnl_a = pos['shares_a'] * (pa - pos['entry_price_a'])
            pnl_b = pos['shares_b'] * (pos['entry_price_b'] - pb)
        else:
            pnl_a = pos['shares_a'] * (pos['entry_price_a'] - pa)
            pnl_b = pos['shares_b'] * (pb - pos['entry_price_b'])
        net_pnl = pnl_a + pnl_b
        trades.append({
            'Pair': 'Liquidated_Pair', 'Type': pos['status'],
            'Entry_Date': pos['entry_date'], 'Exit_Date': date,
            'Entry_Val': pos['shares_a'] * pos['entry_price_a'] + pos['shares_b'] * pos['entry_price_b'],
            'Net_PnL': net_pnl, 'Outcome': 'PROFIT' if net_pnl > 0 else 'LOSS', 'Reason': reason
        })


def calculate_metrics(eq_df, trades_df, initial_capital):
    if eq_df.empty:
        return {}
    final_val = eq_df['Equity'].iloc[-1]
    total_return = (final_val / initial_capital) - 1
    hours = (eq_df.index[-1] - eq_df.index[0]).total_seconds() / 3600
    years = hours / (6.25 * 252)
    cagr = (final_val / initial_capital) ** (1.0 / max(years, 0.001)) - 1 if final_val > 0 else -1

    eq_df['Return'] = eq_df['Equity'].pct_change()
    eq_df['Peak'] = eq_df['Equity'].cummax()
    eq_df['Drawdown'] = (eq_df['Equity'] - eq_df['Peak']) / eq_df['Peak']
    max_dd = eq_df['Drawdown'].min()
    bars_per_day = 26 if len(eq_df) > 100 else 1
    daily_ret = eq_df['Return'] * bars_per_day
    ann_std = daily_ret.std() * np.sqrt(252) if len(daily_ret) > 1 else 0.0
    sharpe = (total_return / ann_std) if ann_std > 0 else 0.0
    downside = daily_ret[daily_ret < 0]
    d_std = downside.std() * np.sqrt(252) if len(downside) > 1 else 0.0
    sortino = (total_return / d_std) if d_std > 0 else 0.0

    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Net_PnL'] > 0]) / len(trades_df)
        total_trades = len(trades_df)
        gp = trades_df[trades_df['Net_PnL'] > 0]['Net_PnL'].sum()
        gl = abs(trades_df[trades_df['Net_PnL'] < 0]['Net_PnL'].sum())
        pf = gp / gl if gl > 0 else (float('inf') if gp > 0 else 1.0)
    else:
        win_rate = total_trades = pf = 0.0

    return {
        'Final_Value': final_val, 'Total_Return': total_return,
        'CAGR': cagr, 'Max_DD': max_dd, 'Sharpe': sharpe,
        'Sortino': sortino, 'Win_Rate': win_rate,
        'Total_Trades': total_trades, 'Profit_Factor': pf
    }
