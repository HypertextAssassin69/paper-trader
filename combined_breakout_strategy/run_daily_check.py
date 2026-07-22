import os
import json
import urllib.request
import urllib.parse
import datetime
import pandas as pd
import yfinance as yf

# Configurations
BENCHMARK_TICKER = "^NSEI"
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

def send_whatsapp_message(text):
    phone = os.getenv("WHATSAPP_PHONE")
    apikey = os.getenv("WHATSAPP_API_KEY")
    if not phone or not apikey:
        print("[INFO] WhatsApp credentials not set. Skipping WhatsApp alert.")
        return
    
    encoded_text = urllib.parse.quote(text)
    url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_text}&apikey={apikey}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        with urllib.request.urlopen(req) as res:
            resp_text = res.read().decode("utf-8")
            print(f"[SUCCESS] WhatsApp alert sent: {resp_text}")
    except Exception as e:
        print(f"[ERROR] Failed to send WhatsApp message: {e}")

def send_ntfy_alert(message, title="🚨 Breakout Strategy Action Required!"):
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        print("[INFO] NTFY_TOPIC not set. Skipping NTFY alert.")
        return
        
    url = f"https://ntfy.sh/{topic}"
    login_url = "https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id=da4dc2ca-2130-4ce6-a3e2-ed2a15096346&redirect_uri=http://127.0.0.1:5000/"
    headers = {
        "Title": title,
        "Priority": "high",
        "Tags": "warning,rotating_light",
        "Click": login_url
    }
    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        headers=headers,
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as res:
            print("[SUCCESS] NTFY alert sent successfully!")
    except Exception as e:
        print(f"[ERROR] Failed to send NTFY alert: {e}")

def create_github_issue(title, body):
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    if not token or not repo:
        print("[INFO] GITHUB_TOKEN or GITHUB_REPOSITORY not set. Skipping GitHub Issue alert.")
        return
        
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    
    payload = json.dumps({"title": title, "body": body}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as res:
            print("[SUCCESS] Created GitHub Issue alert successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to create GitHub Issue: {e}")

def main():
    print(f"Running Daily Check for Breakout-Momentum Strategy...")
    today = datetime.date.today()
    
    # Download Nifty 50 and Midcap data
    tickers_to_download = [BENCHMARK_TICKER] + MIDCAP_TICKERS
    data = yf.download(tickers_to_download, period="90d", group_by="ticker", progress=False)
    
    # Check Nifty 50 Regime
    nifty_close = data[BENCHMARK_TICKER]['Close'].dropna()
    nifty_ema50 = nifty_close.ewm(span=50, adjust=False).mean()
    
    n_close = float(nifty_close.iloc[-1])
    n_ema = float(nifty_ema50.iloc[-1])
    bull = n_close > n_ema
    regime = "BULL (Market Safe)" if bull else "BEAR (Market Unsafe - Exit to Cash)"
    
    # Check if Nifty regime crossed the EMA50 yesterday vs today
    n_prev_close = float(nifty_close.iloc[-2])
    n_prev_ema = float(nifty_ema50.iloc[-2])
    prev_bull = n_prev_close > n_prev_ema
    
    regime_shift = prev_bull != bull
    is_friday = today.weekday() == 4 # Friday check
    
    # Check if today is a rebalance month start (Jan or July) and within the first 5 days
    is_rebalance_window = today.month in [1, 7] and today.day <= 5
    
    alert_title = ""
    alert_body = ""
    
    # Scenario A: Regime Shift (Immediate Action Required)
    if regime_shift:
        if bull:
            alert_title = "🚨 ACTION REQUIRED: Nifty back in BULL Regime - Buy stocks!"
            alert_body = (
                f"### Nifty 50 Crossed ABOVE the 50-day EMA\n\n"
                f"* **Current Nifty Close**: {n_close:.2f}\n"
                f"* **Current 50-day EMA**: {n_ema:.2f}\n"
                f"**Instruction**: Sell your Liquid BeES holdings and buy back into your target momentum stocks immediately."
            )
        else:
            alert_title = "🚨 ACTION REQUIRED: Nifty broken into BEAR Regime - Sell to Cash!"
            alert_body = (
                f"### Nifty 50 Crossed BELOW the 50-day EMA\n\n"
                f"* **Current Nifty Close**: {n_close:.2f}\n"
                f"* **Current 50-day EMA**: {n_ema:.2f}\n"
                f"**Instruction**: Liquidate all your 5 stock positions immediately and park 100% of your capital in Liquid BeES/LIQUIDCASE ETF."
            )
            
    # Scenario B: Weekly Friday Status Update
    elif is_friday:
        alert_title = f"📅 Friday Checkup: Nifty is in {regime} mode"
        alert_body = (
            f"### Weekly Trend Summary ({today.strftime('%Y-%m-%d')})\n\n"
            f"* **Nifty 50 Close**: {n_close:.2f}\n"
            f"* **Nifty 50 EMA**: {n_ema:.2f}\n"
            f"* **Status**: {'Hold positions (Bull market)' if bull else 'Hold Cash / Liquid BeES (Bear market)'}\n\n"
            f"No action required unless you missed a previous exit trigger."
        )

    # Scenario C: 6-Month Rebalance Window (Compute top 5 stocks to buy)
    if is_rebalance_window and (today.day == 1 or regime_shift or is_friday):
        # Calculate breakouts
        print("Computing top 5 breakout momentum stocks...")
        long_data = yf.download(MIDCAP_TICKERS, period="1000d", group_by="ticker", progress=False)
        scores = {}
        for t in MIDCAP_TICKERS:
            c = long_data[t]['Close'].dropna()
            if len(c) < 252: continue
            ret_1y = (c.iloc[-1] - c.iloc[-252]) / c.iloc[-252]
            
            # 3-Year high proximity
            max_3y = c.rolling(min(len(c), 756)).max().iloc[-1]
            proximity = c.iloc[-1] / max_3y
            
            if proximity >= 0.85:
                scores[t] = ret_1y * 0.50 + proximity * 0.50
                
        top_5 = sorted(scores, key=scores.get, reverse=True)[:5]
        
        rebal_title = f"📅 6-Month Rebalance Alert: Top 5 Stocks to Buy!"
        rebal_body = (
            f"### Target Portfolio for the Next 6 Months:\n\n"
            f"1. **{top_5[0]}**\n"
            f"2. **{top_5[1]}**\n"
            f"3. **{top_5[2]}**\n"
            f"4. **{top_5[3]}**\n"
            f"5. **{top_5[4]}**\n\n"
            f"**Execution Instruction**:\n"
            f"* If Nifty is safe, allocate **20% of your capital** to each stock.\n"
            f"* If Nifty is unsafe, keep holding Cash/Liquid BeES instead."
        )
        # Create issue for rebalance
        create_github_issue(rebal_title, rebal_body)
        send_whatsapp_message(f"📅 6-Month Rebalance Alert!\nTarget 5 Stocks to Buy:\n1. {top_5[0].replace('.NS','')}\n2. {top_5[1].replace('.NS','')}\n3. {top_5[2].replace('.NS','')}\n4. {top_5[3].replace('.NS','')}\n5. {top_5[4].replace('.NS','')}")
        send_ntfy_alert(f"Target 5 Stocks to Buy:\n1. {top_5[0].replace('.NS','')}\n2. {top_5[1].replace('.NS','')}\n3. {top_5[2].replace('.NS','')}\n4. {top_5[3].replace('.NS','')}\n5. {top_5[4].replace('.NS','')}", rebal_title)

    # Trigger alert if set
    if alert_title:
        create_github_issue(alert_title, alert_body)
        send_whatsapp_message(f"{alert_title}\n\nNifty Close: {n_close:.1f} | 50 EMA: {n_ema:.1f}")
        send_ntfy_alert(f"Nifty Close: {n_close:.1f} | 50 EMA: {n_ema:.1f}", alert_title)
    else:
        print(f"Daily check complete. Regime: {regime}. No alerts triggered today.")

if __name__ == "__main__":
    main()
