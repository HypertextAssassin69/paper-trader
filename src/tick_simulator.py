import numpy as np
import pandas as pd
from datetime import datetime, timedelta

class TickSimulator:
    """
    Generates high-fidelity simulated Level 3 Order Book and Tick Flow data 
    for two cointegrated assets, embedding Order Book Imbalance (OBI) and 
    Cumulative Delta Footprint Divergences.
    """
    def __init__(self, num_ticks=1000, seed=42):
        np.random.seed(seed)
        self.num_ticks = num_ticks
        self.current_tick = 0
        
        # Cointegration parameters
        self.beta = 1.5
        self.alpha = 10.0
        
        # Generate underlying random walk for Asset B
        self.price_b = np.zeros(num_ticks)
        self.price_b[0] = 100.0
        for i in range(1, num_ticks):
            self.price_b[i] = self.price_b[i-1] + np.random.normal(0.0, 0.2)
            
        # Generate mean-reverting spread (Ornstein-Uhlenbeck process)
        spread = np.zeros(num_ticks)
        spread[0] = 0.0
        theta = 0.1  # Speed of mean reversion
        for i in range(1, num_ticks):
            spread[i] = spread[i-1] + theta * (0.0 - spread[i-1]) + np.random.normal(0.0, 0.15)
            # Inject extreme spread moves that align with our signals
            if 200 <= i <= 250:
                spread[i] -= 1.8 # Force negative spread drift (underpriced)
            elif 400 <= i <= 450:
                spread[i] += 1.8 # Force positive spread drift (overpriced)
            elif 600 <= i <= 650:
                spread[i] -= 1.8
            elif 800 <= i <= 850:
                spread[i] += 1.8
            
        # Asset A is cointegrated with B
        self.price_a = self.beta * self.price_b + self.alpha + spread
        
        # Generate timestamps
        start_time = datetime.now()
        self.timestamps = [start_time + timedelta(seconds=i*5) for i in range(num_ticks)]
        
    def get_tick(self):
        """
        Returns the microsecond-level order book and trades snapshot at the current tick.
        """
        if self.current_tick >= self.num_ticks:
            return None
            
        t = self.current_tick
        p_a = self.price_a[t]
        p_b = self.price_b[t]
        timestamp = self.timestamps[t]
        
        # 1. Simulate Level 3 Order Book for Asset A (Spread Asset)
        bid_multiplier = 1.0
        ask_multiplier = 1.0
        delta_bias = 0.0
        
        # Inject OBI buy wall and delta bias at certain ticks
        if (200 <= t <= 250) or (600 <= t <= 650):
            bid_multiplier = 8.0 # Stacking massive buy orders
            delta_bias = 0.45    # Footprint Cumulative Delta goes up (bullish divergence)
        # Inject OBI sell wall and delta bias at other ticks
        elif (400 <= t <= 450) or (800 <= t <= 850):
            ask_multiplier = 8.0
            delta_bias = -0.45   # Footprint Cumulative Delta goes down (bearish divergence)
            
        bids_a = []
        asks_a = []
        for i in range(5):
            bids_a.append({
                'price': round(p_a - (i * 0.05 + 0.05), 2),
                'size': int(np.random.randint(100, 500) * bid_multiplier)
            })
            asks_a.append({
                'price': round(p_a + (i * 0.05 + 0.05), 2),
                'size': int(np.random.randint(100, 500) * ask_multiplier)
            })
            
        # 2. Simulate Trades (to calculate footprint Cumulative Delta)
        trades_a = []
        num_trades = np.random.randint(5, 15)
        
        for _ in range(num_trades):
            side = 'buy' if (np.random.rand() + delta_bias) > 0.5 else 'sell'
            trades_a.append({
                'price': round(p_a + np.random.normal(0, 0.02), 2),
                'size': int(np.random.choice([10, 50, 100, 200])),
                'side': side
            })
            
        tick_data = {
            'tick_idx': t,
            'timestamp': timestamp,
            'asset_a_price': p_a,
            'asset_b_price': p_b,
            'book_a': {'bids': bids_a, 'asks': asks_a},
            'trades_a': trades_a
        }
        
        self.current_tick += 1
        return tick_data
