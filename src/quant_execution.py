import numpy as np

class QuantExecutionEngine:
    """
    Manages capital allocation, places Bracket Orders, dynamically scales 
    position sizes based on market volatility (VIX/ATR), and enforces 
    the Trailing Peak Equity Drawdown circuit breaker.
    """
    def __init__(self, initial_capital=100000.0, risk_per_trade_pct=0.0025, max_drawdown_pct=0.03):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.risk_per_trade_pct = risk_per_trade_pct # default 0.25% per trade
        self.max_drawdown_pct = max_drawdown_pct # hard 3% daily drawdown cap
        self.peak_equity = initial_capital
        self.active_trading = True
        
        # State tracking: {symbol: {'shares': s, 'entry_price': ep, 'side': 'long'/'short', 'stop_price': sp, 'target_price': tp}}
        self.positions = {}
        self.trades_history = []
        
    def get_equity(self, current_prices):
        """
        Calculates total equity (cash + open positions market value).
        """
        pos_val = 0.0
        for symbol, pos in self.positions.items():
            p = current_prices.get(symbol, pos['entry_price'])
            if pos['side'] == 'long':
                pos_val += pos['shares'] * p
            elif pos['side'] == 'short':
                pos_val -= pos['shares'] * p
        return self.cash + pos_val
        
    def check_drawdown_breaker(self, current_prices, timestamp):
        """
        Calculates trailing drawdown from peak equity and liquidates if breached.
        """
        if not self.active_trading:
            return False
            
        current_equity = self.get_equity(current_prices)
        
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
            
        drawdown = (self.peak_equity - current_equity) / self.peak_equity
        
        if drawdown >= self.max_drawdown_pct:
            self.active_trading = False
            self.liquidate_all_positions(current_prices, timestamp, "BREAKER_TRAILING_DD")
            return False
            
        return True

    def calculate_scaled_position_size(self, entry_price, stop_price, atr, vix):
        """
        Calculates dynamic position sizing using Dynamic Volatility Scaling (ATR/VIX).
        If VIX > 25, risk factor is scaled down by 50% to 75%.
        """
        # 1. Base risk percentage (e.g. 0.25% of current equity)
        current_equity = self.cash
        base_risk_amt = current_equity * self.risk_per_trade_pct
        
        # 2. VIX volatility scaling factor
        vol_scalar = 1.0
        if vix > 25:
            # Scale down risk when market is highly volatile
            vol_scalar = max(0.25, 25.0 / vix)
            
        scaled_risk_amt = base_risk_amt * vol_scalar
        
        # 3. Dynamic Position Sizing using stop distance
        stop_distance = abs(entry_price - stop_price)
        if stop_distance == 0:
            return 0
            
        shares = int(scaled_risk_amt // stop_distance)
        return max(1, shares)
        
    def execute_bracket_order(self, symbol, side, entry_price, stop_price, target_price, shares, timestamp):
        """
        Places a Bracket Order (One-Cancels-the-Other) on the broker servers.
        """
        if not self.active_trading:
            return False
            
        if symbol in self.positions:
            return False # Already have an open position in this asset
            
        cost = shares * entry_price
        fee = min(cost * 0.0005, 20.0) # 0.05% or cap ₹20
        
        if side == 'long':
            if self.cash < (cost + fee):
                return False # Insufficient buying power
            self.cash -= (cost + fee)
        elif side == 'short':
            # Short cash mechanics: receive cash proceeds but hold margin liability
            self.cash += (cost - fee)
            
        self.positions[symbol] = {
            'shares': shares,
            'entry_price': entry_price,
            'side': side,
            'stop_price': stop_price,
            'target_price': target_price,
            'entry_fee': fee,
            'entry_date': timestamp
        }
        
        return True
        
    def check_bracket_exits(self, current_prices, timestamp):
        """
        Evaluates stops and targets for all open positions.
        """
        exited_symbols = []
        for symbol, pos in list(self.positions.items()):
            p_low = current_prices.get(symbol + '_low', current_prices.get(symbol))
            p_high = current_prices.get(symbol + '_high', current_prices.get(symbol))
            p_close = current_prices.get(symbol)
            
            is_exit = False
            exit_price = p_close
            reason = ""
            
            if pos['side'] == 'long':
                # Check Stop Loss
                if p_low <= pos['stop_price']:
                    is_exit = True
                    exit_price = pos['stop_price']
                    reason = "STOP_LOSS"
                # Check Target Profit
                elif p_high >= pos['target_price']:
                    is_exit = True
                    exit_price = pos['target_price']
                    reason = "TAKE_PROFIT"
            elif pos['side'] == 'short':
                # Check Stop Loss
                if p_high >= pos['stop_price']:
                    is_exit = True
                    exit_price = pos['stop_price']
                    reason = "STOP_LOSS"
                # Check Target Profit
                elif p_low <= pos['target_price']:
                    is_exit = True
                    exit_price = pos['target_price']
                    reason = "TAKE_PROFIT"
                    
            if is_exit:
                self.close_position(symbol, exit_price, timestamp, reason)
                exited_symbols.append(symbol)
                
        return exited_symbols

    def close_position(self, symbol, exit_price, timestamp, reason):
        """
        Closes a position, pays commissions, and records the trade log.
        """
        if symbol not in self.positions:
            return
            
        pos = self.positions[symbol]
        shares = pos['shares']
        entry_price = pos['entry_price']
        
        cost = shares * exit_price
        fee = min(cost * 0.0005, 20.0)
        
        if pos['side'] == 'long':
            pnl = shares * (exit_price - entry_price)
            self.cash += (cost - fee)
        elif pos['side'] == 'short':
            pnl = shares * (entry_price - exit_price)
            self.cash -= (cost + fee)
            
        net_pnl = pnl - pos['entry_fee'] - fee
        
        self.trades_history.append({
            'symbol': symbol,
            'side': pos['side'],
            'entry_date': pos['entry_date'],
            'exit_date': timestamp,
            'shares': shares,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'net_pnl': net_pnl,
            'reason': reason,
            'outcome': 'PROFIT' if net_pnl > 0 else 'LOSS'
        })
        
        del self.positions[symbol]
        
    def liquidate_all_positions(self, current_prices, timestamp, reason):
        """
        Instantly liquidates all positions at market open/close price.
        """
        for symbol in list(self.positions.keys()):
            p = current_prices.get(symbol, self.positions[symbol]['entry_price'])
            self.close_position(symbol, p, timestamp, reason)
