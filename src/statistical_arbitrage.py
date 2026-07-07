import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint

class StatisticalArbitrageEngine:
    """
    Handles cointegration scanning, rolling OLS hedge ratio calculations,
    and rolling spread Z-Score calculations for pairs trading.
    """
    def __init__(self, rolling_window=50):
        self.rolling_window = rolling_window
        self.history_a = []
        self.history_b = []
        
    def find_cointegrated_pairs(self, stock_dfs, tickers, start_date, end_date):
        """
        Scans all combinations of tickers to locate cointegrated pairs.
        """
        print(f"Scanning for cointegrated pairs from {start_date.date()} to {end_date.date()}...")
        # Align closing prices
        data_dict = {}
        for ticker in tickers:
            if ticker in stock_dfs:
                df = stock_dfs[ticker]
                sub = df.loc[start_date:end_date]
                if not sub.empty:
                    data_dict[ticker] = sub['Close']
                    
        aligned_df = pd.DataFrame(data_dict).dropna()
        n = len(aligned_df.columns)
        col_names = aligned_df.columns
        pairs = []
        
        for i in range(n):
            for j in range(i + 1, n):
                t1 = col_names[i]
                t2 = col_names[j]
                
                s1 = aligned_df[t1]
                s2 = aligned_df[t2]
                
                score, pvalue, _ = coint(s1, s2)
                if pvalue < 0.05:
                    # Regress A on B to get hedge ratio (beta)
                    X = sm.add_constant(s2)
                    model = sm.OLS(s1, X).fit()
                    beta = model.params.iloc[1]
                    alpha = model.params.iloc[0]
                    
                    pairs.append({
                        'pair': (t1, t2),
                        'p_value': pvalue,
                        'beta': beta,
                        'alpha': alpha
                    })
                    
        return sorted(pairs, key=lambda x: x['p_value'])

    def update_and_calculate_zscore(self, price_a, price_b):
        """
        Appends prices, updates rolling OLS parameters, and returns Z-Score and beta.
        Uses rolling window to avoid look-ahead bias.
        """
        self.history_a.append(price_a)
        self.history_b.append(price_b)
        
        # Limit history to window size
        if len(self.history_a) > self.rolling_window:
            self.history_a.pop(0)
            self.history_b.pop(0)
            
        if len(self.history_a) < self.rolling_window:
            # Not enough data for Z-score calculation yet
            return 0.0, 1.0
            
        # OLS on rolling history
        y = np.array(self.history_a)
        x = np.array(self.history_b)
        
        X = sm.add_constant(x)
        model = sm.OLS(y, X).fit()
        beta = model.params[1]
        alpha = model.params[0]
        
        # Calculate historical rolling spread series
        spreads = y - beta * x - alpha
        mean_spread = np.mean(spreads)
        std_spread = np.std(spreads)
        
        # Current spread
        current_spread = price_a - beta * price_b - alpha
        z_score = (current_spread - mean_spread) / std_spread if std_spread > 0 else 0.0
        
        return z_score, beta
