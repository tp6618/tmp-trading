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
                      (id INTEGER PRIMARY KEY, cash_balance REAL, utilized_margin REAL, total_charges_paid REAL)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders 
                      (order_id TEXT, timestamp TEXT, symbol TEXT, txn_type TEXT, 
                       product TEXT, quantity INTEGER, price REAL, charges REAL, status TEXT)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS positions 
                      (symbol TEXT, product TEXT, quantity INTEGER, avg_price REAL, sl_price REAL, tp_price REAL)''')
    
    cursor.execute("SELECT COUNT(*) FROM account")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO account (cash_balance, utilized_margin, total_charges_paid) VALUES (?, ?, ?)", (1000000.0, 0.0, 0.0))
    else:
        # Check if total_charges_paid column exists for older DB versions
        cursor.execute("PRAGMA table_info(account)")
        columns = [col[1] for col in cursor.fetchall()]
        if "total_charges_paid" not in columns:
            cursor.execute("ALTER TABLE account ADD COLUMN total_charges_paid REAL DEFAULT 0.0")
    
    conn.commit()
    conn.close()

init_db()

def get_account_summary():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT cash_balance, utilized_margin, total_charges_paid FROM account WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"cash_balance": row[0], "utilized_margin": row[1], "total_charges_paid": row[2] if len(row) > 2 else 0.0}
    return {"cash_balance": 1000000.0, "utilized_margin": 0.0, "total_charges_paid": 0.0}

def calculate_standard_charges(turnover, txn_type, product):
    """Calculates standard Indian stock market charges (Brokerage, STT, Exchange, GST, SEBI, Stamp Duty)."""
    is_delivery = "Delivery" in product
    
    # 1. Brokerage: Flat ₹20 or flat percentage
    brokerage = min(20.0, turnover * 0.0003)
    
    # 2. STT / CTT
    if is_delivery:
        stt = turnover * 0.001  # 0.1% on buy & sell for delivery
    else:
        stt = turnover * 0.00025 if txn_type == "SELL" else 0.0 # 0.025% on sell side for intraday
        
    # 3. Exchange Transaction Charges (~0.00325%)
    exchange_txn = turnover * 0.0000325
    
    # 4. GST (18% on brokerage + exchange charges)
    gst = (brokerage + exchange_txn) * 0.18
    
    # 5. SEBI Turnover Charges (₹10 per Crore -> 0.0001%)
    sebi_charges = turnover * 0.000001
    
    # 6. Stamp Duty (0.015% for delivery buy, 0.003% for intraday buy)
    stamp_duty = turnover * 0.00015 if (is_delivery and txn_type == "BUY") else (turnover * 0.00003 if txn_type == "BUY" else 0.0)
    
    total_charges = brokerage + stt + exchange_txn + gst + sebi_charges + stamp_duty
    return round(total_charges, 2)

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
    
    margin_multiplier = 0.2 if "Intraday" in product else 1.0
    turnover = price * quantity
    charges = calculate_standard_charges(turnover, txn_type, product)
    
    required_margin = (turnover * margin_multiplier) + (charges if txn_type == "BUY" else 0.0)
    
    if txn_type == "BUY" and cash < required_margin:
        conn.close()
        return False, f"Insufficient funds! Required margin + charges: ₹{required_margin:,.2f}"
    
    new_cash = cash - required_margin if txn_type == "BUY" else cash - charges
    new_utilized = account['utilized_margin'] + (turnover * margin_multiplier) if txn_type == "BUY" else account['utilized_margin']
    new_charges_total = account['total_charges_paid'] + charges
    
    cursor.execute("UPDATE account SET cash_balance = ?, utilized_margin = ?, total_charges_paid = ? WHERE id = 1", 
                   (new_cash, new_utilized, new_charges_total))
    
    order_id = "TMP" + str(datetime.datetime.now().strftime("%H%M%S%f"))[:10]
    timestamp = now_ist.strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (order_id, timestamp, symbol, txn_type, product, quantity, price, charges, "COMPLETE"))
    
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
    return True, f"Order {order_id} executed successfully! Charges applied: ₹{charges:,.2f}"

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
    
    exit_turnover = current_price * qty
    exit_charges = calculate_standard_charges(exit_turnover, "SELL", product)
    
    realized_pnl = (current_price - avg_price) * qty
    
    account = get_account_summary()
    new_cash = account['cash_balance'] + released_margin + realized_pnl - exit_charges
    new_utilized = max(0.0, account['utilized_margin'] - released_margin)
    new_charges_total = account['total_charges_paid'] + exit_charges
    
    cursor.execute("UPDATE account SET cash_balance = ?, utilized_margin = ?, total_charges_paid = ? WHERE id = 1", 
                   (new_cash, new_utilized, new_charges_total))
    cursor.execute("DELETE FROM positions WHERE symbol = ? AND product = ?", (symbol, product))
    
    conn.commit()
    conn.close()
    return True, f"Squared off {symbol}. Realized P&L: ₹{realized_pnl:,.2f} (Exit Charges: ₹{exit_charges:,.2f})"

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
