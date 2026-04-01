"""
app.py  —  Entry point and auth gate for the Portfolio XIRR Dashboard.

This file does two things only:
  1. Shows the login form if the user is not authenticated.
  2. Once authenticated, registers all pages via st.navigation() and runs them.

Pages themselves contain zero auth code. Unauthenticated users cannot reach
any page URL because the pages are never registered until login succeeds.

Requires Streamlit >= 1.36 for st.navigation() support.
"""
import streamlit as st

st.set_page_config(
    page_title="Portfolio XIRR Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.auth import _show_login_form, logout, current_user
from utils.ui import TEAL, GREY, BORDER

# ── Global CSS (applied to all pages) ────────────────────────────────────────
st.markdown("""
<style>
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.5rem; }
    .dataframe thead tr th {
        background: #F4F6F8 !important;
        color: #374151 !important;
        font-size: 0.78rem !important;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .stTabs [data-baseweb="tab"] { color: #6B7280; font-weight: 500; }
    .stTabs [aria-selected="true"] {
        color: #00A88A !important;
        border-bottom: 2px solid #00A88A;
    }
    [data-testid="stMetricDelta"] { font-size: 0.8rem; }
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #F4F6F8;
        border-right: 1px solid #E2E8F0;
    }
    /* Cards / expanders */
    [data-testid="stExpander"] {
        border: 1px solid #E2E8F0 !important;
        border-radius: 8px !important;
    }
    /* Dataframe */
    .stDataFrame { border: 1px solid #E2E8F0; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


# ── Step 1: Auth gate ─────────────────────────────────────────────────────────
if not st.session_state.get("authenticated", False):
    _show_login_form()
    st.stop()


# ── Step 2: Authenticated — build navigation and run ─────────────────────────
from datetime import date

with st.sidebar:
    st.markdown("""
    <div style="padding:12px 0 16px 0">
        <div style="font-size:1.3rem;font-weight:800;color:#00A88A">📈 XIRR Tracker</div>
        <div style="font-size:0.78rem;color:#6B7280;margin-top:2px">Indian Equity Portfolio</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    if st.button("🔄  Refresh Data", width='stretch'):
        st.cache_data.clear()
        st.rerun()

    st.markdown("<div style='height:4px'/>", unsafe_allow_html=True)

    col_u, col_o = st.columns([2, 1])
    col_u.markdown(
        f'<div style="color:{GREY};font-size:0.78rem;padding-top:6px">'
        f'Signed in as<br><strong style="color:#FAFAFA">{current_user()}</strong></div>',
        unsafe_allow_html=True,
    )
    if col_o.button("Sign out", width='stretch'):
        logout()

    st.markdown(
        f'<div style="color:#4B5563;font-size:0.72rem;margin-top:12px">'
        f'Data cached 5 min<br>{date.today().strftime("%d %b %Y")}</div>',
        unsafe_allow_html=True,
    )

# Register all pages
pg = st.navigation([
    st.Page("pages/1_overview.py",         title="Portfolio Overview", icon="🏠"),
    st.Page("pages/2_scrip_detail.py",      title="Scrip Deep-Dive",    icon="🔍"),
    st.Page("pages/3_trade_ledger.py",      title="Trade Ledger",       icon="📋"),
    st.Page("pages/4_add_trade.py",         title="Add Trade",          icon="➕"),
    st.Page("pages/5_analytics.py",         title="Analytics",          icon="📊"),
    st.Page("pages/6_bulk_upload.py",       title="Bulk Upload",        icon="📤"),
    st.Page("pages/7_edit_trades.py",       title="Edit Trades",        icon="✏️"),
    st.Page("pages/9_broker_config.py",     title="Broker Config",      icon="🏦"),
    st.Page("pages/10_email_config.py",    title="Email Alerts",       icon="📧"),
    st.Page("pages/0_debug_connection.py",  title="Connection Debug",   icon="🔧"),
])
pg.run()
