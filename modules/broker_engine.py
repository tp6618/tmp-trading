import sqlite3
import pandas as pd
import os
import datetime

os.makedirs("data", exist_ok=True)
DB_PATH = "data/tmp_trading.sqlite"

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS account 
                      (id INTEGER PRIMARY KEY, cash_balance REAL, utilized_margin REAL)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (order_id TEXT, timestamp TEXT, symbol TEXT, txn_type TEXT, 
                       product TEXT, quantity INTEGER, price REAL, status TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS positions 
                      (symbol TEXT, product TEXT, quantity INTEGER, avg_price REAL)''')
    
    cursor.execute("SELECT COUNT(*) FROM account")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO account (cash_balance, utilized_margin) VALUES (?, ?)", (1000000.0, 0.0))
    
    conn.commit()
    conn.close()

init_db()

def get_account_summary():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT cash_balance, utilized_margin FROM account WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"cash_balance": row[0], "utilized_margin": row[1]}
    return {"cash_balance": 1000000.0, "utilized_margin": 0.0}

def place_order(symbol, txn_type, product, quantity, price):
    ist_offset = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = datetime.datetime.now(ist_offset)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    account = get_account_summary()
    cash = account['cash_balance']
    
    if "Intraday" in product:
        margin_multiplier = 0.2
    elif "Delivery" in product:
        margin_multiplier = 1.0
    else:
        margin_multiplier = 0.25
        
    required_margin = (price * quantity) * margin_multiplier
    
    if txn_type == "BUY" and cash < required_margin:
        conn.close()
        return False, f"Insufficient funds! Required margin: ₹{required_margin:,.2f}"
    
    new_cash = cash - required_margin if txn_type == "BUY" else cash
    new_utilized = account['utilized_margin'] + required_margin
    
    cursor.execute("UPDATE account SET cash_balance = ?, utilized_margin = ? WHERE id = 1", (new_cash, new_utilized))
    
    order_id = "TMP" + str(datetime.datetime.now().strftime("%H%M%S%f"))[:10]
    timestamp = now_ist.strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (order_id, timestamp, symbol, txn_type, product, quantity, price, "COMPLETE"))
    
    cursor.execute("SELECT quantity, avg_price FROM positions WHERE symbol = ? AND product = ?", (symbol, product))
    pos = cursor.fetchone()
    
    if pos:
        existing_qty, existing_avg = pos
        if txn_type == "BUY":
            new_qty = existing_qty + quantity
            new_avg = ((existing_qty * existing_avg) + (quantity * price)) / new_qty
            cursor.execute("UPDATE positions SET quantity = ?, avg_price = ? WHERE symbol = ? AND product = ?", 
                           (new_qty, new_avg, symbol, product))
        else:
            new_qty = existing_qty - quantity
            if new_qty <= 0:
                cursor.execute("DELETE FROM positions WHERE symbol = ? AND product = ?", (symbol, product))
            else:
                cursor.execute("UPDATE positions SET quantity = ?, avg_price = ? WHERE symbol = ? AND product = ?", 
                               (new_qty, existing_avg, symbol, product))
    else:
        if txn_type == "BUY":
            cursor.execute("INSERT INTO positions VALUES (?, ?, ?, ?)", (symbol, product, quantity, price))
            
    conn.commit()
    conn.close()
    return True, f"Order {order_id} executed successfully!"

def square_off_position(symbol, product, current_price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT quantity, avg_price FROM positions WHERE symbol = ? AND product = ?", (symbol, product))
    pos = cursor.fetchone()
    if not pos:
        conn.close()
        return False, "Position not found."
    
    qty, avg_price = pos
    
    if "Intraday" in product:
        margin_multiplier = 0.2
    elif "Delivery" in product:
        margin_multiplier = 1.0
    else:
        margin_multiplier = 0.25
        
    released_margin = (avg_price * qty) * margin_multiplier
    realized_pnl = (current_price - avg_price) * qty
    
    account = get_account_summary()
    new_cash = account['cash_balance'] + released_margin + realized_pnl
    new_utilized = max(0.0, account['utilized_margin'] - released_margin)
    
    cursor.execute("UPDATE account SET cash_balance = ?, utilized_margin = ? WHERE id = 1", (new_cash, new_utilized))
    cursor.execute("DELETE FROM positions WHERE symbol = ? AND product = ?", (symbol, product))
    
    conn.commit()
    conn.close()
    return True, f"Successfully squared off {symbol}. Realized P&L: ₹{realized_pnl:,.2f}"

def reset_account():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    return True

def get_orders():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM orders ORDER BY timestamp DESC", conn)
    conn.close()
    return df

def get_positions():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM positions", conn)
    conn.close()
    return df
