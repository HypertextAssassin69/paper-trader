import numpy as np
import pandas as pd

class OrderFlowAnalyzer:
    """
    Analyzes real-time Order Book Imbalance (OBI) and footprints trade streams
    to track Cumulative Delta and identify institutional Iceberg absorption (Delta Divergence).
    """
    def __init__(self, window_size=20):
        self.window_size = window_size
        self.cum_delta = 0.0
        self.history = [] # list of dicts: {'price', 'cum_delta', 'obi'}
        
    def calculate_obi(self, book_snapshot, depth=5):
        """
        Calculates Order Book Imbalance (OBI) for a Level 3 book snapshot.
        """
        bids = book_snapshot.get('bids', [])[:depth]
        asks = book_snapshot.get('asks', [])[:depth]
        
        bid_vol = sum(level['size'] for level in bids)
        ask_vol = sum(level['size'] for level in asks)
        
        total_vol = bid_vol + ask_vol
        if total_vol == 0:
            return 0.0
            
        return (bid_vol - ask_vol) / total_vol
        
    def update_delta(self, trades):
        """
        Updates Cumulative Delta from trade records.
        """
        delta = 0.0
        for trade in trades:
            size = trade['size']
            side = trade['side']
            if side == 'buy':
                delta += size
            elif side == 'sell':
                delta -= size
                
        self.cum_delta += delta
        return self.cum_delta
        
    def process_tick(self, price, book_snapshot, trades):
        """
        Processes a single tick data and returns flow signals.
        """
        obi = self.calculate_obi(book_snapshot)
        cum_delta = self.update_delta(trades)
        
        self.history.append({
            'price': price,
            'cum_delta': cum_delta,
            'obi': obi
        })
        
        # Maintain rolling window
        if len(self.history) > self.window_size:
            self.history.pop(0)
            
        signals = {
            'obi': obi,
            'cum_delta': cum_delta,
            'delta_divergence': 'none'
        }
        
        # Check for Delta Divergence if window is full
        if len(self.history) >= self.window_size:
            prices = [h['price'] for h in self.history]
            deltas = [h['cum_delta'] for h in self.history]
            
            # Find local extrema in the window
            min_price_idx = np.argmin(prices)
            max_price_idx = np.argmax(prices)
            
            # Case 1: Price makes a new low at the end of the window (index -1)
            # but Cumulative Delta is NOT at its lowest, indicating absorption.
            if min_price_idx == len(prices) - 1:
                # Find the minimum delta in the window
                min_delta_idx = np.argmin(deltas)
                if min_delta_idx != len(deltas) - 1:
                    # Delta did not make a new low while price did -> Bullish Delta Divergence
                    signals['delta_divergence'] = 'bullish'
                    
            # Case 2: Price makes a new high at the end of the window (index -1)
            # but Cumulative Delta is NOT at its highest, indicating absorption.
            elif max_price_idx == len(prices) - 1:
                max_delta_idx = np.argmax(deltas)
                if max_delta_idx != len(deltas) - 1:
                    # Delta did not make a new high while price did -> Bearish Delta Divergence
                    signals['delta_divergence'] = 'bearish'
                    
        return signals
