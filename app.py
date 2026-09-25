import streamlit as st
import pandas as pd
import yfinance as yf
from modules.broker_engine import get_account_summary, place_order, get_orders, get_positions, square_off_position, reset_account, check_auto_exits, update_sl_tp

# Page Configuration
st.set_page_config(
    page_title="TMP TRADING | Equity Terminal",
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

@st.cache_data(ttl=86400)
def get_exchange_stocks():
    stocks = {}
    try:
        url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        df = pd.read_csv(url, storage_options=headers)
        for _, row in df.iterrows():
            sym = str(row['SYMBOL']).strip()
            name = str(row['NAME OF COMPANY']).strip()
            stocks[f"{sym} - {name}"] = f"{sym}.NS"
    except Exception:
        pass
    
    fallback_stocks = {
        "RELIANCE - Reliance Industries Ltd": "RELIANCE.NS",
        "TCS - Tata Consultancy Services Ltd": "TCS.NS",
        "HDFCBANK - HDFC Bank Ltd": "HDFCBANK.NS",
        "ICICIBANK - ICICI Bank Ltd": "ICICIBANK.NS",
        "INFY - Infosys Ltd": "INFY.NS",
        "ITC - ITC Ltd": "ITC.NS",
        "SBIN - State Bank of India": "SBIN.NS",
        "BHARTIARTL - Bharti Airtel Ltd": "BHARTIARTL.NS",
        "KOTAKBANK - Kotak Mahindra Bank Ltd": "KOTAKBANK.NS",
        "LT - Larsen & Toubro Ltd": "LT.NS",
        "AXISBANK - Axis Bank Ltd": "AXISBANK.NS",
        "HINDUNILVR - Hindustan Unilever Ltd": "HINDUNILVR.NS",
        "BAJFINANCE - Bajaj Finance Ltd": "BAJFINANCE.NS",
        "MARUTI - Maruti Suzuki India Ltd": "MARUTI.NS",
        "SUNPHARMA - Sun Pharmaceutical Industries Ltd": "SUNPHARMA.NS",
        "TITAN - Titan Company Ltd": "TITAN.NS",
        "WIPRO - Wipro Ltd": "WIPRO.NS",
        "ULTRACEMCO - UltraTech Cement Ltd": "ULTRACEMCO.NS",
        "TATAMOTORS - Tata Motors Ltd": "TATAMOTORS.NS",
        "TATASTEEL - Tata Steel Ltd": "TATASTEEL.NS",
        "POWERGRID - Power Grid Corporation of India Ltd": "POWERGRID.NS",
        "NTPC - NTPC Ltd": "NTPC.NS",
        "ONGC - Oil & Natural Gas Corporation Ltd": "ONGC.NS",
        "ASIANPAINT - Asian Paints Ltd": "ASIANPAINT.NS",
        "ZOMATO - Zomato Ltd": "ZOMATO.NS"
    }
    
    for k, v in fallback_stocks.items():
        if k not in stocks:
            stocks[k] = v
            
    return stocks

@st.cache_data(ttl=2)
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
st.sidebar.caption("Equity Paper Terminal")
st.sidebar.markdown("---")

stock_mapping = get_exchange_stocks()
available_products = ["Equity Delivery (CNC) - 1x", "Equity Intraday (MIS) - 5x"]

selected_option = st.sidebar.selectbox("🔍 Search & Select Stock", list(stock_mapping.keys()))
ticker_code = stock_mapping[selected_option]

ltp = fetch_live_price(ticker_code)
if ltp == 0.00:
    ltp = 1000.00

st.sidebar.markdown(f"### Live LTP: `₹{ltp:,.2f}`")

txn_type = st.sidebar.radio("Action Type", ["BUY", "SELL"], horizontal=True)
product = st.sidebar.selectbox("Product Type", available_products)
qty = st.sidebar.number_input("Quantity", min_value=1, value=15)

price_mode = st.sidebar.radio("Price Mode", ["Live LTP", "Manual Price"], horizontal=True)
if price_mode == "Manual Price":
    execution_price = st.sidebar.number_input("Enter Custom Entry Price", min_value=0.05, value=float(ltp), step=0.5)
else:
    execution_price = ltp

st.sidebar.markdown("#### 🛡️ Risk Management (SL / TP)")
sl_price = st.sidebar.number_input("Stop Loss (SL) Price", min_value=0.0, value=0.0, step=0.5)
tp_price = st.sidebar.number_input("Take Profit (TP) Price", min_value=0.0, value=0.0, step=0.5)

margin_mult = 0.2 if "Intraday" in product else 1.0
turnover = execution_price * qty

est_brokerage = min(20.0, turnover * 0.0003)
est_stt = turnover * 0.001 if "Delivery" in product else (turnover * 0.00025 if txn_type == "SELL" else 0.0)
est_regulatory = round(est_brokerage + est_stt + (turnover * 0.00005), 2)
est_platform_fee = 5.00
est_total_fees = est_regulatory + est_platform_fee

est_required = (turnover * margin_mult) + (est_total_fees if txn_type == "BUY" else 0.0)
st.sidebar.caption(f"Margin: **₹{est_required - est_total_fees:,.2f}** | Reg. Charges: **₹{est_regulatory:,.2f}** | Platform Fee: **₹{est_platform_fee:,.2f}**")

if st.sidebar.button("🚀 Execute Order", type="primary", use_container_width=True):
    success, msg = place_order(selected_option, txn_type, product, qty, execution_price, sl_price, tp_price)
    if success:
        st.sidebar.success(msg)
    else:
        st.sidebar.error(msg)

st.sidebar.markdown("---")
if st.sidebar.button("⚠️ Reset Account (Capital ₹10L)", type="secondary"):
    reset_account()
    st.sidebar.success("Account reset successfully!")
    st.rerun()

# Main Dashboard Centered Header
st.title("⚡ TMP TRADING Terminal")
st.markdown("Professional Equity paper trading environment with regulatory taxes and platform infrastructure fees.")

@st.fragment(run_every=2)
def live_dashboard_fragment():
    auto_exit_msgs = check_auto_exits(fetch_live_price, stock_mapping)
    for msg in auto_exit_msgs:
        st.warning(msg)

    account = get_account_summary()
    free_cash = account['cash_balance']
    utilized = account['utilized_margin']
    total_charges = account['total_charges_paid']
    total_platform = account['total_platform_fees']

    positions_df = get_positions()
    total_unrealized_pnl = 0.0

    if not positions_df.empty:
        live_ltps = []
        pnl_list = []
        pnl_pct_list = []
        
        for idx, row in positions_df.iterrows():
            sym_name = row['symbol']
            sym_code = stock_mapping.get(sym_name, "RELIANCE.NS")
                
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

    st.markdown("### 📊 Account Performance Metrics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Available Cash", f"₹{free_cash:,.2f}")
    col2.metric("Utilized Margin", f"₹{utilized:,.2f}")
    col3.metric("Total Net Worth", f"₹{total_portfolio_value:,.2f}")
    col4.metric("Unrealized P&L", f"₹{total_unrealized_pnl:,.2f}", delta=f"₹{total_unrealized_pnl:,.2f}")

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["📊 Active Positions", "📑 Order Book", "💰 Ledger Summary"])

    with tab1:
        st.subheader("Open Positions, SL/TP & Real-Time P&L")
        if not positions_df.empty:
            st.dataframe(positions_df, use_container_width=True)
            
            st.markdown("### ⚙️ Manage SL / TP & Manual Exit")
            col_sym, col_prod, col_sl, col_tp, col_btn = st.columns([2, 2, 1, 1, 1])
            with col_sym:
                mod_symbol = st.selectbox("Position Symbol", positions_df['symbol'].tolist(), key="mod_sym")
            with col_prod:
                mod_product = st.selectbox("Product Type", positions_df[positions_df['symbol'] == mod_symbol]['product'].tolist(), key="mod_prod")
            
            current_pos_row = positions_df[(positions_df['symbol'] == mod_symbol) & (positions_df['product'] == mod_product)]
            default_sl = float(current_pos_row['sl_price'].values[0]) if not current_pos_row.empty else 0.0
            default_tp = float(current_pos_row['tp_price'].values[0]) if not current_pos_row.empty else 0.0
            
            with col_sl:
                new_sl = st.number_input("New SL", value=default_sl, step=0.5, key="new_sl")
            with col_tp:
                new_tp = st.number_input("New TP", value=default_tp, step=0.5, key="new_tp")
            with col_btn:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Update SL/TP", type="secondary"):
                    update_sl_tp(mod_symbol, mod_product, new_sl, new_tp)
                    st.success("SL/TP Updated!")
                    st.rerun()

            st.markdown("---")
            if st.button("❌ Square Off Position", type="primary"):
                so_code = stock_mapping.get(mod_symbol, "RELIANCE.NS")
                exit_price = fetch_live_price(so_code)
                if exit_price == 0.0:
                    exit_price = 1000.0
                
                success, msg = square_off_position(mod_symbol, mod_product, exit_price)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.info("No open positions currently active.")

    with tab2:
        st.subheader("Complete Order Book History & Fees")
        orders_df = get_orders()
        if not orders_df.empty:
            st.dataframe(orders_df, use_container_width=True)
        else:
            st.info("No orders placed yet.")

    with tab3:
        st.subheader("Ledger Details & Brokerage Summary")
        st.json({
            "Broker Name": "TMP TRADING",
            "Available Cash Balance": f"₹{free_cash:,.2f}",
            "Blocked Exposure Margin": f"₹{utilized:,.2f}",
            "Total Regulatory Taxes Paid": f"₹{total_charges:,.2f}",
            "Total Platform Fees Paid": f"₹{total_platform:,.2f}"
        })

live_dashboard_fragment()
