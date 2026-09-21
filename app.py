"""
app.py  —  Entry point and auth gate for the Portfolio XIRR Dashboard.

This file does two things only:
  1. Shows the login form if the user is not authenticated.
  2. Once authenticated, registers all pages via st.navigation() and runs them.

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

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Hide Streamlit footer and header branding — but NOT the sidebar toggle */
    footer { visibility: hidden; }
    header { visibility: hidden; }

    /* Keep hamburger visible on mobile so users can open the sidebar */
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
    }

    .block-container { padding-top: 1rem; }

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
    [data-testid="stExpander"] {
        border: 1px solid #E2E8F0 !important;
        border-radius: 8px !important;
    }
    .stDataFrame { border: 1px solid #E2E8F0; border-radius: 8px; }

    /* ── Mobile nav strip ───────────────────────────────────────────────────
       Shown only on narrow screens (≤ 640 px).
       Gives one-tap access to the four most-used pages without opening the
       sidebar. Sits at the bottom of the viewport (safe-area aware).       */
    .mobile-nav {
        display: none;
    }
    @media (max-width: 640px) {
        /* Push page content up so it isn't hidden behind the nav strip */
        .block-container {
            padding-bottom: calc(68px + env(safe-area-inset-bottom, 0px)) !important;
        }
        .mobile-nav {
            display: flex;
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            z-index: 9999;
            background: #FFFFFF;
            border-top: 1px solid #E2E8F0;
            padding-bottom: env(safe-area-inset-bottom, 0px);
            justify-content: space-around;
            align-items: center;
            height: 60px;
            box-shadow: 0 -2px 8px rgba(0,0,0,0.06);
        }
        .mobile-nav a {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            font-size: 0.62rem;
            color: #6B7280;
            text-decoration: none;
            gap: 2px;
            flex: 1;
            padding: 6px 2px;
        }
        .mobile-nav a span.icon { font-size: 1.3rem; line-height: 1; }
        .mobile-nav a:hover,
        .mobile-nav a:active { color: #00A88A; }

        /* Enlarge the sidebar hamburger so it's easy to tap */
        [data-testid="collapsedControl"] button {
            width: 44px !important;
            height: 44px !important;
        }

        /* Sidebar full-width overlay on mobile */
        [data-testid="stSidebar"] {
            min-width: 80vw !important;
            max-width: 90vw !important;
        }
    }
</style>

<!-- Bottom mobile navigation strip — visible only on narrow screens -->
<div class="mobile-nav" aria-label="Mobile navigation">
    <a href="/" title="Overview">
        <span class="icon">🏠</span>Overview
    </a>
    <a href="/Scrip_Deep-Dive" title="Scrip">
        <span class="icon">🔍</span>Scrip
    </a>
    <a href="/Trade_Ledger" title="Ledger">
        <span class="icon">📋</span>Ledger
    </a>
    <a href="/Add_Trade" title="Add">
        <span class="icon">➕</span>Add
    </a>
    <a href="/Analytics" title="Analytics">
        <span class="icon">📊</span>Analytics
    </a>
</div>
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
        f'Signed in as<br><strong>{current_user()}</strong></div>',
        unsafe_allow_html=True,
    )
    if col_o.button("Sign out", width='stretch'):
        logout()

    st.markdown(
        f'<div style="color:#6B7280;font-size:0.72rem;margin-top:12px">'
        f'Data cached 5 min · {date.today().strftime("%d %b %Y")}</div>',
        unsafe_allow_html=True,
    )

# Register all pages
pg = st.navigation([
    st.Page("pages/1_overview.py",        title="Portfolio Overview", icon="🏠"),
    st.Page("pages/2_scrip_detail.py",    title="Scrip Deep-Dive",    icon="🔍"),
    st.Page("pages/3_trade_ledger.py",    title="Trade Ledger",       icon="📋"),
    st.Page("pages/4_add_trade.py",       title="Add Trade",          icon="➕"),
    st.Page("pages/5_analytics.py",       title="Analytics",          icon="📊"),
    st.Page("pages/6_bulk_upload.py",     title="Bulk Upload",        icon="📤"),
    st.Page("pages/7_edit_trades.py",     title="Edit Trades",        icon="✏️"),
    st.Page("pages/9_broker_config.py",   title="Broker Config",      icon="🏦"),
    st.Page("pages/10_email_config.py",   title="Email Alerts",       icon="📧"),
    st.Page("pages/0_debug_connection.py",title="Connection Debug",   icon="🔧"),
])
pg.run()
