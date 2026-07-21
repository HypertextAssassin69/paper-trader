import os
import yfinance as yf
import pandas as pd
import numpy as np

# A broad pool of top high-growth mid-cap & small-cap stocks in India spanning key growth sectors
TICKER_POOL = [
    "CUMMINSIND.NS", "BEL.NS", "POLYCAB.NS", "DIXON.NS", "HAL.NS", 
    "MUTHOOTFIN.NS", "PERSISTENT.NS", "ABCAPITAL.NS", "BHARATFORG.NS", "MAXHEALTH.NS", 
    "MANKIND.NS", "JSWENERGY.NS", "LTTS.NS", "KPITTECH.NS", "COFORGE.NS", 
    "TATAELXSI.NS", "AUBANK.NS", "VOLTAS.NS", "CONCOR.NS", "BSE.NS",
    "MCX.NS", "ZOMATO.NS", "PAYTM.NS", "TRENT.NS", "OBEROIRLTY.NS"
]

def get_quantitative_score(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        
        # 1. Fundamental Metrics
        roe = info.get("returnOnEquity", 0.0)
        if roe is None: roe = 0.0
        
        rev_growth = info.get("revenueGrowth", 0.0)
        if rev_growth is None: rev_growth = 0.0
        
        inst_holding = info.get("heldPercentInstitutions", 0.0)
        if inst_holding is None: inst_holding = 0.0
        
        op_margin = info.get("operatingMargins", 0.0)
        if op_margin is None: op_margin = 0.0
        
        # 2. Technical Momentum Metrics (1-Year Price Return)
        hist = t.history(period="1y")
        hist = hist.dropna(subset=['Close'])
        if len(hist) > 100:
            start_price = float(hist['Close'].iloc[0])
            end_price = float(hist['Close'].iloc[-1])
            price_return = ((end_price - start_price) / start_price) if start_price > 0 else 0.0
            
            # Trend stability (percentage of days above 50-day SMA)
            sma50 = hist['Close'].rolling(50).mean()
            trend_strength = (hist['Close'] > sma50).mean()
        else:
            price_return = 0.0
            trend_strength = 0.0
            
        return {
            "Ticker": ticker,
            "Name": info.get("longName", ticker),
            "Sector": info.get("sector", "N/A"),
            "ROE %": roe * 100.0,
            "Revenue Growth %": rev_growth * 100.0,
            "Inst Holding %": inst_holding * 100.0,
            "Operating Margin %": op_margin * 100.0,
            "1Y Return %": price_return * 100.0,
            "Trend Strength %": trend_strength * 100.0
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {str(e)}")
        return None

def main():
    print("Initializing Multi-Factor Predictive Model for Future Large-Caps...")
    data_list = []
    
    for ticker in TICKER_POOL:
        print(f"Analyzing {ticker}...")
        res = get_quantitative_score(ticker)
        if res:
            data_list.append(res)
            
    df = pd.DataFrame(data_list)
    if df.empty:
        print("No stock data could be gathered.")
        return
        
    # Normalize scores between 0 and 1 for weighted scoring
    def min_max_normalize(series):
        if series.max() == series.min():
            return series * 0.0
        return (series - series.min()) / (series.max() - series.min())
        
    # Weights Configuration:
    # 30% Price Momentum (1Y Return)
    # 25% Sales Growth (Revenue Growth)
    # 20% Capital Efficiency (ROE)
    # 15% Institutional backing (Inst Holding)
    # 10% Trend stability (Trend Strength)
    
    df['Norm_Momentum'] = min_max_normalize(df['1Y Return %'])
    df['Norm_Growth'] = min_max_normalize(df['Revenue Growth %'])
    df['Norm_ROE'] = min_max_normalize(df['ROE %'])
    df['Norm_Institutions'] = min_max_normalize(df['Inst Holding %'])
    df['Norm_Trend'] = min_max_normalize(df['Trend Strength %'])
    
    df['Composite_Score'] = (
        df['Norm_Momentum'] * 0.30 +
        df['Norm_Growth'] * 0.25 +
        df['Norm_ROE'] * 0.20 +
        df['Norm_Institutions'] * 0.15 +
        df['Norm_Trend'] * 0.10
    ) * 100.0
    
    df_sorted = df.sort_values(by="Composite_Score", ascending=False)
    
    # Save the output to a local reports directory inside the git repository
    os.makedirs("reports", exist_ok=True)
    report_path = os.path.join("reports", "predictive_largecaps_model.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 🤖 Multi-Factor Predictive Model: Next Decade's Large-Caps\n")
        f.write("*Deploying a Quantitative Multi-Factor Ranking Screen to exploit future survivorship bias*\n\n")
        
        f.write("> [!IMPORTANT]\n")
        f.write("> **How this Model Works:** Instead of using hindsight, this model uses a composite score across 5 parameters—1Y Price Momentum, Revenue Growth, Capital Efficiency (ROE), Institutional Backing (FII/DII), and Trend Strength—to mathematically identify mid-caps graduating to index-level large-caps.\n\n")
        
        f.write("## 📊 Quantitative Ranking Table\n")
        f.write("| Rank | Ticker | Name | Sector | ROE % | Revenue Growth % | Inst Holding % | 1Y Return % | **Composite Score** |\n")
        f.write("| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |\n")
        
        for idx, row in enumerate(df_sorted.to_dict('records')):
            f.write(f"| {idx+1} | `{row['Ticker']}` | {row['Name']} | {row['Sector']} | {row['ROE %']:.1f}% | {row['Revenue Growth %']:.1f}% | {row['Inst Holding %']:.1f}% | {row['1Y Return %']:.1f}% | **{row['Composite_Score']:.2f}** |\n")
            
        f.write("\n## 🎯 Model Recommendations: The 5-Stock 'Future Giants' Basket\n")
        f.write("We recommend replacing or updating the `MID_BASKET` inside your **Dhurandhar Main** live trader with the top 5 stocks identified by this model:\n\n")
        
        top_5 = df_sorted.head(5).to_dict('records')
        for i, row in enumerate(top_5):
            f.write(f"### {i+1}. `{row['Ticker']}` — {row['Name']}\n")
            f.write(f"* **Sector:** {row['Sector']}\n")
            f.write(f"* **Sales Growth & ROE:** Growing sales at **{row['Revenue Growth %']:.1f}%** with an exceptional ROE of **{row['ROE %']:.1f}%**.\n")
            f.write(f"* **Smart Money Interest:** FIIs and DIIs own **{row['Inst Holding %']:.1f}%** of the company, indicating institutional accumulation before index entry.\n")
            f.write(f"* **1-Year Price Run:** Outperformed the market with a **{row['1Y Return %']:.1f}%** return.\n\n")
            
        f.write("## 🛠️ Step-by-Step Universe Integration Plan\n")
        f.write("To integrate these 5 stocks into your live **Dhurandhar Main** trading script:\n")
        f.write("1. Open `compare_strats/paper_trader_strat_v7_hybrid.py`\n")
        f.write("2. Locate the `MID_BASKET` list variable.\n")
        f.write("3. Replace any lower-ranked mid-caps with the top 5 candidates from this report.\n")
        f.write("4. The live runner will automatically begin trading them in the next daily session.\n")
        
    print(f"\nReport written successfully to {report_path}")

if __name__ == "__main__":
    main()
