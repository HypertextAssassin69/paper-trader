import os, warnings, argparse
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from sklearn.mixture import GaussianMixture

warnings.filterwarnings('ignore')

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

INDEX_TICKER  = "^NSEI"
START_CAPITAL = 100_000.0
FEE_RATE      = 0.001
SLOW_WINDOW   = 50
FEATURE_COLS  = ['Return_Mean_Slow', 'Volatility_Slow', 'ADX_Slow', 'Slope_Slow']

def _adx(df, window=50):
    high, low, close = df['High'], df['Low'], df['Close']
    c_prev = close.shift(1)
    tr = pd.concat([high - low, (high - c_prev).abs(), (low - c_prev).abs()], axis=1).max(axis=1)
    h_diff = high - high.shift(1)
    l_diff = low.shift(1) - low
    pdm = np.where((h_diff > l_diff) & (h_diff > 0), h_diff, 0.0)
    mdm = np.where((l_diff > h_diff) & (l_diff > 0), l_diff, 0.0)
    a = 1 / window
    tr_s  = tr.ewm(alpha=a, adjust=False).mean()
    pdm_s = pd.Series(pdm, index=df.index).ewm(alpha=a, adjust=False).mean()
    mdm_s = pd.Series(mdm, index=df.index).ewm(alpha=a, adjust=False).mean()
    pdi   = 100 * pdm_s / tr_s
    mdi   = 100 * mdm_s / tr_s
    di_sum = pdi + mdi
    dx = 100 * np.where(di_sum == 0, 0, (pdi - mdi).abs() / di_sum)
    return pd.Series(dx, index=df.index).ewm(alpha=a, adjust=False).mean()

def _slope(series, window=50):
    n = window
    x = np.arange(n)
    x_mean = x.mean()
    x_var  = ((x - x_mean) ** 2).sum()

    def _get(y):
        if np.any(np.isnan(y)):
            return np.nan
        ym = np.mean(y)
        return 0.0 if ym == 0 else np.sum((x - x_mean) * (y - ym)) / x_var / ym

    return series.rolling(window).apply(_get, raw=True)

def extract_features(df):
    df = df.copy()
    if 'Adj Close' in df.columns:
        ratio = df['Adj Close'] / df['Close']
        for col in ['Open', 'High', 'Low']:
            df[col] = df[col] * ratio
        df['Close'] = df['Adj Close']
    df['Log_Return']       = np.log(df['Close'] / df['Close'].shift(1))
    df['Return_Mean_Slow'] = df['Log_Return'].rolling(SLOW_WINDOW).mean()
    df['Volatility_Slow']  = df['Log_Return'].rolling(SLOW_WINDOW).std() * np.sqrt(252)
    df['ADX_Slow']         = _adx(df, SLOW_WINDOW)
    df['Slope_Slow']       = _slope(df['Close'], SLOW_WINDOW)
    return df

def capped_temperature_softmax(scores_dict, T, cap):
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

def run_simulation(all_data, active, nifty_bullish, sim_dates, gmm, scaler, bullish_idx, bearish_idx, T, cap):
    capital      = START_CAPITAL
    holdings     = {}
    equity_curve = []
    
    for date in sim_dates:
        # Mark-to-market
        assets = 0.0
        for t in active:
            if holdings.get(t, 0) > 0 and date in all_data[t].index:
                assets += holdings[t] * all_data[t].loc[date, 'Close']
        equity = capital + assets
        equity_curve.append(equity)

        # Bear Guard check
        ts_date = pd.Timestamp(date)
        is_bullish_macro = True
        if ts_date in nifty_bullish.index:
            is_bullish_macro = bool(nifty_bullish.loc[ts_date])

        if not is_bullish_macro:
            for t in list(holdings.keys()):
                if holdings[t] > 0 and date in all_data[t].index:
                    price = all_data[t].loc[date, 'Close']
                    capital += holdings[t] * price * (1 - FEE_RATE)
                    holdings[t] = 0.0
            continue

        # Score stocks
        scores = {}
        prices = {}
        for t in active:
            if date not in all_data[t].index:
                continue
            row = all_data[t].loc[date]
            prices[t] = row['Close']
            feat = row[FEATURE_COLS].values
            if np.any(np.isnan(feat)):
                continue
            probs  = gmm.predict_proba(scaler.transform(feat.reshape(1, -1)))[0]
            p_bull = probs[bullish_idx]
            p_bear = probs[bearish_idx]
            if p_bull > p_bear and p_bear < 0.35:
                scores[t] = p_bull - p_bear

        # Capped Softmax
        target_weights = {}
        if scores:
            target_weights = capped_temperature_softmax(scores, T, cap)

        # Target shares
        target_shares = {
            t: (equity * target_weights.get(t, 0.0)) / prices[t]
            for t in active if t in prices and prices[t] > 0
        }

        # Sells first
        for t in active:
            cur = holdings.get(t, 0.0)
            tgt = target_shares.get(t, 0.0)
            if cur > tgt and t in prices:
                capital += (cur - tgt) * prices[t] * (1 - FEE_RATE)
                holdings[t] = tgt

        # Buys second
        for t in active:
            cur = holdings.get(t, 0.0)
            tgt = target_shares.get(t, 0.0)
            if tgt > cur and t in prices:
                buy_sh = tgt - cur
                cost   = buy_sh * prices[t] * (1 + FEE_RATE)
                if cost <= capital:
                    capital -= cost
                    holdings[t] = cur + buy_sh
                elif capital > prices[t] * (1 + FEE_RATE):
                    affordable   = capital / (prices[t] * (1 + FEE_RATE))
                    capital     -= affordable * prices[t] * (1 + FEE_RATE)
                    holdings[t]  = cur + affordable
                    
    # Calculate metrics
    s = pd.Series(equity_curve)
    total_ret = (s.iloc[-1] - START_CAPITAL) / START_CAPITAL * 100
    n_years   = len(s) / 252
    cagr      = ((s.iloc[-1] / START_CAPITAL) ** (1 / n_years) - 1) * 100
    daily_ret = s.pct_change().dropna()
    sharpe    = (daily_ret.mean() / daily_ret.std() * np.sqrt(252) - 0.05) if daily_ret.std() > 0 else 0
    roll_max  = s.cummax()
    max_dd    = ((s - roll_max) / roll_max).min() * 100
    
    return cagr, max_dd, sharpe, s.iloc[-1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="1996-01-01")
    parser.add_argument("--end",   default="2026-07-01")
    args = parser.parse_args()

    print("=" * 70)
    print(f"  30-Year ML Parameter Sweep Optimization (1996 - 2026)")
    print("=" * 70)

    # 1. Download Nifty
    print("Downloading Nifty...")
    nifty_raw = yf.download(INDEX_TICKER, start=args.start, end=args.end, auto_adjust=False, progress=False)
    if isinstance(nifty_raw.columns, pd.MultiIndex):
        nifty_raw.columns = nifty_raw.columns.get_level_values(0)
    nifty_close = nifty_raw['Adj Close'] if 'Adj Close' in nifty_raw.columns else nifty_raw['Close']
    nifty_ema50 = nifty_close.ewm(span=50, adjust=False).mean()
    nifty_bullish = (nifty_close >= nifty_ema50)

    # 2. Download Stocks
    print("Downloading stocks...")
    all_data = {}
    for t in TICKERS:
        df = yf.download(t, start=args.start, end=args.end, auto_adjust=False, progress=False)
        if df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = extract_features(df)
        valid = df.dropna(subset=FEATURE_COLS)
        if len(valid) < 80:
            continue
        all_data[t] = df
    active = list(all_data.keys())
    print(f"  {len(active)} tickers ready.")

    # 3. Fit GMM on 3-year warmup (1996 to 1999)
    print("\nFitting GMM on 3-year warmup (1996-01-01 to 1999-01-01)...")
    cutoff_dt = pd.to_datetime("1999-01-01")
    
    pool_rows = []
    for t in active:
        warmup_df = all_data[t]
        warmup_df = warmup_df[warmup_df.index <= cutoff_dt].dropna(subset=FEATURE_COLS)
        if len(warmup_df) >= 20:
            pool_rows.append(warmup_df[FEATURE_COLS].values)

    all_pool = np.vstack(pool_rows)
    scaler   = StandardScaler()
    scaled   = scaler.fit_transform(all_pool)

    gmm = GaussianMixture(n_components=3, covariance_type='full', random_state=42, max_iter=200)
    gmm.fit(scaled)

    preds = gmm.predict(scaled)
    c_ret = [(c, all_pool[preds == c, 0].mean()) for c in range(3)]
    c_ret.sort(key=lambda x: x[1])
    bearish_idx, bullish_idx = c_ret[0][0], c_ret[2][0]

    all_dates = sorted(set().union(*[set(df.index) for df in all_data.values()]))
    sim_dates = [d for d in all_dates if pd.Timestamp(d) > cutoff_dt]
    print(f"  Trading starts: {cutoff_dt.date()} | Days: {len(sim_dates)}")

    # 4. Sweep Parameters
    sweep_params = [
        # (T, cap)
        (0.30, 0.15),
        (0.20, 0.15),
        (0.20, 0.20),
        (0.15, 0.20),
        (0.15, 0.25),
        (0.10, 0.25)
    ]

    print("\n" + "-"*80)
    print(f"{'Temp (T)':<10} | {'Cap %':<8} | {'CAGR %':<10} | {'Max DD %':<10} | {'Sharpe':<10} | {'Final Value (INR)':<18}")
    print("-"*80)

    results = []
    for T, cap in sweep_params:
        cagr, max_dd, sharpe, final_val = run_simulation(
            all_data, active, nifty_bullish, sim_dates, gmm, scaler, bullish_idx, bearish_idx, T, cap
        )
        print(f"{T:<10.2f} | {int(cap*100):<6}% | {cagr:<8.2f}% | {max_dd:<8.2f}% | {sharpe:<8.3f} | INR {final_val:,.2f}")
        results.append((T, cap, cagr, max_dd, sharpe, final_val))
    print("-"*80)

if __name__ == "__main__":
    main()
