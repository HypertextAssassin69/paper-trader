import os
import sys
import yfinance as yf

# List of 40 highly liquid Nifty stock tickers + Nifty 50 Index (^NSEI)
TICKERS = [
    "^NSEI",  # Nifty 50 Index (Regime Filter)
    "^INDIAVIX",  # India VIX (Dynamic Volatility Scaling)
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "KOTAKBANK.NS", "SBIN.NS", "LT.NS", "ITC.NS", "HINDUNILVR.NS",
    "AXISBANK.NS", "BHARTIARTL.NS", "MARUTI.NS", "TATASTEEL.NS", "WIPRO.NS",
    "HCLTECH.NS", "SUNPHARMA.NS", "ASIANPAINT.NS", "TITAN.NS", "ULTRACEMCO.NS",
    "ADANIENT.NS", "BAJFINANCE.NS", "NTPC.NS", "ONGC.NS", "COALINDIA.NS",
    "POWERGRID.NS", "JSWSTEEL.NS", "HEROMOTOCO.NS", "NESTLEIND.NS", "HDFCLIFE.NS",
    "SBILIFE.NS", "GRASIM.NS", "INDUSINDBK.NS", "BAJAJFINSV.NS", "BPCL.NS",
    "CIPLA.NS", "DIVISLAB.NS", "EICHERMOT.NS", "M&M.NS", "APOLLOHOSP.NS"
]

def download_data(output_dir="data"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
        
    start_date = "1996-01-01"
    end_date = "2026-07-07"
    
    print(f"Downloading daily data for {len(TICKERS)} tickers from {start_date} to {end_date}...")
    
    success_count = 0
    for ticker in TICKERS:
        print(f"Fetching {ticker}...", end="", flush=True)
        try:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if data.empty:
                print(" FAILED (No data returned)")
                continue
                
            file_path = os.path.join(output_dir, f"{ticker}.csv")
            data.to_csv(file_path)
            print(f" SAVED ({len(data)} rows)")
            success_count += 1
        except Exception as e:
            print(f" ERROR: {str(e)}")
            
    print(f"\nDownload completed. Successfully downloaded {success_count}/{len(TICKERS)} tickers.")

if __name__ == "__main__":
    download_data()
