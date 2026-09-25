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
                      (symbol TEXT, product TEXT, quantity INTEGER, avg_price REAL, sl_price REAL, tp_price REAL)''')
    
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

def place_order(symbol, txn_type, product, quantity, price, sl_price=0.0, tp_price=0.0):
    ist_offset = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now_ist = datetime.datetime.now(ist_offset)
    
    current_weekday = now_ist.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    current_time = now_ist.time()
    
    market_open = datetime.time(9, 15)
    market_close = datetime.time(15, 30)
    
    is_weekend = current_weekday >= 5
    is_within_time = market_open <= current_time <= market_close
    
    if is_weekend or not is_within_time:
        return False, f"Market is CLOSED! Trading hours are Mon–Fri, 9:15 AM to 3:30 PM IST. Current IST: {now_ist.strftime('%A %H:%M')}"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    account = get_account_summary()
    cash = account['cash_balance']
    
    if "Intraday" in product:
        margin_multiplier = 0.2
    else:
        margin_multiplier = 1.0
        
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
            cursor.execute("UPDATE positions SET quantity = ?, avg_price = ?, sl_price = ?, tp_price = ? WHERE symbol = ? AND product = ?", 
                           (new_qty, new_avg, sl_price, tp_price, symbol, product))
        else:
            new_qty = existing_qty - quantity
            if new_qty <= 0:
                cursor.execute("DELETE FROM positions WHERE symbol = ? AND product = ?", (symbol, product))
            else:
                cursor.execute("UPDATE positions SET quantity = ?, avg_price = ? WHERE symbol = ? AND product = ?", 
                               (new_qty, existing_avg, symbol, product))
    else:
        if txn_type == "BUY":
            cursor.execute("INSERT INTO positions VALUES (?, ?, ?, ?, ?, ?)", (symbol, product, quantity, price, sl_price, tp_price))
            
    conn.commit()
    conn.close()
    return True, f"Order {order_id} executed successfully at ₹{price:,.2f}!"

def update_sl_tp(symbol, product, new_sl, new_tp):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE positions SET sl_price = ?, tp_price = ? WHERE symbol = ? AND product = ?", (new_sl, new_tp, symbol, product))
    conn.commit()
    conn.close()
    return True, f"Successfully updated SL/TP for {symbol}!"

def square_off_position(symbol, product, current_price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT quantity, avg_price FROM positions WHERE symbol = ? AND product = ?", (symbol, product))
    pos = cursor.fetchone()
    if not pos:
        conn.close()
        return False, "Position not found."
    
    qty, avg_price = pos
    
    margin_multiplier = 0.2 if "Intraday" in product else 1.0
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

def check_auto_exits(get_live_price_func, stock_mapping):
    positions = get_positions()
    if positions.empty:
        return []
    
    triggered_messages = []
    for idx, row in positions.iterrows():
        symbol = row['symbol']
        product = row['product']
        sl = row['sl_price']
        tp = row['tp_price']
        
        sym_code = stock_mapping.get(symbol, "RELIANCE.NS")
        current_ltp = get_live_price_func(sym_code)
        if current_ltp == 0.0:
            continue
            
        hit_exit = False
        reason = ""
        if sl > 0 and current_ltp <= sl:
            hit_exit = True
            reason = f"Stop Loss hit at ₹{current_ltp:,.2f}"
        elif tp > 0 and current_ltp >= tp:
            hit_exit = True
            reason = f"Take Profit hit at ₹{current_ltp:,.2f}"
            
        if hit_exit:
            success, msg = square_off_position(symbol, product, current_ltp)
            if success:
                triggered_messages.append(f"⚡ AUTO EXIT ({symbol}): {reason}. {msg}")
                
    return triggered_messages

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
