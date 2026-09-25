import streamlit as st
import pandas as pd
import time
import yfinance as yf
from modules.broker_engine import get_account_summary, place_order, get_orders, get_positions

# Page Configuration
st.set_page_config(
    page_title="TMP TRADING | Live Multi-Segment Terminal",
    page_icon="⚡",
    layout="wide"
)

# Professional Dark Theme & Centered UI Styling
st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    .stMetric {
        background-color: #1e222d; 
        padding: 12px; 
        border-radius: 6px; 
        border: 1px solid #2d3748;
        text-align: center;
    }
    h1, h2, h3 {
        text-align: center;
        color: #f0f2f6;
    }
    p, .stMarkdown {
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# Helper function to fetch real-time LTP from NSE feeds with caching
@st.cache_data(ttl=5)
def fetch_live_price(ticker_symbol):
    try:
        data = yf.Ticker(ticker_symbol)
        todays_data = data.history(period='1d')
        if not todays_data.empty:
            return float(todays_data['Close'].iloc[-1])
    except Exception:
        pass
    return 0.00

# Sidebar Order Ticket Panel
st.sidebar.title("⚡ TMP TRADING")
st.sidebar.caption("Institutional Paper Terminal")
st.sidebar.markdown("---")

# Segment selection category
market_segment = st.sidebar.selectbox("Market Segment", ["Equity Cash", "Futures & Options (F&O)"])

if market_segment == "Equity Cash":
    stock_mapping = {
        "RELIANCE": "RELIANCE.NS",
        "TCS": "TCS.NS",
        "HDFCBANK": "HDFCBANK.NS",
        "ICICIBANK": "ICICIBANK.NS",
        "INFY": "INFY.NS",
        "ITC": "ITC.NS",
        "SBIN": "SBIN.NS",
        "LTIM": "LTIM.NS",
        "BHARTIARTL": "BHARTIARTL.NS",
        "KOTAKBANK": "KOTAKBANK.NS",
        "LT": "LT.NS",
        "AXISBANK": "AXISBANK.NS",
        "HINDUNILVR": "HINDUNILVR.NS",
        "BAJFINANCE": "BAJFINANCE.NS",
        "ASIANPAINT": "ASIANPAINT.NS",
        "MARUTI": "MARUTI.NS",
        "SUNPHARMA": "SUNPHARMA.NS",
        "TITAN": "TITAN.NS",
        "WIPRO": "WIPRO.NS",
        "ULTRACEMCO": "ULTRACEMCO.NS",
        "TATAMOTORS": "TATAMOTORS.NS",
        "TATASTEEL": "TATASTEEL.NS",
        "POWERGRID": "POWERGRID.NS",
        "NTPC": "NTPC.NS",
        "ONGC": "ONGC.NS"
    }
    available_products = ["Equity Delivery (CNC) - 1x", "Equity Intraday (MIS) - 5x"]
else:
    stock_mapping = {
        "NIFTY 50 Index": "^NSEI",
        "BANK NIFTY Index": "^NSEBANK",
        "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
        "NIFTY MIDCAP 50": "^NSEMDCP50",
        "RELIANCE FNO": "RELIANCE.NS",
        "TCS FNO": "TCS.NS",
        "HDFCBANK FNO": "HDFCBANK.NS",
        "SBIN FNO": "SBIN.NS"
    }
    available_products = ["F&O Intraday (MIS)", "F&O Carry Forward (NRML)"]

selected_option = st.sidebar.selectbox("Trading Symbol", list(stock_mapping.keys()))
ticker_code = stock_mapping[selected_option]

# Fetch Real-Time LTP
with st.spinner("Fetching live tick..."):
    ltp = fetch_live_price(ticker_code)

if ltp == 0.00:
    ltp = 2500.00  # Fallback default safety price

st.sidebar.markdown(f"### Live LTP: `₹{ltp:,.2f}`")

txn_type = st.sidebar.radio("Action Type", ["BUY", "SELL"], horizontal=True)
product = st.sidebar.selectbox("Product Type", available_products)
qty = st.sidebar.number_input("Quantity / Lot Size", min_value=1, value=15)

# Dynamic Margin Calculation Preview
if "Intraday" in product:
    margin_mult = 0.2
elif "Delivery" in product:
    margin_mult = 1.0
else:
    margin_mult = 0.25

est_required = (ltp * qty) * margin_mult
st.sidebar.caption(f"Estimated Margin Needed: **₹{est_required:,.2f}**")

if st.sidebar.button("🚀 Execute Order", type="primary", use_container_width=True):
    success, msg = place_order(selected_option, txn_type, product, qty, ltp)
    if success:
        st.sidebar.success(msg)
        time.sleep(0.5)
        st.rerun()
    else:
        st.sidebar.error(msg)

# Main Dashboard Centered Header
st.title("⚡ TMP TRADING Terminal")
st.markdown("Live multi-segment simulated environment supporting Equity Delivery, Intraday, and F&O.")

# Fetch Account Balances
account = get_account_summary()
free_cash = account['cash_balance']
utilized = account['utilized_margin']

# Compute Live Unrealized P&L from Active Positions
positions_df = get_positions()
total_unrealized_pnl = 0.0

if not positions_df.empty:
    live_ltps = []
    pnl_list = []
    pnl_pct_list = []
    
    for idx, row in positions_df.iterrows():
        sym_name = row['symbol']
        sym_code = "RELIANCE.NS"
        for k, v in stock_mapping.items():
            if k == sym_name:
                sym_code = v
                break
                
        current_ltp = fetch_live_price(sym_code)
        if current_ltp == 0.0:
            current_ltp = row['avg_price']
            
        live_ltps.append(current_ltp)
        
        pnl = (current_ltp - row['avg_price']) * row['quantity']
        pnl_pct = ((current_ltp - row['avg_price']) / row['avg_price']) * 100 if row['avg_price'] > 0 else 0.0
        
        pnl_list.append(round(pnl, 2))
        pnl_pct_list.append(f"{pnl_pct:.2f}%")
        total_unrealized_pnl += pnl

    positions_df['LTP'] = live_ltps
    positions_df['Unrealized P&L'] = pnl_list
    positions_df['P&L (%)'] = pnl_pct_list

total_portfolio_value = free_cash + utilized + total_unrealized_pnl

# Top Financial Metrics Bar (Centered layout)
st.markdown("### 📊 Account Performance Metrics")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Available Cash", f"₹{free_cash:,.2f}")
col2.metric("Utilized Margin", f"₹{utilized:,.2f}")
col3.metric("Total Net Worth", f"₹{total_portfolio_value:,.2f}")
col4.metric("Unrealized P&L", f"₹{total_unrealized_pnl:,.2f}", delta=f"₹{total_unrealized_pnl:,.2f}")

st.markdown("---")

# Portfolio Management Centered Tabs
tab1, tab2, tab3 = st.tabs(["📊 Active Positions", "📑 Order Book", "💰 Ledger Summary"])

with tab1:
    st.subheader("Open Positions (Equity & F&O)")
    if not positions_df.empty:
        st.dataframe(positions_df, use_container_width=True)
    else:
        st.info("No open positions currently active. Use the sidebar ticket to place a trade.")

with tab2:
    st.subheader("Complete Order Book History")
    orders_df = get_orders()
    if not orders_df.empty:
        st.dataframe(orders_df, use_container_width=True)
    else:
        st.info("No orders placed yet.")

with tab3:
    st.subheader("Ledger Details")
    st.json({
        "Broker Name": "TMP TRADING",
        "Supported Segments": ["Equity Delivery (CNC)", "Equity Intraday (MIS)", "F&O (NRML/MIS)"],
        "Available Cash Balance": f"₹{free_cash:,.2f}",
        "Blocked Exposure Margin": f"₹{utilized:,.2f}"
    })

# Real-Time Ticker Refresh Feed Toggles
if st.sidebar.checkbox("Enable Live Ticker Refresh (5s)", value=True):
    time.sleep(5)
    st.rerun()
