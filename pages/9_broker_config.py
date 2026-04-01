"""
pages/9_broker_config.py
Manage per-broker charge rates.
Charges = max(trade_value x rate%, min_charge)
"""
import streamlit as st
import pandas as pd

from utils.data import (
    load_broker_configs,
    save_broker_config,
    delete_broker_config,
    DEFAULT_BROKERS,
)
from utils.ui import section_header, TEAL, RED, GREY, BORDER, CARD_BG, ORANGE

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
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:4px">Broker Configuration</h1>
<div style="color:#6B7280;margin-bottom:8px">
    Set default brokerage rates per broker.
    Charges are calculated as <strong>max(trade_value × rate%, min_charge)</strong>
    and auto-filled when adding trades.
</div>
""", unsafe_allow_html=True)

# ── Example callout ───────────────────────────────────────────────────────────
with st.expander("How charges are calculated"):
    st.markdown("""
| Trade value | Rate | Min charge | Result |
|---|---|---|---|
| ₹10,000 | 0.03% | ₹20 | max(₹3, ₹20) = **₹20** |
| ₹1,00,000 | 0.03% | ₹20 | max(₹30, ₹20) = **₹30** |
| ₹5,00,000 | 0.03% | ₹20 | max(₹150, ₹20) = **₹150** |

You can set different rates for BUY, SELL, and RIGHTS per broker.
DIVIDEND and BONUS never have charges.
    """)

# ── Current broker table ──────────────────────────────────────────────────────
broker_configs = load_broker_configs()

if broker_configs:
    section_header("Configured Brokers")
    rows = []
    for c in broker_configs:
        rows.append({
            "Broker":           c.get("broker_name", c.get("broker_key", "")),
            "Key":              c.get("broker_key", ""),
            "Buy Rate %":       float(c.get("buy_pct", 0)),
            "Buy Min (₹)":      float(c.get("buy_min", 0)),
            "Sell Rate %":      float(c.get("sell_pct", 0)),
            "Sell Min (₹)":     float(c.get("sell_min", 0)),
            "Rights Rate %":    float(c.get("rights_pct", 0)),
            "Rights Min (₹)":   float(c.get("rights_min", 0)),
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df.style
        .format({
            "Buy Rate %":     "{:.4g}%",
            "Sell Rate %":    "{:.4g}%",
            "Rights Rate %":  "{:.4g}%",
            "Buy Min (₹)":    "₹{:.0f}",
            "Sell Min (₹)":   "₹{:.0f}",
            "Rights Min (₹)": "₹{:.0f}",
        })
        .hide(axis="index"),
        width='stretch',
        height=min(320, 60 + len(rows) * 36),
    )
else:
    st.info("No brokers configured yet. Add one below.")

st.markdown("---")

# ── Add / Edit form ───────────────────────────────────────────────────────────
existing_keys = [c.get("broker_key", "") for c in broker_configs]
edit_options  = ["➕ Add new broker"] + existing_keys
edit_choice   = st.selectbox("Add new or edit existing", edit_options,
                              label_visibility="collapsed")

is_new  = edit_choice == "➕ Add new broker"
edit_cfg = next(
    (c for c in broker_configs if c.get("broker_key") == edit_choice), {}
) if not is_new else {}

section_header(
    "Add Broker" if is_new else f"Edit — {edit_cfg.get('broker_name', edit_choice)}"
)

with st.form("broker_config_form"):
    id_col, name_col = st.columns(2)

    with id_col:
        if is_new:
            available = [k for k in DEFAULT_BROKERS if k not in existing_keys]
            preset    = st.selectbox(
                "Choose preset or enter custom",
                ["CUSTOM"] + available,
                help="Select a preset broker key or choose CUSTOM to type your own.",
            )
            if preset == "CUSTOM":
                b_key = st.text_input(
                    "Broker key (CAPS, no spaces) *",
                    placeholder="MY_BROKER",
                ).strip().upper()
            else:
                b_key = preset
                st.text_input("Broker key", value=b_key, disabled=True)
        else:
            b_key = edit_choice
            st.text_input("Broker key (not editable)", value=b_key, disabled=True)

    with name_col:
        default_name = edit_cfg.get("broker_name", b_key.replace("_", " ").title() if b_key else "")
        b_name = st.text_input("Display name *", value=default_name,
                                placeholder="e.g. Zerodha")

    st.markdown("##### Charge rates by action type")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(f'<div style="color:{TEAL};font-weight:600;margin-bottom:8px">BUY</div>',
                    unsafe_allow_html=True)
        buy_pct = st.number_input(
            "Rate %", min_value=0.0,
            value=float(edit_cfg.get("buy_pct", 0.03)),
            step=0.001, format="%.4f", key="buy_pct",
            help="Brokerage as % of trade value",
        )
        buy_min = st.number_input(
            "Min charge (₹)", min_value=0.0,
            value=float(edit_cfg.get("buy_min", 20.0)),
            step=1.0, format="%.2f", key="buy_min",
            help="Minimum charge regardless of trade size",
        )

    with c2:
        st.markdown(f'<div style="color:{RED};font-weight:600;margin-bottom:8px">SELL</div>',
                    unsafe_allow_html=True)
        sell_pct = st.number_input(
            "Rate %", min_value=0.0,
            value=float(edit_cfg.get("sell_pct", 0.03)),
            step=0.001, format="%.4f", key="sell_pct",
        )
        sell_min = st.number_input(
            "Min charge (₹)", min_value=0.0,
            value=float(edit_cfg.get("sell_min", 20.0)),
            step=1.0, format="%.2f", key="sell_min",
        )

    with c3:
        st.markdown(f'<div style="color:{ORANGE};font-weight:600;margin-bottom:8px">RIGHTS</div>',
                    unsafe_allow_html=True)
        rights_pct = st.number_input(
            "Rate %", min_value=0.0,
            value=float(edit_cfg.get("rights_pct", 0.03)),
            step=0.001, format="%.4f", key="rights_pct",
        )
        rights_min = st.number_input(
            "Min charge (₹)", min_value=0.0,
            value=float(edit_cfg.get("rights_min", 20.0)),
            step=1.0, format="%.2f", key="rights_min",
        )

    # Live preview
    preview_val = 100_000.0
    p_buy   = round(max(preview_val * buy_pct   / 100, buy_min),   2)
    p_sell  = round(max(preview_val * sell_pct  / 100, sell_min),  2)
    p_right = round(max(preview_val * rights_pct / 100, rights_min), 2)

    st.markdown(
        f'<div style="background:{CARD_BG};border:1px solid {BORDER};border-radius:8px;'
        f'padding:10px 16px;margin-top:8px;font-size:0.84rem;color:{GREY}">'
        f'Example charges on a ₹1,00,000 trade: '
        f'<span style="color:{TEAL}">BUY ₹{p_buy:,.2f}</span> · '
        f'<span style="color:{RED}">SELL ₹{p_sell:,.2f}</span> · '
        f'<span style="color:{ORANGE}">RIGHTS ₹{p_right:,.2f}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:4px'/>", unsafe_allow_html=True)
    save_btn = st.form_submit_button(
        "💾 Save broker config", type="primary", width='stretch'
    )

if save_btn:
    final_key = b_key if is_new else edit_choice
    if not final_key:
        st.error("Broker key is required.")
    elif not b_name.strip():
        st.error("Display name is required.")
    else:
        try:
            save_broker_config({
                "broker_key":  final_key,
                "broker_name": b_name.strip(),
                "buy_pct":     buy_pct,
                "buy_min":     buy_min,
                "sell_pct":    sell_pct,
                "sell_min":    sell_min,
                "rights_pct":  rights_pct,
                "rights_min":  rights_min,
            })
            st.success(f"✅ Broker **{b_name.strip()}** saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save: {e}")

# ── Delete ────────────────────────────────────────────────────────────────────
if broker_configs:
    st.markdown("---")
    section_header("Delete Broker")
    st.markdown(
        f'<div style="color:{GREY};font-size:0.85rem;margin-bottom:12px">'
        'Deleting a broker does not affect existing trades — they keep their broker tag. '
        'Only the charge rate config is removed.</div>',
        unsafe_allow_html=True,
    )
    del_col, btn_col = st.columns([2, 1])
    with del_col:
        del_choice = st.selectbox(
            "Select broker to delete", existing_keys, label_visibility="collapsed"
        )
    with btn_col:
        st.markdown("<div style='height:26px'/>", unsafe_allow_html=True)
        if st.button("🗑️ Delete", width='stretch'):
            try:
                delete_broker_config(del_choice)
                st.success(f"Broker `{del_choice}` deleted.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")
