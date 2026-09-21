"""
app.py — Entry point and auth gate for the Portfolio XIRR Dashboard.

Mobile navigation: bottom tab bar using st.switch_page() so session
state (authentication) is never lost on page change.

Requires Streamlit >= 1.36 for st.navigation() / st.switch_page() support.
"""
import streamlit as st

st.set_page_config(
    page_title="Portfolio XIRR Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",    # visible on desktop; mobile collapses it automatically
)

from utils.auth import _show_login_form, logout, current_user
from utils.ui import TEAL, GREY, BORDER

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    footer { visibility: hidden; }
    header { visibility: hidden; }

    /* Keep hamburger visible */
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
    [data-testid="stSidebar"] {
        background: #F4F6F8;
        border-right: 1px solid #E2E8F0;
    }
    [data-testid="stExpander"] {
        border: 1px solid #E2E8F0 !important;
        border-radius: 8px !important;
    }
    .stDataFrame { border: 1px solid #E2E8F0; border-radius: 8px; }

    /* Mobile improvements */
    @media (max-width: 640px) {
        [data-testid="stSidebar"] {
            min-width: 80vw !important;
            max-width: 90vw !important;
        }
    }
</style>
""", unsafe_allow_html=True)


# ── Step 1: Auth gate ─────────────────────────────────────────────────────────
if not st.session_state.get("authenticated", False):
    _show_login_form()
    st.stop()


# ── Step 2: Authenticated — sidebar nav ──────────────────────────────────────
from datetime import date

with st.sidebar:
    st.markdown(
        '<div style="padding:12px 0 16px 0">'
        '<div style="font-size:1.3rem;font-weight:800;color:#00A88A">📈 XIRR Tracker</div>'
        '<div style="font-size:0.78rem;color:#6B7280;margin-top:2px">Indian Equity Portfolio</div>'
        '</div>',
        unsafe_allow_html=True,
    )
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

# ── Step 3: Register pages ────────────────────────────────────────────────────
pg = st.navigation([
    st.Page("pages/1_overview.py",         title="Portfolio Overview", icon="🏠"),
    st.Page("pages/2_scrip_detail.py",     title="Scrip Deep-Dive",    icon="🔍"),
    st.Page("pages/3_trade_ledger.py",     title="Trade Ledger",       icon="📋"),
    st.Page("pages/4_add_trade.py",        title="Add Trade",          icon="➕"),
    st.Page("pages/5_analytics.py",        title="Analytics",          icon="📊"),
    st.Page("pages/6_bulk_upload.py",      title="Bulk Upload",        icon="📤"),
    st.Page("pages/7_edit_trades.py",      title="Edit Trades",        icon="✏️"),
    st.Page("pages/9_broker_config.py",    title="Broker Config",      icon="🏦"),
    st.Page("pages/10_email_config.py",    title="Email Alerts",       icon="📧"),
    st.Page("pages/0_debug_connection.py", title="Connection Debug",   icon="🔧"),
])
pg.run()


# ── Step 4: Mobile navigation — floating popover button ──────────────────────
# A single 📍 button fixed to the bottom-right corner opens a compact popover
# with all pages. Uses st.popover (available since Streamlit 1.31) +
# st.switch_page so session state is fully preserved on navigation.

ALL_PAGES = [
    ("🏠", "Portfolio Overview", "pages/1_overview.py"),
    ("🔍", "Scrip Deep-Dive",    "pages/2_scrip_detail.py"),
    ("📋", "Trade Ledger",       "pages/3_trade_ledger.py"),
    ("➕", "Add Trade",          "pages/4_add_trade.py"),
    ("📊", "Analytics",          "pages/5_analytics.py"),
    ("📤", "Bulk Upload",        "pages/6_bulk_upload.py"),
    ("✏️", "Edit Trades",        "pages/7_edit_trades.py"),
    ("🏦", "Broker Config",      "pages/9_broker_config.py"),
    ("📧", "Email Alerts",       "pages/10_email_config.py"),
]

# Inject a fixed-position wrapper so the popover trigger sits at bottom-right
st.markdown("""
<style>
/* Anchor the popover trigger to bottom-right on all screen sizes */
div[data-testid="stPopover"] {
    position: fixed !important;
    bottom: 20px !important;
    right: 20px !important;
    z-index: 9999 !important;
}
div[data-testid="stPopover"] > div > button {
    width: 52px !important;
    height: 52px !important;
    border-radius: 50% !important;
    font-size: 1.4rem !important;
    padding: 0 !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18) !important;
    background: #00A88A !important;
    color: white !important;
    border: none !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
</style>
""", unsafe_allow_html=True)

with st.popover("☰", use_container_width=False):
    st.markdown(
        '<div style="font-size:0.78rem;color:#6B7280;'
        'text-transform:uppercase;letter-spacing:0.06em;'
        'margin-bottom:8px">Navigate to</div>',
        unsafe_allow_html=True,
    )
    for icon, label, page_path in ALL_PAGES:
        if st.button(
            f"{icon}  {label}",
            key=f"pop_nav_{label}",
            width="stretch",
        ):
            st.switch_page(page_path)
