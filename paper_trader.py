"""
paper_trader.py  —  6-Strategy Parallel Paper Trader
Version 1.0 Options A/B/C  vs  Version 2.0 Options A/B/C
Runs daily via GitHub Actions at 3:45 PM IST (10:15 AM UTC)
"""

import os, json, csv, datetime, warnings, sqlite3
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
TICKERS = [
    "RELIANCE.NS","TCS.NS","HDFCBANK.NS","HINDUNILVR.NS","MARUTI.NS",
    "SUNPHARMA.NS","LT.NS","TATASTEEL.NS","ULTRACEMCO.NS","BHARTIARTL.NS",
]
START_CAPITAL      = 100_000.0
RISK_FREE_RATE     = 0.05
FEE_RATE           = 0.001
WARMUP_DAYS        = 280
ADX_THRESHOLD      = 18.0
SUPERTREND_PERIOD  = 10
SUPERTREND_MULT    = 3.0
HMA_PERIOD         = 20
BB_PERIOD          = 20
BB_STD_MULT        = 2.0
RSI_PERIOD         = 14
CHOPPY_RSI_LIMIT   = 45

# Strategy registry
STRATEGIES = {
    "v1_a": {"version": "v1", "capital": "full",    "label": "V1 Option A", "color": "#3498db"},
    "v1_b": {"version": "v1", "capital": "dynamic", "label": "V1 Option B", "color": "#85c1e9"},
    "v1_c": {"version": "v1", "capital": "blend",   "label": "V1 Option C", "color": "#1a5276"},
    "v2_a": {"version": "v2", "capital": "full",    "label": "V2 Option A", "color": "#8e44ad"},
    "v2_b": {"version": "v2", "capital": "dynamic", "label": "V2 Option B", "color": "#d2b4de"},
    "v2_c": {"version": "v2", "capital": "blend",   "label": "V2 Option C", "color": "#4a235a"},
}

# Paths
STATES_DIR  = "states"
DATA_DIR    = "data"
CHARTS_DIR  = "charts"
REPORTS_DIR = "reports"


# ─────────────────────────────────────────────────────────────────────────────
#  INDICATOR FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────
def _wma(s, n):
    w = np.arange(1, n+1, dtype=float)
    return s.rolling(n).apply(lambda x: np.dot(x, w)/w.sum(), raw=True)

def _hma(s, n):
    return _wma(2*_wma(s, n//2) - _wma(s, n), int(np.sqrt(n)))

def _rsi(s, n=14):
    d = s.diff()
    g = d.where(d>0, 0.0).rolling(n).mean()
    l = (-d.where(d<0, 0.0)).rolling(n).mean()
    return 100 - 100/(1 + g/(l+1e-10))

def _atr(df, n=14):
    c  = df['Close'].shift(1)
    tr = pd.concat([df['High']-df['Low'],
                    (df['High']-c).abs(),
                    (df['Low'] -c).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def _adx(df, n=14):
    hd  = df['High']-df['High'].shift(1)
    ld  = df['Low'].shift(1)-df['Low']
    c   = df['Close'].shift(1)
    tr  = pd.concat([df['High']-df['Low'],
                     (df['High']-c).abs(),
                     (df['Low'] -c).abs()], axis=1).max(axis=1)
    pdm = np.where((hd>ld)&(hd>0), hd, 0.0)
    mdm = np.where((ld>hd)&(ld>0), ld, 0.0)
    atr_s = tr.ewm(alpha=1/n, adjust=False).mean()
    pdi = 100*pd.Series(pdm,index=df.index).ewm(alpha=1/n,adjust=False).mean()/(atr_s+1e-8)
    mdi = 100*pd.Series(mdm,index=df.index).ewm(alpha=1/n,adjust=False).mean()/(atr_s+1e-8)
    dx  = 100*(pdi-mdi).abs()/(pdi+mdi+1e-8)
    return dx.ewm(alpha=1/n, adjust=False).mean()

def _supertrend(df, n=10, m=3.0):
    atr  = _atr(df, n)
    hl2  = (df['High']+df['Low'])/2
    bu   = hl2 + m*atr
    bl   = hl2 - m*atr
    fu, fl = bu.copy(), bl.copy()
    close = df['Close']
    for i in range(n, len(df)):
        fu.iloc[i] = bu.iloc[i] if (bu.iloc[i]<fu.iloc[i-1] or close.iloc[i-1]>fu.iloc[i-1]) else fu.iloc[i-1]
        fl.iloc[i] = bl.iloc[i] if (bl.iloc[i]>fl.iloc[i-1] or close.iloc[i-1]<fl.iloc[i-1]) else fl.iloc[i-1]
    st   = pd.Series(np.nan, index=df.index)
    dir_ = pd.Series(1,      index=df.index)
    for i in range(n, len(df)):
        if   close.iloc[i] > fu.iloc[i-1]: dir_.iloc[i] = 1
        elif close.iloc[i] < fl.iloc[i-1]: dir_.iloc[i] = -1
        else:                               dir_.iloc[i] = dir_.iloc[i-1]
        st.iloc[i] = fl.iloc[i] if dir_.iloc[i]==1 else fu.iloc[i]
    return st, dir_

def _ema(s, n):  return s.ewm(span=n, adjust=False).mean()
def _sma(s, n):  return s.rolling(n).mean()

def _slope(s, n=20):
    def ls(x): return np.nan if np.isnan(x).any() else np.polyfit(np.arange(len(x)),x,1)[0]
    return s.rolling(n).apply(ls, raw=True)

def add_indicators(df):
    df    = df.copy()
    close = df['Close']
    df['ADX']      = _adx(df)
    df['RSI']      = _rsi(close, RSI_PERIOD)
    df['ST'], df['ST_Dir'] = _supertrend(df, SUPERTREND_PERIOD, SUPERTREND_MULT)
    df['HMA']      = _hma(close, HMA_PERIOD)
    df['BB_Std']   = close.rolling(BB_PERIOD).std()
    df['BB_Hug_Lo']= df['HMA'] - BB_STD_MULT*df['BB_Std']
    df['HMA_30']   = _hma(close, 30)
    df['EMA_30']   = _ema(close, 30)
    df['BB_Mid']   = _sma(close, 20)
    df['BB_Lower'] = df['BB_Mid'] - BB_STD_MULT*df['BB_Std']
    df['EMA_Fast'] = _ema(close, 20)
    df['EMA_Slow'] = _ema(close, 50)
    df['EMA_Trend']= _ema(close, 200)
    df['Slope']    = _slope(close.pct_change()*100, 20)
    return df.dropna()

def detect_regime(row):
    if row['Close']>row['EMA_Trend'] and row['Slope']>0 and row['ADX']>ADX_THRESHOLD:
        return 'Bullish'
    elif row['Close']<row['EMA_Trend'] and row['Slope']<0 and row['ADX']>ADX_THRESHOLD:
        return 'Bearish'
    return 'Choppy'

def softmax(x):
    if len(x)==0: return np.array([])
    e = np.exp(x - x.max()); return e/e.sum()


# ─────────────────────────────────────────────────────────────────────────────
#  STATE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  STATE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH = os.path.join(DATA_DIR, "trading_journal.db")

def state_path(sid):  return os.path.join(STATES_DIR, f"portfolio_{sid}.json")
def pnl_path(sid):    return os.path.join(DATA_DIR,   f"pnl_{sid}.csv")
def trades_path(sid): return os.path.join(DATA_DIR,   f"trades_{sid}.csv")
def chart_path(sid):  return os.path.join(CHARTS_DIR, f"pnl_{sid}.png")
def report_path(sid): return os.path.join(REPORTS_DIR,f"report_{sid}.md")

def load_state(sid):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT cash, holdings, start_date, start_capital, last_run FROM portfolio_states WHERE strategy_id = ?", (sid,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "cash": float(row[0]),
                "holdings": json.loads(row[1]),
                "start_date": str(row[2]),
                "start_capital": float(row[3]),
                "last_run": row[4]
            }
    except Exception as e:
        print(f"[DB WARN] Failed to load state for {sid} from DB: {e}. Falling back to JSON.")
        
    p = state_path(sid)
    if os.path.exists(p):
        with open(p) as f: return json.load(f)
    return {"cash": START_CAPITAL, "holdings": {},
            "start_date": str(datetime.date.today()),
            "start_capital": START_CAPITAL, "last_run": None}

def save_state(sid, state):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO portfolio_states (strategy_id, cash, holdings, start_date, start_capital, last_run)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            sid,
            float(state.get("cash", 100000.0)),
            json.dumps(state.get("holdings", {})),
            str(state.get("start_date", datetime.date.today())),
            float(state.get("start_capital", 100000.0)),
            state.get("last_run")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] Failed to save state to DB: {e}")

    try:
        with open(state_path(sid), 'w') as f: json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[IO ERROR] Failed to write JSON state fallback: {e}")

def append_pnl(sid, date, value, cash):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO pnl_records (strategy_id, date, portfolio_value, cash)
        VALUES (?, ?, ?, ?)
        """, (sid, str(date), float(value), float(cash)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] Failed to append PnL to DB: {e}")

    p = pnl_path(sid); exists = os.path.exists(p)
    try:
        with open(p, 'a', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['date','portfolio_value','cash'])
            if not exists: w.writeheader()
            w.writerow({'date': date, 'portfolio_value': round(value,2), 'cash': round(cash,2)})
    except Exception as e:
        print(f"[IO ERROR] Failed to append PnL CSV fallback: {e}")

def append_trades(sid, rows):
    if not rows: return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for row in rows:
            cursor.execute("""
            INSERT INTO trades (strategy_id, date, ticker, action, shares, price, value, regime, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sid,
                str(row.get('date')),
                str(row.get('ticker')),
                str(row.get('action')),
                float(row.get('shares', 0.0)),
                float(row.get('price', 0.0)),
                float(row.get('value', 0.0)),
                str(row.get('regime', 'Unknown')),
                str(row.get('reason', 'Rebalance'))
            ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB ERROR] Failed to append trades to DB: {e}")

    p = trades_path(sid); exists = os.path.exists(p)
    try:
        with open(p, 'a', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['date','ticker','action','shares','price','value','regime','reason'])
            if not exists: w.writeheader()
            w.writerows(rows)
    except Exception as e:
        print(f"[IO ERROR] Failed to append trades CSV fallback: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  SIGNAL GENERATION (runs ONE strategy for ONE day)
# ─────────────────────────────────────────────────────────────────────────────
def run_strategy(sid, cfg, ticker_data, current_prices, today):
    version = cfg['version']   # 'v1' or 'v2'
    cap_mode= cfg['capital']   # 'full' or 'dynamic'
    state   = load_state(sid)

    # Current equity
    assets = sum(state['holdings'].get(t,{}).get('shares',0)*current_prices.get(t,0) for t in TICKERS)
    equity = state['cash'] + assets

    # Signal pass
    eligible, scores = [], []
    for t, df in ticker_data.items():
        row    = df.iloc[-1]
        price  = row['Close']
        regime = detect_regime(row)
        adx, rsi = row['ADX'], row['RSI']

        if version == 'v2':
            st_dir = row['ST_Dir']
            hug_lo = row['BB_Hug_Lo']
            hug_mid= row['HMA']
            bb_std = row['BB_Std']
            if regime=='Bullish' and st_dir==1:
                eligible.append((t,regime,'Supertrend Bullish')); scores.append(adx/10.0)
            elif regime=='Choppy' and rsi<CHOPPY_RSI_LIMIT and price<hug_lo:
                z = (hug_mid-price)/(bb_std+1e-8)
                eligible.append((t,regime,f'HMA Band z={z:.2f}')); scores.append(z)
        else:
            hma30   = row['HMA_30']
            ema30   = row['EMA_30']
            bb_mid  = row['BB_Mid']
            bb_low  = row['BB_Lower']
            bb_std  = row['BB_Std']
            if regime=='Bullish' and hma30>ema30:
                eligible.append((t,regime,'HMA/EMA Cross')); scores.append(adx/10.0)
            elif regime=='Choppy' and rsi<35 and price<bb_low:
                z = (bb_mid-price)/(bb_std+1e-8)
                eligible.append((t,regime,f'BB z={z:.2f}')); scores.append(z)

    # Target allocation
    target_shares = {t: 0.0 for t in TICKERS}
    if eligible:
        weights = softmax(np.array(scores))
        if cap_mode == 'full':
            deployed = equity
        else:  # dynamic: scale by fraction of eligible
            deployed = equity * (len(eligible) / len(TICKERS))
        for idx,(t,_,_) in enumerate(eligible):
            target_shares[t] = (deployed*weights[idx]*(1-FEE_RATE)) / current_prices[t]

    # Execute virtual trades
    trade_rows   = []
    new_holdings = {}
    for t in TICKERS:
        cur_sh  = state['holdings'].get(t,{}).get('shares',0.0)
        tgt_sh  = target_shares.get(t,0.0)
        price   = current_prices.get(t,0.0)
        diff    = tgt_sh - cur_sh
        regime  = detect_regime(ticker_data[t].iloc[-1]) if t in ticker_data else 'Unknown'

        if abs(diff) < 0.001:
            if cur_sh > 0 and price > 0:
                new_holdings[t] = {'shares': cur_sh, 'avg_price': state['holdings'][t]['avg_price']}
            continue

        if diff > 0:
            old_avg = state['holdings'].get(t,{}).get('avg_price', price)
            new_avg = (cur_sh*old_avg + diff*price)/(cur_sh+diff) if (cur_sh+diff)>0 else price
            new_holdings[t] = {'shares': tgt_sh, 'avg_price': new_avg}
            state['cash'] -= diff*price
            action = 'BUY'
        else:
            if tgt_sh > 0:
                new_holdings[t] = {'shares': tgt_sh, 'avg_price': state['holdings'][t]['avg_price']}
            state['cash'] += abs(diff)*price*(1-FEE_RATE)
            action = 'SELL'

        reason = next((e[2] for e in eligible if e[0]==t), 'Rebalance/Exit')
        trade_rows.append({'date':today,'ticker':t,'action':action,
                           'shares':round(abs(diff),6),'price':round(price,2),
                           'value':round(abs(diff)*price,2),'regime':regime,'reason':reason})

    state['holdings'] = new_holdings
    assets_after = sum(new_holdings.get(t,{}).get('shares',0)*current_prices.get(t,0) for t in TICKERS)
    final_value  = state['cash'] + assets_after
    state['last_run'] = today

    save_state(sid, state)
    append_trades(sid, trade_rows)
    append_pnl(sid, today, final_value, state['cash'])
    return final_value, state, trade_rows


# ─────────────────────────────────────────────────────────────────────────────
#  COMPUTE METRICS FROM PNL CSV
# ─────────────────────────────────────────────────────────────────────────────
def compute_metrics(sid, start_date):
    p = pnl_path(sid)
    if not os.path.exists(p): return None
    df = pd.read_csv(p, parse_dates=['date'])
    if len(df) < 1: return None
    vals = df['portfolio_value'].values
    today_val = vals[-1]
    days_live = (pd.to_datetime(df['date'].iloc[-1]) - pd.to_datetime(start_date)).days
    years     = max(days_live/365.25, 1/365.25)
    total_ret = (today_val - START_CAPITAL)/START_CAPITAL*100
    cagr      = ((today_val/START_CAPITAL)**(1/years)-1)*100
    if len(vals) >= 2:
        daily_ret = pd.Series(vals).pct_change().dropna()
        vol       = daily_ret.std()*np.sqrt(252)*100
        sharpe    = (daily_ret.mean()-(RISK_FREE_RATE/252))/(daily_ret.std()+1e-8)*np.sqrt(252)
        down_std  = daily_ret[daily_ret<0].std()*np.sqrt(252)*100
        sortino   = (cagr - RISK_FREE_RATE*100)/(down_std+1e-8)
        roll_max  = pd.Series(vals).cummax()
        max_dd    = ((pd.Series(vals)-roll_max)/roll_max*100).min()
        pos_m     = (daily_ret>=0).sum(); neg_m = (daily_ret<0).sum()
        win_rate  = pos_m/(pos_m+neg_m)*100 if (pos_m+neg_m)>0 else 0
    else:
        vol = sharpe = sortino = win_rate = 0.0
        max_dd = 0.0
    return dict(today_val=today_val, total_ret=total_ret, cagr=cagr, vol=vol,
                sharpe=sharpe, sortino=sortino, max_dd=max_dd,
                days_live=days_live, win_rate=win_rate,
                dates=df['date'].values, values=vals)



# ─────────────────────────────────────────────────────────────────────────────
#  INDIVIDUAL CHART + REPORT
# ─────────────────────────────────────────────────────────────────────────────
def gen_individual_chart(sid, cfg, m):
    dates  = pd.to_datetime(m['dates'])
    values = m['values']
    color  = cfg['color']
    label  = cfg['label']
    fig, ax = plt.subplots(figsize=(13,4))
    ax.plot(dates, values, color=color, linewidth=2.2, label=label)
    ax.axhline(START_CAPITAL, color='#e74c3c', linestyle=':', alpha=0.6, linewidth=1.2, label='Start INR1L')
    ax.fill_between(dates, START_CAPITAL, values,
                    where=(values>=START_CAPITAL), alpha=0.10, color='#27ae60')
    ax.fill_between(dates, START_CAPITAL, values,
                    where=(values< START_CAPITAL), alpha=0.10, color='#e74c3c')
    ax.set_title(f"Live Paper PnL — {label}  |  Day {m['days_live']}",
                 fontsize=12, fontweight='bold', pad=10)
    ax.set_ylabel("Portfolio Value (INR)", fontsize=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"INR{x:,.0f}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True, linestyle=':', alpha=0.45)

    # Annotate current value
    ax.annotate(f"INR{values[-1]:,.0f}  ({m['total_ret']:+.2f}%)",
                xy=(dates[-1], values[-1]), xytext=(-90, 14),
                textcoords='offset points', fontsize=9,
                color=color, fontweight='bold',
                arrowprops=dict(arrowstyle='->', color=color, lw=1.2))
    plt.tight_layout()
    cp = chart_path(sid)
    plt.savefig(cp, dpi=150, bbox_inches='tight')
    plt.close()
    return cp

def gen_individual_report(sid, cfg, m, state, holdings_snap):
    label = cfg['label']
    lines = []
    lines.append(f"# Paper Trading Report — {label}\n")
    lines.append(f"> **Last Updated**: {state['last_run']}  |  **Days Live**: {m['days_live']}\n")
    lines.append(f"## Portfolio Summary\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"| :--- | :---: |")
    lines.append(f"| Start Capital | **INR{START_CAPITAL:,.0f}** |")
    lines.append(f"| Current Value | **INR{m['today_val']:,.2f}** |")
    lines.append(f"| Total Return | **{m['total_ret']:+.2f}%** |")
    lines.append(f"| CAGR (annualised) | **{m['cagr']:+.2f}%** |")
    lines.append(f"| Annual Volatility | **{m['vol']:.2f}%** |")
    lines.append(f"| Sharpe Ratio (Rf=5%) | **{m['sharpe']:.3f}** |")
    lines.append(f"| Sortino Ratio | **{m['sortino']:.3f}** |")
    lines.append(f"| Max Drawdown | **{m['max_dd']:.2f}%** |")
    lines.append(f"| Daily Win Rate | **{m['win_rate']:.1f}%** |\n")

    lines.append(f"## Current Holdings\n")
    lines.append(f"| Ticker | Shares | Avg Buy | Current | Unrealised PnL |")
    lines.append(f"| :--- | :---: | :---: | :---: | :---: |")
    for h in holdings_snap:
        pnl = (h['current_price']-h['avg_price'])/h['avg_price']*100
        lines.append(f"| {h['ticker']} | {h['shares']:.4f} | INR{h['avg_price']:.2f} | INR{h['current_price']:.2f} | **{pnl:+.2f}%** |")
    lines.append(f"\n**Cash on hand**: INR{state['cash']:,.2f}\n")

    cp = os.path.join('..', CHARTS_DIR, f"pnl_{sid}.png")
    lines.append(f"## PnL Chart\n")
    lines.append(f"![PnL Chart]({cp})\n")

    tp = trades_path(sid)
    if os.path.exists(tp):
        tdf = pd.read_csv(tp)
        lines.append(f"## Recent Trades (Last 15)\n")
        lines.append(f"| Date | Ticker | Action | Shares | Price | Regime |")
        lines.append(f"| :--- | :--- | :--- | :---: | :---: | :--- |")
        for _, r in tdf.tail(15).iloc[::-1].iterrows():
            lines.append(f"| {r['date']} | {r['ticker']} | **{r['action']}** | "
                         f"{float(r['shares']):.4f} | INR{float(r['price']):.2f} | {r['regime']} |")

    with open(report_path(sid), 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
#  COMPARISON CHARTS
# ─────────────────────────────────────────────────────────────────────────────
def gen_comparison_curves(metrics_map):
    fig, axes = plt.subplots(3, 2, figsize=(16, 13), facecolor='#0d0d0d')
    fig.suptitle("All 6 Strategies — Individual Live PnL Curves", fontsize=14,
                 fontweight='bold', color='white', y=1.01)
    order = ['v1_a','v1_b','v1_c','v2_a','v2_b','v2_c']
    for ax, sid in zip(axes.flatten(), order):
        if sid not in metrics_map: continue
        cfg = STRATEGIES[sid]; m = metrics_map[sid]
        dates  = pd.to_datetime(m['dates']); values = m['values']
        color  = cfg['color']
        ax.set_facecolor('#1a1a2e')
        ax.plot(dates, values, color=color, linewidth=2)
        ax.axhline(START_CAPITAL, color='#e74c3c', linestyle=':', alpha=0.6, linewidth=1)
        ax.fill_between(dates, START_CAPITAL, values,
                        where=(values>=START_CAPITAL), alpha=0.12, color='#27ae60')
        ax.fill_between(dates, START_CAPITAL, values,
                        where=(values< START_CAPITAL), alpha=0.12, color='#e74c3c')
        ax.set_title(f"{cfg['label']}  |  {m['total_ret']:+.2f}%  |  Sharpe {m['sharpe']:.2f}",
                     fontsize=10, fontweight='bold', color='white', pad=6)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"INR{x/1e3:.0f}K"))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'))
        ax.tick_params(colors='#aaaaaa', labelsize=8)
        for spine in ax.spines.values(): spine.set_edgecolor('#333')
        ax.grid(True, linestyle=':', alpha=0.25, color='#555')
    plt.tight_layout(rect=[0,0,1,0.99])
    cp = os.path.join(CHARTS_DIR, "comparison_curves.png")
    plt.savefig(cp, dpi=150, bbox_inches='tight', facecolor='#0d0d0d')
    plt.close()
    return cp

def gen_comparison_bar(metrics_map):
    sids   = [s for s in ['v1_a','v1_b','v1_c','v2_a','v2_b','v2_c'] if s in metrics_map]
    labels = [STRATEGIES[s]['label'] for s in sids]
    colors = [STRATEGIES[s]['color'] for s in sids]

    metrics_to_plot = [
        ('total_ret',  'Total Return (%)',    False),
        ('cagr',       'CAGR (%)',            False),
        ('sharpe',     'Sharpe Ratio',        False),
        ('max_dd',     'Max Drawdown (%)',     True),   # lower is better
    ]

    fig, axes = plt.subplots(1, 4, figsize=(18, 6), facecolor='#0d0d0d')
    fig.suptitle("Strategy Comparison — Key Metrics (Live Paper Trading)",
                 fontsize=13, fontweight='bold', color='white', y=1.02)

    for ax, (key, title, inverse) in zip(axes, metrics_to_plot):
        vals = [metrics_map[s][key] for s in sids]
        bars = ax.bar(labels, vals, color=colors, edgecolor='none', alpha=0.88, width=0.55)
        ax.set_facecolor('#1a1a2e')
        ax.set_title(title, fontsize=11, fontweight='bold', color='white', pad=8)
        ax.tick_params(colors='#aaaaaa', labelsize=8)
        ax.set_xticklabels(labels, rotation=35, ha='right', fontsize=8)
        for spine in ax.spines.values(): spine.set_edgecolor('#333')
        ax.grid(True, axis='y', linestyle=':', alpha=0.3, color='#555')
        ax.axhline(0, color='#e74c3c', linewidth=0.8, linestyle='-')

        # Value label on top of each bar
        for bar, val in zip(bars, vals):
            ypos = bar.get_height() if val>=0 else bar.get_height()
            offset = 0.3 if val>=0 else -2.5
            ax.text(bar.get_x()+bar.get_width()/2, ypos+offset,
                    f"{val:+.2f}%" if key!='sharpe' else f"{val:.3f}",
                    ha='center', va='bottom', fontsize=8, color='white', fontweight='bold')

        # Star best performer (guard against all-equal on Day 1)
        if len(vals) > 0 and not all(v == vals[0] for v in vals):
            best_idx = int(np.argmax(vals)) if not inverse else int(np.argmin(vals))
            bar_patches = [c for c in ax.get_children() if hasattr(c, 'get_facecolor') and hasattr(c, 'set_edgecolor')]
            if best_idx < len(bar_patches):
                bar_patches[best_idx].set_edgecolor('#f1c40f')
                bar_patches[best_idx].set_linewidth(2.5)

    plt.tight_layout()
    cp = os.path.join(CHARTS_DIR, "comparison_bar.png")
    plt.savefig(cp, dpi=150, bbox_inches='tight', facecolor='#0d0d0d')
    plt.close()
    return cp


# ─────────────────────────────────────────────────────────────────────────────
#  MASTER REPORT
# ─────────────────────────────────────────────────────────────────────────────
def gen_master_report(metrics_map, today):
    sids   = ['v1_a','v1_b','v1_c','v2_a','v2_b','v2_c']
    lines  = []
    lines.append(f"# Master Report — All 6 Strategies Live Comparison\n")
    lines.append(f"> **Date**: {today}  |  **Starting Capital**: INR{START_CAPITAL:,.0f} each\n")

    lines.append(f"## Performance Leaderboard\n")
    lines.append(f"| Rank | Strategy | Portfolio Value | Total Return | CAGR | Sharpe | Max DD | Win Rate |")
    lines.append(f"| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |")

    ranked = sorted(
        [(s, metrics_map[s]) for s in sids if s in metrics_map],
        key=lambda x: x[1]['total_ret'], reverse=True
    )
    medals = ['🥇','🥈','🥉','4️⃣','5️⃣','6️⃣']
    for rank,(sid,m) in enumerate(ranked):
        label = STRATEGIES[sid]['label']
        lines.append(f"| {medals[rank]} | **{label}** | INR{m['today_val']:,.2f} | "
                     f"**{m['total_ret']:+.2f}%** | {m['cagr']:+.2f}% | "
                     f"{m['sharpe']:.3f} | {m['max_dd']:.2f}% | {m['win_rate']:.1f}% |")

    lines.append(f"\n> ⭐ Yellow border on bar chart = best performer in each metric.\n")

    # Charts
    lines.append(f"## Individual PnL Curves (All 6)\n")
    lines.append(f"![All Curves]({os.path.join('..', CHARTS_DIR,'comparison_curves.png')})\n")
    lines.append(f"## Metric Comparison Bar Chart\n")
    lines.append(f"![Bar Chart]({os.path.join('..', CHARTS_DIR,'comparison_bar.png')})\n")

    lines.append(f"## Quick Links — Individual Reports\n")
    for sid in sids:
        if sid in metrics_map:
            label = STRATEGIES[sid]['label']
            m = metrics_map[sid]
            lines.append(f"- **[{label}](report_{sid}.md)** — INR{m['today_val']:,.2f} | {m['total_ret']:+.2f}% | Sharpe {m['sharpe']:.3f}")

    lines.append(f"\n## Strategy Descriptions\n")
    lines.append(f"| Strategy | Regime Engine | Entry Logic | Capital Mode |")
    lines.append(f"| :--- | :--- | :--- | :--- |")
    lines.append(f"| V1 Option A | EMA/HMA Crossover | HMA>EMA (Bull), BB lower band (Choppy) | 100% deployed |")
    lines.append(f"| V1 Option B | EMA/HMA Crossover | Same as A | Dynamic (scales with breadth) |")
    lines.append(f"| V1 Option C | EMA/HMA Crossover | Same as A | 70% A + 30% B blend |")
    lines.append(f"| V2 Option A | Supertrend + HMA-BB | Supertrend green (Bull), HMA Band (Choppy) | 100% deployed |")
    lines.append(f"| V2 Option B | Supertrend + HMA-BB | Same as A | Dynamic (scales with breadth) |")
    lines.append(f"| V2 Option C | Supertrend + HMA-BB | Same as A | 70% A + 30% B blend |")

    with open(os.path.join(REPORTS_DIR, 'master_report.md'), 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print("  Master report saved.")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    today = str(datetime.date.today())
    print(f"\n{'='*60}")
    print(f"  6-Strategy Parallel Paper Trader  |  {today}")
    print(f"{'='*60}")

    # ── Load data ONCE (shared across all strategies) ─────────────
    end_dt   = datetime.date.today() + datetime.timedelta(days=1)
    start_dt = datetime.date.today() - datetime.timedelta(days=WARMUP_DAYS+30)
    ticker_data, current_prices = {}, {}

    for t in TICKERS:
        df = yf.download(t, start=str(start_dt), end=str(end_dt), progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Open','High','Low','Close','Volume']].copy()
        df = add_indicators(df)
        if df.empty: continue
        ticker_data[t]   = df
        current_prices[t]= df['Close'].iloc[-1]
        print(f"  {t:18s} INR{current_prices[t]:>10,.2f}")

    print(f"\n  Running all 6 strategies...\n")

    # ── Run base strategies (A + B, both versions) ────────────────
    final_values, states_map = {}, {}
    base_sids = ['v1_a','v1_b','v2_a','v2_b']

    for sid in base_sids:
        cfg = STRATEGIES[sid]
        val, state, trades = run_strategy(sid, cfg, ticker_data, current_prices, today)
        final_values[sid]  = val
        states_map[sid]    = state
        ret = (val-START_CAPITAL)/START_CAPITAL*100
        print(f"  {cfg['label']:16s}  INR{val:>10,.2f}  ({ret:+.2f}%)")

    # ── Compute C blends (70% A + 30% B) ─────────────────────────
    for ver in ['v1','v2']:
        sid_a, sid_b, sid_c = f'{ver}_a', f'{ver}_b', f'{ver}_c'
        val_c = 0.7*final_values[sid_a] + 0.3*final_values[sid_b]
        final_values[sid_c] = val_c

        # Build synthetic PnL for C by blending A and B histories
        pa = pd.read_csv(pnl_path(sid_a), parse_dates=['date'])
        pb = pd.read_csv(pnl_path(sid_b), parse_dates=['date'])
        merged = pa.merge(pb, on='date', suffixes=('_a','_b'))
        merged['portfolio_value'] = 0.7*merged['portfolio_value_a'] + 0.3*merged['portfolio_value_b']
        merged['cash']            = 0.7*merged['cash_a']            + 0.3*merged['cash_b']
        merged[['date','portfolio_value','cash']].to_csv(pnl_path(sid_c), index=False)

        # Synthetic state for C
        state_a = load_state(sid_a); state_b = load_state(sid_b)
        blended_holdings = {}
        all_tickers = set(list(state_a['holdings'].keys()) + list(state_b['holdings'].keys()))
        for t in all_tickers:
            sh_a = state_a['holdings'].get(t,{}).get('shares',0)*0.7
            sh_b = state_b['holdings'].get(t,{}).get('shares',0)*0.3
            p_a  = state_a['holdings'].get(t,{}).get('avg_price', current_prices.get(t,1))
            p_b  = state_b['holdings'].get(t,{}).get('avg_price', current_prices.get(t,1))
            sh   = sh_a + sh_b
            avg  = (sh_a*p_a + sh_b*p_b)/sh if sh>0 else 0
            if sh>0: blended_holdings[t] = {'shares':sh,'avg_price':avg}
        state_c = {'cash': 0.7*state_a['cash']+0.3*state_b['cash'],
                   'holdings': blended_holdings,
                   'start_date': state_a['start_date'],
                   'start_capital': START_CAPITAL,
                   'last_run': today}
        save_state(sid_c, state_c)
        states_map[sid_c] = state_c
        ret = (val_c-START_CAPITAL)/START_CAPITAL*100
        print(f"  {STRATEGIES[sid_c]['label']:16s}  INR{val_c:>10,.2f}  ({ret:+.2f}%)  [blended]")

    # ── Compute metrics & generate charts + reports ───────────────
    print(f"\n  Generating charts and reports...")
    metrics_map = {}
    for sid in STRATEGIES:
        state  = states_map.get(sid, load_state(sid))
        m = compute_metrics(sid, state['start_date'])
        if m is None: continue
        metrics_map[sid] = m

        # Individual chart
        gen_individual_chart(sid, STRATEGIES[sid], m)

        # Individual report — build holdings snapshot
        snap = [{'ticker':t,'shares':info['shares'],
                 'avg_price':info['avg_price'],
                 'current_price':current_prices.get(t,0)}
                for t,info in state['holdings'].items() if info.get('shares',0)>0]
        gen_individual_report(sid, STRATEGIES[sid], m, state, snap)
        print(f"  {STRATEGIES[sid]['label']:16s}  charts + report done.")

    # ── Comparison charts + master report ────────────────────────
    gen_comparison_curves(metrics_map)
    gen_comparison_bar(metrics_map)
    gen_master_report(metrics_map, today)

    # ── Final summary ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    best = max(metrics_map.items(), key=lambda x: x[1]['total_ret'])
    print(f"  Best performer today: {STRATEGIES[best[0]]['label']}  ({best[1]['total_ret']:+.2f}%)")
    print(f"  All reports in:  {REPORTS_DIR}/")
    print(f"  All charts  in:  {CHARTS_DIR}/")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()


