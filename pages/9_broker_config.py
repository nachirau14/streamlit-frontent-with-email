"""
pages/9_broker_config.py
Manage brokers — simple name-based list.
Brokers are auto-registered when trades are added or uploaded.
"""
import streamlit as st

from utils.data import (
    load_broker_configs,
    save_broker_config,
    delete_broker_config,
    get_all_broker_names,
    load_all_trades,
)
from utils.ui import section_header, TEAL, RED, GREY, BORDER, CARD_BG

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.3rem;font-weight:800;color:#00A88A;padding:16px 0 24px">'
        "📈 XIRR Tracker</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("🔄 Refresh", width='stretch'):
        st.cache_data.clear()
        st.rerun()

st.markdown("""
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:4px">Broker List</h1>
<div style="color:#6B7280;margin-bottom:24px">
    Brokers are added automatically when trades are recorded or uploaded.
    You can also add or remove brokers manually here.
</div>
""", unsafe_allow_html=True)

broker_configs = load_broker_configs()

# ── Current brokers ───────────────────────────────────────────────────────────
section_header("Configured Brokers")

if broker_configs:
    for c in broker_configs:
        col_name, col_del = st.columns([4, 1])
        with col_name:
            st.markdown(
                f'<div style="background:{CARD_BG};border:1px solid {BORDER};'
                f'border-radius:8px;padding:10px 16px;margin-bottom:6px;'
                f'font-weight:600">{c.get("broker_name", c.get("broker_key",""))}</div>',
                unsafe_allow_html=True,
            )
        with col_del:
            st.markdown("<div style='height:6px'/>", unsafe_allow_html=True)
            if st.button("🗑️", key=f"del_{c.get('broker_key','')}",
                         help=f"Remove {c.get('broker_name','')}",
                         width='stretch'):
                try:
                    delete_broker_config(c["broker_key"])
                    st.cache_data.clear()
                    st.success(f"Removed {c.get('broker_name','')}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")
else:
    st.info(
        "No brokers configured yet. They will be added automatically when you "
        "record a trade or upload a CSV."
    )

# ── Brokers found in trades but not yet registered ────────────────────────────
configured_keys = {c.get("broker_key","") for c in broker_configs}
unregistered = []
try:
    all_t = load_all_trades()
    seen  = set()
    for trades in all_t.values():
        for t in trades:
            bk = t.get("broker","").strip().upper()
            if bk and bk not in configured_keys and bk not in seen:
                seen.add(bk)
                unregistered.append(bk)
except Exception:
    pass

if unregistered:
    st.markdown("---")
    section_header(
        "Brokers in Your Trades (not yet registered)",
        "Click to add them to the list"
    )
    for bk in sorted(unregistered):
        col_name, col_add = st.columns([4, 1])
        display = bk.replace("_", " ").title()
        with col_name:
            st.markdown(
                f'<div style="background:#F9FAFB;border:1px dashed {BORDER};'
                f'border-radius:8px;padding:10px 16px;margin-bottom:6px;'
                f'color:{GREY}">{display}</div>',
                unsafe_allow_html=True,
            )
        with col_add:
            st.markdown("<div style='height:6px'/>", unsafe_allow_html=True)
            if st.button("➕ Add", key=f"add_{bk}", width='stretch'):
                try:
                    save_broker_config({"broker_key": bk, "broker_name": display})
                    st.cache_data.clear()
                    st.success(f"Added {display}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")

# ── Manual add ────────────────────────────────────────────────────────────────
st.markdown("---")
section_header("Add Broker Manually")

with st.form("add_broker_form", clear_on_submit=True):
    new_name = st.text_input(
        "Broker name",
        placeholder="e.g. Zerodha, HDFC Securities, Angel One",
        help="The name will appear in the broker dropdown when adding trades.",
    )
    if st.form_submit_button("➕ Add broker", type="primary", width='stretch'):
        name = new_name.strip()
        if not name:
            st.error("Please enter a broker name.")
        else:
            key = name.upper().replace(" ", "_")
            if key in configured_keys:
                st.warning(f"{name} is already in the list.")
            else:
                try:
                    save_broker_config({"broker_key": key, "broker_name": name})
                    st.cache_data.clear()
                    st.success(f"✅ Added {name}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")
