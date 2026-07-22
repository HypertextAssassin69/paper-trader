import os
import json
import urllib.request
import urllib.parse
import webbrowser
import http.server
import socketserver
import threading
import time
import datetime
import pandas as pd
import yfinance as yf

# Load .env variables manually to avoid python-dotenv dependency
def load_env():
    env_vars = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

ENV = load_env()
API_KEY = ENV.get("UPSTOX_API_KEY")
API_SECRET = ENV.get("UPSTOX_API_SECRET")
REDIRECT_URI = ENV.get("UPSTOX_REDIRECT_URI", "http://127.0.0.1:5000/")
TOKEN_FILE = "combined_breakout_strategy/upstox_token.json"

# Local Server variables to capture Auth Code
captured_code = None
server_running = True

class AuthorizationHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Suppress server console logs
        
    def do_GET(self):
        global captured_code, server_running
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        if "code" in query_params:
            captured_code = query_params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            
            html = """
            <html>
            <head><title>Login Successful</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 50px; background-color: #0d1117; color: #58a6ff;">
                <h1 style="color: #2ea44f;">✔ Login Successful!</h1>
                <p style="color: #c9d1d9;">You have successfully authenticated with Upstox.</p>
                <p style="color: #8b949e;">You can close this browser tab now and return to the terminal.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
            server_running = False
        else:
            self.send_response(400)
            self.end_headers()

def run_local_server():
    global server_running
    port = int(urllib.parse.urlparse(REDIRECT_URI).port or 5000)
    with socketserver.TCPServer(("127.0.0.1", port), AuthorizationHandler) as httpd:
        while server_running:
            httpd.handle_request()

def get_access_token():
    # 1. Try to load saved token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            token_data = json.load(f)
            # Upstox tokens usually last 24h, check if created today
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            if token_data.get("date") == today_str:
                print("[INFO] Using active session token from cache.")
                return token_data["access_token"]

    # 2. Re-authenticate
    global captured_code, server_running
    captured_code = None
    server_running = True
    
    print("[INFO] Starting temporary authentication server...")
    server_thread = threading.Thread(target=run_local_server)
    server_thread.daemon = True
    server_thread.start()

    login_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={API_KEY}&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    )
    
    print(f"[INFO] Opening browser for authentication...")
    print(f"[URL] {login_url}")
    webbrowser.open(login_url)

    print("[WAIT] Waiting for you to log in on the browser...")
    while captured_code is None:
        time.sleep(1)

    # 3. Exchange code for access token
    print("[INFO] Exchanging Authorization Code for Access Token...")
    token_url = "https://api.upstox.com/v2/login/authorization/token"
    headers = {
        "accept": "application/json",
        "Api-Version": "2.0",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "code": captured_code,
        "client_id": API_KEY,
        "client_secret": API_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    req_data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(token_url, data=req_data, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req) as res:
            resp = json.loads(res.read().decode("utf-8"))
            access_token = resp["access_token"]
            
            # Cache the token
            with open(TOKEN_FILE, "w") as f:
                json.dump({
                    "access_token": access_token,
                    "date": datetime.date.today().strftime("%Y-%m-%d")
                }, f)
            print("[SUCCESS] Authentication complete and token cached!")
            return access_token
    except Exception as e:
        print(f"[ERROR] Failed to get access token: {e}")
        return None

def get_upstox_instrument_key(symbol, access_token):
    sym = symbol.replace('.NS', '')
    # Upstox V2 instrument search API
    url = f"https://api.upstox.com/v2/instruments/search?query={sym}&exchange=NSE"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("accept", "application/json")
    try:
        with urllib.request.urlopen(req) as res:
            resp = json.loads(res.read().decode("utf-8"))
            if resp.get("status") == "success" and resp.get("data"):
                # Filter for exact symbol and EQUITY segment
                for item in resp["data"]:
                    if item.get("trading_symbol") == sym and item.get("instrument_type") == "EQUITY":
                        return item["instrument_key"]
    except Exception as e:
        print(f"[ERROR] Instrument key search failed for {symbol}: {e}")
    return None

def get_account_balance(access_token):
    url = "https://api.upstox.com/v2/user/profile" # Or profile check
    # In Upstox, the user margin is at: /v2/user/get-margin
    url = "https://api.upstox.com/v2/user/get-margin"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("accept", "application/json")
    try:
        with urllib.request.urlopen(req) as res:
            resp = json.loads(res.read().decode("utf-8"))
            if resp.get("status") == "success" and resp.get("data"):
                # equity net margin
                return float(resp["data"]["equity"]["available_margin"])
    except Exception as e:
        print(f"[ERROR] Failed to retrieve account margin: {e}")
    return 100000.0 # Default fallback

def place_upstox_order(instrument_key, transaction_type, quantity, access_token):
    url = "https://api.upstox.com/v2/order/place"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "accept": "application/json",
        "Api-Version": "2.0"
    }
    payload = {
        "quantity": int(quantity),
        "product": "DELIVERY",
        "validity": "DAY",
        "price": 0.0,
        "tag": "breakout_strat",
        "instrument_token": instrument_key,
        "order_type": "MARKET",
        "transaction_type": transaction_type,
        "disclosed_quantity": 0,
        "trigger_price": 0.0,
        "is_amo": False
    }
    
    data_json = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_json, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as res:
            resp = json.loads(res.read().decode("utf-8"))
            if resp.get("status") == "success":
                order_id = resp["data"]["order_id"]
                print(f"[SUCCESS] Order placed! ID: {order_id} | {transaction_type} {quantity} shares")
                return order_id
    except Exception as e:
        print(f"[ERROR] Failed to place order: {e}")
    return None

def run_trading_loop(access_token):
    print("\n[START] Running Portfolio Allocation & Trading Logic...")
    
    # 1. Download market data to check regime
    print("Checking market regime...")
    nifty = yf.download(BENCHMARK_TICKER, period="90d", progress=False)
    nifty_close = nifty['Close'].dropna()
    nifty_ema50 = nifty_close.ewm(span=50, adjust=False).mean()
    
    n_close = float(nifty_close.iloc[-1])
    n_ema = float(nifty_ema50.iloc[-1])
    bull = n_close > n_ema
    print(f"Nifty 50 Close: {n_close:.2f} | 50 EMA: {n_ema:.2f} | Regime: {'BULL (Safe)' if bull else 'BEAR (Unsafe)'}")
    
    # 2. Get current holdings from Upstox
    print("Fetching current Upstox holdings...")
    holdings_url = "https://api.upstox.com/v2/portfolio/long-term-holdings"
    req = urllib.request.Request(holdings_url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("accept", "application/json")
    
    current_holdings = {}
    try:
        with urllib.request.urlopen(req) as res:
            resp = json.loads(res.read().decode("utf-8"))
            if resp.get("status") == "success" and resp.get("data"):
                for item in resp["data"]:
                    symbol = item["trading_symbol"]
                    qty = int(item["quantity"])
                    if qty > 0:
                        current_holdings[symbol] = {
                            "qty": qty,
                            "instrument_key": item["instrument_token"],
                            "ltp": float(item["last_price"])
                        }
    except Exception as e:
        print(f"[ERROR] Failed to fetch holdings: {e}")
        return

    print(f"Current portfolio holdings: {list(current_holdings.keys())}")

    # 3. Action Logic
    if not bull:
        # BEAR REGIME: Exit all non-LiquidBeES equity positions to cash
        print("\n[BEAR ALERT] Exit to Cash! Liquidating holdings...")
        for sym, info in current_holdings.items():
            if "LIQUID" in sym or "BEES" in sym: continue # Keep cash/liquid assets
            print(f"Placing SELL order for {sym} | Quantity: {info['qty']}")
            place_upstox_order(info["instrument_key"], "SELL", info["qty"], access_token)
    else:
        # BULL REGIME: Execute 6-Month Rebalance / Re-entry
        print("\n[BULL REGIME] Running scanner to calculate target portfolio...")
        # Get target breakout stocks
        long_data = yf.download(MIDCAP_TICKERS, period="1000d", group_by="ticker", progress=False)
        scores = {}
        for t in MIDCAP_TICKERS:
            c = long_data[t]['Close'].dropna()
            if len(c) < 252: continue
            ret_1y = (c.iloc[-1] - c.iloc[-252]) / c.iloc[-252]
            max_3y = c.rolling(min(len(c), 756)).max().iloc[-1]
            proximity = c.iloc[-1] / max_3y
            
            if proximity >= 0.85:
                scores[t] = ret_1y * 0.50 + proximity * 0.50
                
        top_5 = sorted(scores, key=scores.get, reverse=True)[:5]
        target_symbols = [s.replace('.NS', '') for s in top_5]
        print(f"Target Breakout Momentum Portfolio: {target_symbols}")

        # A. Sell positions that are NOT in the target portfolio
        for sym, info in current_holdings.items():
            if sym not in target_symbols and "LIQUID" not in sym and "BEES" not in sym:
                print(f"Stock {sym} is no longer in the Top 5. Selling...")
                place_upstox_order(info["instrument_key"], "SELL", info["qty"], access_token)

        # B. Buy new target positions
        # Fetch account capital
        capital = get_account_balance(access_token)
        print(f"Available capital for deployment: INR {capital:.2f}")
        slot_capital = capital / 5.0
        
        for sym in target_symbols:
            if sym in current_holdings:
                print(f"Already holding target stock {sym}. No action needed.")
            else:
                key = get_upstox_instrument_key(sym, access_token)
                if not key:
                    print(f"[WARNING] Could not resolve Upstox key for {sym}. Skipping buy.")
                    continue
                # Get current price
                quotes_url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_key={key}"
                q_req = urllib.request.Request(quotes_url, method="GET")
                q_req.add_header("Authorization", f"Bearer {access_token}")
                q_req.add_header("accept", "application/json")
                try:
                    with urllib.request.urlopen(q_req) as q_res:
                        q_resp = json.loads(q_res.read().decode("utf-8"))
                        price = float(q_resp["data"][key]["last_price"])
                        qty = int(slot_capital / price)
                        if qty > 0:
                            print(f"Buying new target stock {sym} | Qty: {qty} @ INR {price:.2f}")
                            place_upstox_order(key, "BUY", qty, access_token)
                except Exception as e:
                    print(f"[ERROR] Failed to get price/buy {sym}: {e}")

    print("\n[COMPLETE] Trading routine finished successfully!")

def main():
    if not API_KEY or not API_SECRET:
        print("[CRITICAL ERROR] Upstox credentials are not set in the .env file.")
        print("Please create a .env file and fill in UPSTOX_API_KEY and UPSTOX_API_SECRET.")
        return
        
    access_token = get_access_token()
    if access_token:
        run_trading_loop(access_token)
    else:
        print("[CRITICAL ERROR] Failed to authenticate with Upstox.")

if __name__ == "__main__":
    main()
