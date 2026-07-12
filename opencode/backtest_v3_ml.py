"""
Version 3.0 Backtester — ML GMM Probabilistic Softmax Allocator (Fix B)
========================================================================
Fixes applied vs raw V3.0:
  1. Temperature raised from 0.05 -> 0.30 (moderate concentration, 3-5 leaders)
  2. Max single-stock cap: 15% of total equity
  3. Nifty 50 EMA-50 Circuit Breaker: goes 100% Cash when Nifty < EMA-50

Usage:
    python backtest_v3_ml.py --start 2018-01-01 --end 2026-07-01

Outputs -> compare_strats/reports/backtest_v3_ml_report.md
           compare_strats/charts/backtest_v3_ml_equity.png
"""

import argparse, os, warnings
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from sklearn.mixture import GaussianMixture
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────────────────
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

# ── OPTIMIZED V3.0 PARAMETERS ───────────────────────────────────────────────
TEMPERATURE   = 0.15      # Concentrates weights in top 1-3 confident stocks
MAX_STOCK_CAP = 0.20      # Hard ceiling of 20% per stock
BEAR_GUARD    = True      # Nifty EMA-50 circuit breaker enabled
# ─────────────────────────────────────────────────────────────────────────────

SLOW_WINDOW   = 50
WARMUP_YEARS  = 1.5
REPORT_DIR    = "compare_strats/reports"
CHART_DIR     = "compare_strats/charts"
FEATURE_COLS  = ['Return_Mean_Slow', 'Volatility_Slow', 'ADX_Slow', 'Slope_Slow']

# ─────────────────────────────────────────────────────────────────────────────
#  INDICATORS
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
#  CAPPED TEMPERATURE SOFTMAX
# ─────────────────────────────────────────────────────────────────────────────
def capped_temperature_softmax(scores_dict, T=TEMPERATURE, cap=MAX_STOCK_CAP):
    """Softmax with temperature, then iteratively redistribute weight > cap."""
    ticks = list(scores_dict.keys())
    vals  = np.array([scores_dict[t] for t in ticks]) / T
    exp_v = np.exp(vals - np.max(vals))
    w     = exp_v / exp_v.sum()

    # Iterative cap: redistribute overflow weight to uncapped stocks
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


# ─────────────────────────────────────────────────────────────────────────────
#  METRICS
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end",   default="2026-07-01")
    args = parser.parse_args()

    os.makedirs(REPORT_DIR, exist_ok=True)
    os.makedirs(CHART_DIR,  exist_ok=True)

    print("=" * 60)
    print("  V3.0 ML Probabilistic Softmax — Fix B")
    print(f"  T={TEMPERATURE} | Max cap={int(MAX_STOCK_CAP*100)}% | Bear Guard={'ON' if BEAR_GUARD else 'OFF'}")
    print(f"  Period : {args.start}  ->  {args.end}")
    print("=" * 60)

    # ── 1. DOWNLOAD NIFTY (for circuit breaker) ───────────────────────────────
    print("\n[1/5] Downloading Nifty 50 index...")
    nifty_raw = yf.download(INDEX_TICKER, start=args.start, end=args.end,
                            auto_adjust=False, progress=False)
    if isinstance(nifty_raw.columns, pd.MultiIndex):
        nifty_raw.columns = nifty_raw.columns.get_level_values(0)
    nifty_close = nifty_raw['Adj Close'] if 'Adj Close' in nifty_raw.columns else nifty_raw['Close']
    nifty_ema50 = nifty_close.ewm(span=50, adjust=False).mean()
    nifty_bullish = (nifty_close >= nifty_ema50)  # True = above EMA50 = Risk-On

    # ── 2. DOWNLOAD STOCKS ────────────────────────────────────────────────────
    print("[2/5] Downloading stocks and extracting features...")
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
    print(f"      {len(active)} tickers ready.")

    # ── 3. FIT GMM ON WARMUP (once, no lookahead) ─────────────────────────────
    print(f"\n[3/5] Fitting GMM on first {WARMUP_YEARS}-year warmup...")
    start_dt  = pd.to_datetime(args.start)
    cutoff_dt = start_dt + pd.DateOffset(months=int(WARMUP_YEARS * 12))

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
    print(f"      Pooled {len(all_pool):,} rows | Bearish={bearish_idx}, Bullish={bullish_idx}")
    print(f"      Trading period: {cutoff_dt.date()} -> {args.end}")

    # ── 4. SIMULATION ─────────────────────────────────────────────────────────
    print(f"\n[4/5] Running simulation...")
    all_dates = sorted(set().union(*[set(df.index) for df in all_data.values()]))
    sim_dates = [d for d in all_dates if pd.Timestamp(d) > cutoff_dt]
    print(f"      {len(sim_dates)} trading days")

    capital      = START_CAPITAL
    holdings     = {}
    equity_curve = []
    dates_curve  = []
    cash_days    = 0   # days spent in cash due to bear guard
    max_alloc_log = []

    for date in sim_dates:
        # Mark-to-market
        assets = 0.0
        for t in active:
            if holdings.get(t, 0) > 0 and date in all_data[t].index:
                assets += holdings[t] * all_data[t].loc[date, 'Close']
        equity = capital + assets
        equity_curve.append(equity)
        dates_curve.append(date)

        # ── BEAR GUARD: Nifty EMA-50 circuit breaker ──────────────────────────
        ts_date = pd.Timestamp(date)
        is_bullish_macro = True
        if BEAR_GUARD and ts_date in nifty_bullish.index:
            is_bullish_macro = bool(nifty_bullish.loc[ts_date])

        if not is_bullish_macro:
            cash_days += 1
            # Emergency liquidate all holdings
            for t in list(holdings.keys()):
                if holdings[t] > 0 and date in all_data[t].index:
                    price = all_data[t].loc[date, 'Close']
                    capital += holdings[t] * price * (1 - FEE_RATE)
                    holdings[t] = 0.0
            continue  # skip rebalancing, sit in cash

        # ── SCORE STOCKS via GMM ───────────────────────────────────────────────
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

        # ── CAPPED SOFTMAX WEIGHTS ─────────────────────────────────────────────
        target_weights = {}
        if scores:
            target_weights = capped_temperature_softmax(scores)
            max_alloc_log.append(max(target_weights.values()) * 100)

        # ── REBALANCE: Sells then Buys ─────────────────────────────────────────
        target_shares = {
            t: (equity * target_weights.get(t, 0.0)) / prices[t]
            for t in active if t in prices and prices[t] > 0
        }

        for t in active:  # sells first
            cur = holdings.get(t, 0.0)
            tgt = target_shares.get(t, 0.0)
            if cur > tgt and t in prices:
                capital += (cur - tgt) * prices[t] * (1 - FEE_RATE)
                holdings[t] = tgt

        for t in active:  # buys second
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

    # ── 5. METRICS, CHART, REPORT ─────────────────────────────────────────────
    print(f"\n[5/5] Computing metrics and generating outputs...")
    m = compute_metrics(equity_curve, START_CAPITAL)
    avg_max_alloc = np.mean(max_alloc_log) if max_alloc_log else 0
    cash_pct = cash_days / len(sim_dates) * 100

    print(f"\n{'='*60}")
    print(f"  V3.0 ML Fix-B RESULTS  |  T={TEMPERATURE}  Cap={int(MAX_STOCK_CAP*100)}%  BearGuard=ON")
    print(f"{'='*60}")
    for k, v in m.items():
        print(f"  {k:<22}: {v}")
    print(f"  {'Avg Top-Stock Alloc':<22}: {avg_max_alloc:.1f}%")
    print(f"  {'Days in Cash (Bear)':<22}: {cash_days} ({cash_pct:.1f}%)")
    print(f"{'='*60}")

    # Chart
    dates_plot = pd.to_datetime(dates_curve)
    eq_arr     = np.array(equity_curve)

    fig, ax = plt.subplots(figsize=(14, 5.5))
    ax.plot(dates_plot, eq_arr, color='#9b59b6', linewidth=2.2,
            label=f"V3.0 ML (T={TEMPERATURE}, cap={int(MAX_STOCK_CAP*100)}%, Bear Guard)")
    ax.axhline(START_CAPITAL, color='#e74c3c', linestyle=':', alpha=0.7, label='Starting Capital')
    ax.fill_between(dates_plot, START_CAPITAL, eq_arr,
                    where=(eq_arr >= START_CAPITAL), alpha=0.08, color='#9b59b6')
    ax.fill_between(dates_plot, START_CAPITAL, eq_arr,
                    where=(eq_arr < START_CAPITAL), alpha=0.12, color='#e74c3c')
    ax.set_title(
        f"V3.0 ML Fix-B — {cutoff_dt.date()} → {args.end}\n"
        f"CAGR: {m['CAGR']:.2f}%  |  Sharpe: {m['Sharpe']:.3f}  |  "
        f"Max DD: {m['Max Drawdown']:.2f}%  |  Avg Top Alloc: {avg_max_alloc:.1f}%",
        fontsize=11, fontweight='bold'
    )
    ax.set_ylabel("Portfolio Value (INR)", fontsize=10)
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"INR {x:,.0f}"))
    ax.legend(fontsize=9)
    plt.tight_layout()
    chart_path = os.path.join(CHART_DIR, "backtest_v3_ml_equity.png")
    plt.savefig(chart_path, dpi=150)
    plt.close()
    print(f"      Chart -> {chart_path}")

    # Report
    eff_start   = str(cutoff_dt.date())
    report_path = os.path.join(REPORT_DIR, "backtest_v3_ml_report.md")
    lines = [
        "# Version 3.0 ML Probabilistic Softmax (Fix B) - Backtest Report\n",
        f"> **GMM Training**: {args.start} to {eff_start} ({WARMUP_YEARS} yrs warmup, no trading)",
        f"> **Trading Period**: {eff_start} to {args.end}  |  **Universe**: {len(active)} stocks",
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
        f"| Avg Top-Stock Allocation | {avg_max_alloc:.1f}% |",
        f"| Days in Cash (Bear Guard) | {cash_days} ({cash_pct:.1f}%) |",
        "\n## Head-to-Head vs All Versions (7-8 Year Backtest)",
        "| Strategy | CAGR | Sharpe | Sortino | Max DD |",
        "| :--- | :---: | :---: | :---: | :---: |",
        f"| **V3.0 ML Fix-B (this)** | **{m['CAGR']:.2f}%** | **{m['Sharpe']:.3f}** | **{m['Sortino']:.3f}** | {m['Max Drawdown']:.2f}% |",
        "| V2 No-Stops (Heuristic) | ~26.99% | 1.075 | 1.609 | -23.23% |",
        "| V2 Bulletproof (Heuristic + EMA) | ~21.52% | 0.988 | 1.512 | -21.39% |",
        "| V3.0 Raw (T=0.05, no guard) | 7.45% | 0.318 | 1.23 | -88.4% |",
        "\n## Fix B Changes Explained",
        "| Fix | Change | Why |",
        "| :--- | :--- | :--- |",
        f"| Temperature | 0.05 -> {TEMPERATURE} | Reduces single-stock concentration from 48% avg to ~{avg_max_alloc:.0f}% avg |",
        f"| Max Stock Cap | None -> {int(MAX_STOCK_CAP*100)}% | Hard ceiling so no single stock can dominate |",
        "| Bear Guard | OFF -> ON | Nifty EMA-50 circuit breaker flushes to cash in bear markets |",
    ]
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"      Report -> {report_path}")
    print("\n[DONE] V3.0 Fix-B backtest complete!")


if __name__ == "__main__":
    main()
