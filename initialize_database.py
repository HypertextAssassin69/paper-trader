import os
import json
import csv
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = os.path.join("data", "trading_journal.db")

def setup_schema(conn):
    """Creates the production tables for transactional state tracking."""
    cursor = conn.cursor()
    
    # 1. Table for tracking strategy states
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS portfolio_states (
        strategy_id TEXT PRIMARY KEY,
        cash REAL NOT NULL,
        holdings TEXT NOT NULL, -- JSON string
        start_date TEXT NOT NULL,
        start_capital REAL NOT NULL,
        last_run TEXT
    )
    """)
    
    # 2. Table for tracking virtual trades
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_id TEXT NOT NULL,
        date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        action TEXT NOT NULL,
        shares REAL NOT NULL,
        price REAL NOT NULL,
        value REAL NOT NULL,
        regime TEXT NOT NULL,
        reason TEXT NOT NULL
    )
    """)
    
    # 3. Table for tracking daily PnL records
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pnl_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_id TEXT NOT NULL,
        date TEXT NOT NULL,
        portfolio_value REAL NOT NULL,
        cash REAL NOT NULL
    )
    """)
    conn.commit()
    print("Database schema verified/created successfully.")

def migrate_existing_data(conn):
    """Imports all existing JSON and CSV records into the SQLite tables."""
    cursor = conn.cursor()
    
    # Register strategy IDs from compare_strats settings
    strategies = ["v1_a", "v1_b", "v1_c", "v2_a", "v2_b", "v2_c", "bulletproof", "nostops", "v3_ml", "v4_heuristic", "ensemble_70_30", "pairs", "v7_hybrid", "v7_large", "v7_mid"]
    
    # 1. Migrate JSON portfolio states
    for sid in strategies:
        json_path = os.path.join("states", f"portfolio_{sid}.json")
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                state = json.load(f)
            
            cursor.execute("""
            INSERT OR REPLACE INTO portfolio_states (strategy_id, cash, holdings, start_date, start_capital, last_run)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sid,
                state.get("cash", 100000.0),
                json.dumps(state.get("holdings", {})),
                state.get("start_date", str(datetime.now().date())),
                state.get("start_capital", 100000.0),
                state.get("last_run")
            ))
            print(f"Migrated state for strategy: {sid}")
            
    # 2. Migrate CSV PnL records
    for sid in strategies:
        pnl_csv = os.path.join("data", f"pnl_{sid}.csv")
        if os.path.exists(pnl_csv):
            # Check if database already has records to prevent duplicates
            cursor.execute("SELECT COUNT(*) FROM pnl_records WHERE strategy_id = ?", (sid,))
            if cursor.fetchone()[0] == 0:
                df = pd.read_csv(pnl_csv)
                for _, row in df.iterrows():
                    cursor.execute("""
                    INSERT INTO pnl_records (strategy_id, date, portfolio_value, cash)
                    VALUES (?, ?, ?, ?)
                    """, (sid, str(row['date']), float(row['portfolio_value']), float(row['cash'])))
                print(f"Migrated PnL history for strategy: {sid} ({len(df)} rows)")
                
    # 3. Migrate CSV Trades records
    for sid in strategies:
        trades_csv = os.path.join("data", f"trades_{sid}.csv")
        if os.path.exists(trades_csv):
            cursor.execute("SELECT COUNT(*) FROM trades WHERE strategy_id = ?", (sid,))
            if cursor.fetchone()[0] == 0:
                df = pd.read_csv(trades_csv)
                for _, row in df.iterrows():
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
                print(f"Migrated Trade history for strategy: {sid} ({len(df)} rows)")
                
    conn.commit()

def main():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        setup_schema(conn)
        migrate_existing_data(conn)
        print("All data migration completed successfully.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
