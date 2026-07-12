import os, argparse, warnings
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

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

TEMPERATURE   = 0.15
MAX_STOCK_CAP = 0.20
BEAR_GUARD    = True

SLOW_WINDOW   = 50
WARMUP_DAYS   = 400
REPORT_DIR    = "compare_strats/reports"
CHART_DIR     = "compare_strats/charts"

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

def heuristic_probabilities(row):
    ret_mean = row['Return_Mean_Slow']
    slope    = row['Slope_Slow']
    adx      = row['ADX_Slow']
    vol      = row['Volatility_Slow']
    s_ret    = 1.0 / (1.0 + np.exp(-500.0 * ret_mean))
    s_slope  = 1.0 / (1.0 + np.exp(-100.0 * slope))
    s_dir    = (s_ret + s_slope) / 2.0
    s_adx    = min(1.0, adx / 50.0)
    s_vol    = max(0.0, 1.0 - vol)
    p_bull   = s_dir * s_adx * s_vol
    p_bear   = (1.0 - s_dir) * s_adx * s_vol
    return p_bull, p_bear

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

def compute_metrics(equity_series, start_capital):
    s         = pd.Series(equity_series)
    total_ret = (s.iloc[-1] - start_capital) / start_capital * 100
    n_years   = len(s) / 252
    cagr      = ((s.iloc[-1] / start_capital) ** (1 / n_years) - 1) * 100
    daily_ret = s.pct_change().dropna()
    sharpe    = (daily_ret.mean() / daily_ret.std() * np.sqrt(252) - 0.05) if daily_ret.std() > 0 else 0
    roll_max  = s.cummax()
    max_dd    = ((s - roll_max) / roll_max).min() * 100
    downside  = daily_ret[daily_ret < 0].std() * np.sqrt(252)
    sortino   = ((daily_ret.mean() * 252 - 0.05) / downside) if downside > 0 else 0
    calmar    = (cagr / 100) / abs(max_dd / 100) if max_dd != 0 else 0
    return {
        "Final Value":  round(s.iloc[-1], 2),
        "Total Return": round(total_ret, 2),
        "CAGR":         round(cagr, 2),
        "Sharpe":       round(sharpe, 3),
        "Sortino":      round(sortino, 3),
        "Calmar":       round(calmar, 3),
        "Max Drawdown": round(max_dd, 2),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-01-07")
    parser.add_argument("--end",   default="2026-07-07")
    args = parser.parse_args()

    trade_start = pd.to_datetime(args.start)
    trade_end   = pd.to_datetime(args.end)
    data_start  = trade_start - pd.Timedelta(days=WARMUP_DAYS)

    os.makedirs(REPORT_DIR, exist_ok=True)
    os.makedirs(CHART_DIR,  exist_ok=True)

    print("=" * 60)
    print("  V4.0 Heuristic Probabilistic — Backtest")
    print(f"  T={TEMPERATURE} | Max cap={int(MAX_STOCK_CAP*100)}% | Bear Guard={'ON' if BEAR_GUARD else 'OFF'}")
    print(f"  Period : {trade_start.date()}  ->  {trade_end.date()}")
    print(f"  Data   : {data_start.date()}  ->  {trade_end.date()}")
    print("=" * 60)

    # 1. Download Nifty
    print("\n[1/5] Downloading Nifty 50 index...")
    dl_end = (trade_end + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    nifty_raw = yf.download(INDEX_TICKER, start=data_start.strftime('%Y-%m-%d'), end=dl_end,
                            auto_adjust=False, progress=False)
    if nifty_raw.empty:
        print("  [ERROR] No Nifty data")
        return
    if isinstance(nifty_raw.columns, pd.MultiIndex):
        nifty_raw.columns = nifty_raw.columns.get_level_values(0)
    nifty_close = nifty_raw['Adj Close'] if 'Adj Close' in nifty_raw.columns else nifty_raw['Close']
    nifty_ema50 = nifty_close.ewm(span=50, adjust=False).mean()
    nifty_bullish = (nifty_close >= nifty_ema50)

    # 2. Download stocks
    print("[2/5] Downloading stocks...")
    all_data = {}
    for t in TICKERS:
        df = yf.download(t, start=data_start.strftime('%Y-%m-%d'), end=dl_end,
                         auto_adjust=False, progress=False)
        if df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = extract_features(df)
        valid = df.dropna(subset=['Return_Mean_Slow', 'Volatility_Slow', 'ADX_Slow', 'Slope_Slow'])
        if len(valid) < 80:
            continue
        all_data[t] = df
    active = list(all_data.keys())
    print(f"      {len(active)} tickers ready.")

    # 3. Simulation
    print(f"\n[3/5] Running simulation...")
    all_dates = sorted(set().union(*[set(df.index) for df in all_data.values()]))
    sim_dates = [d for d in all_dates if trade_start <= pd.Timestamp(d) <= trade_end]
    print(f"      {len(sim_dates)} trading days")

    capital      = START_CAPITAL
    holdings     = {}
    equity_curve = []
    dates_curve  = []
    cash_days    = 0

    for date in sim_dates:
        # MTM
        assets = 0.0
        for t in active:
            if holdings.get(t, 0) > 0 and date in all_data[t].index:
                assets += holdings[t] * all_data[t].loc[date, 'Close']
        equity = capital + assets
        equity_curve.append(equity)
        dates_curve.append(date)

        # Bear guard
        ts_date = pd.Timestamp(date)
        is_bullish = True
        if BEAR_GUARD and ts_date in nifty_bullish.index:
            is_bullish = bool(nifty_bullish.loc[ts_date])

        if not is_bullish:
            cash_days += 1
            for t in list(holdings.keys()):
                if holdings[t] > 0 and date in all_data[t].index:
                    price = all_data[t].loc[date, 'Close']
                    capital += holdings[t] * price * (1 - FEE_RATE)
                    holdings[t] = 0.0
            continue

        # Score with heuristic
        scores = {}
        prices = {}
        for t in active:
            if date not in all_data[t].index:
                continue
            row = all_data[t].loc[date]
            prices[t] = row['Close']
            if pd.isna(row['Return_Mean_Slow']):
                continue
            p_bull, p_bear = heuristic_probabilities(row)
            if p_bull > p_bear and p_bear < 0.35:
                scores[t] = p_bull - p_bear

        # Softmax weights
        target_weights = {}
        if scores:
            target_weights = capped_temperature_softmax(scores, TEMPERATURE, MAX_STOCK_CAP)

        # Rebalance
        target_shares = {
            t: (equity * target_weights.get(t, 0.0)) / prices[t]
            for t in active if t in prices and prices[t] > 0
        }

        for t in active:
            cur = holdings.get(t, 0.0)
            tgt = target_shares.get(t, 0.0)
            if cur > tgt and t in prices:
                capital += (cur - tgt) * prices[t] * (1 - FEE_RATE)
                holdings[t] = tgt

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
                    affordable = capital / (prices[t] * (1 + FEE_RATE))
                    capital   -= affordable * prices[t] * (1 + FEE_RATE)
                    holdings[t] = cur + affordable

    # 4. Metrics & Output
    print(f"\n[4/5] Computing metrics...")
    m = compute_metrics(equity_curve, START_CAPITAL)
    cash_pct = cash_days / len(sim_dates) * 100

    print(f"\n{'='*60}")
    print(f"  V4.0 HEURISTIC RESULTS  |  T={TEMPERATURE}  Cap={int(MAX_STOCK_CAP*100)}%  BearGuard=ON")
    print(f"{'='*60}")
    for k, v in m.items():
        print(f"  {k:<22}: {v}")
    print(f"  {'Days in Cash (Bear)':<22}: {cash_days} ({cash_pct:.1f}%)")
    print(f"{'='*60}")

    # Chart
    dates_plot = pd.to_datetime(dates_curve)
    eq_arr     = np.array(equity_curve)

    fig, ax = plt.subplots(figsize=(14, 5.5))
    ax.plot(dates_plot, eq_arr, color='#e67e22', linewidth=2.2,
            label=f"V4.0 Heuristic (T={TEMPERATURE}, cap={int(MAX_STOCK_CAP*100)}%)")
    ax.axhline(START_CAPITAL, color='#e74c3c', linestyle=':', alpha=0.7)
    ax.fill_between(dates_plot, START_CAPITAL, eq_arr,
                    where=(eq_arr >= START_CAPITAL), alpha=0.08, color='#e67e22')
    ax.fill_between(dates_plot, START_CAPITAL, eq_arr,
                    where=(eq_arr < START_CAPITAL), alpha=0.12, color='#e74c3c')
    ax.set_title(
        f"V4.0 Heuristic — {trade_start.date()} to {trade_end.date()}\n"
        f"CAGR: {m['CAGR']:.2f}%  |  Sharpe: {m['Sharpe']:.3f}  |  "
        f"Max DD: {m['Max Drawdown']:.2f}%",
        fontsize=11, fontweight='bold'
    )
    ax.set_ylabel("Portfolio Value (INR)", fontsize=10)
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"INR {x:,.0f}"))
    ax.legend(fontsize=9)
    plt.tight_layout()
    chart_path = os.path.join(CHART_DIR, "backtest_v4_heuristic_equity.png")
    plt.savefig(chart_path, dpi=150)
    plt.close()
    print(f"      Chart -> {chart_path}")

    # Report
    report_path = os.path.join(REPORT_DIR, "backtest_v4_heuristic_report.md")
    lines = [
        "# Version 4.0 Heuristic Probabilistic - Backtest Report\n",
        f"> **Trading Period**: {trade_start.date()} to {trade_end.date()}  |  **Universe**: {len(active)} stocks",
        f"> **T={TEMPERATURE}** | **Max cap={int(MAX_STOCK_CAP*100)}%/stock** | **Nifty EMA-50 Bear Guard: ON**\n",
        "## Performance Metrics",
        "| Metric | Value |",
        "| :--- | :---: |",
        f"| Final Portfolio Value | **INR {m['Final Value']:,.2f}** |",
        f"| Total Return | **+{m['Total Return']:.2f}%** |",
        f"| CAGR (Annualized) | **{m['CAGR']:.2f}%** |",
        f"| Sharpe Ratio | {m['Sharpe']:.3f} |",
        f"| Sortino Ratio | {m['Sortino']:.3f} |",
        f"| Calmar Ratio | {m['Calmar']:.3f} |",
        f"| Max Drawdown | {m['Max Drawdown']:.2f}% |",
        f"| Days in Cash (Bear Guard) | {cash_days} ({cash_pct:.1f}%) |",
    ]
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"      Report -> {report_path}")
    print("\n[DONE] V4.0 Heuristic backtest complete!")

if __name__ == "__main__":
    main()
