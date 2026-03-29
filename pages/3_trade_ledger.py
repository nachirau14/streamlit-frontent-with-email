"""
pages/3_trade_ledger.py
Full trade ledger with broker and sector columns and filters.
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from utils.data import load_all_trades
from utils.ui import (
    fmt_inr, section_header,
    TEAL, RED, GREY, BORDER, CARD_BG, CYAN, PURPLE, ORANGE,
    ACTION_COLOURS,
)

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.3rem;font-weight:800;color:#00A88A;padding:16px 0 24px">'
        "📈 XIRR Tracker</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("🔄  Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("""
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:4px">Trade Ledger</h1>
<div style="color:#6B7280;margin-bottom:24px">
    All transactions and corporate actions across the portfolio
</div>
""", unsafe_allow_html=True)

# ── Load ──────────────────────────────────────────────────────────────────────
with st.spinner("Loading all trades…"):
    try:
        all_trades = load_all_trades()
    except Exception as e:
        st.error(f"DynamoDB error: {e}")
        st.stop()

if not all_trades:
    st.warning("No trade records found.")
    st.stop()

# ── Flatten to DataFrame ──────────────────────────────────────────────────────
rows = []
for symbol, trades in all_trades.items():
    for t in trades:
        qty     = float(t.get("qty", 0))
        price   = float(t.get("price", 0))
        charges = float(t.get("charges", 0))
        action  = t.get("action", "").upper()

        if action in ("BUY", "RIGHTS"):
            value = -(qty * price + charges)
        elif action == "SELL":
            value = qty * price - charges
        elif action == "DIVIDEND":
            value = qty * price
        else:
            value = 0.0

        rows.append({
            "Date":        t.get("trade_date", ""),
            "Symbol":      symbol,
            "Action":      action,
            "Broker":      t.get("broker", ""),
            "Sector":      t.get("sector", ""),
            "Qty":         qty,
            "Price (₹)":   price,
            "Charges (₹)": charges,
            "Net (₹)":     value,
            "Notes":       t.get("notes", ""),
        })

df = pd.DataFrame(rows).sort_values(["Date", "Symbol"], ascending=[False, True])

# ── Filter controls ───────────────────────────────────────────────────────────
f1, f2, f3, f4 = st.columns([2, 2, 2, 2])

with f1:
    _ledger_symbols = sorted(df["Symbol"].dropna().unique().tolist())
    sym_search = st.multiselect(
        "Symbol",
        options=_ledger_symbols,
        default=[],
        placeholder="All scrips",
        label_visibility="collapsed",
    )
with f2:
    action_filter = st.multiselect(
        "Action", options=["BUY", "SELL", "DIVIDEND", "BONUS", "RIGHTS"],
        default=[], label_visibility="collapsed", placeholder="All actions",
    )
with f3:
    # Broker filter — from actual data
    all_brokers = sorted(df["Broker"].replace("", pd.NA).dropna().unique())
    broker_filter = st.multiselect(
        "Broker", options=all_brokers,
        default=[], label_visibility="collapsed", placeholder="All brokers",
    )
with f4:
    all_sectors = sorted(df["Sector"].replace("", pd.NA).dropna().unique())
    sector_filter = st.multiselect(
        "Sector", options=all_sectors,
        default=[], label_visibility="collapsed", placeholder="All sectors",
    )

f5, f6, f7 = st.columns([2, 2, 2])
with f5:
    date_range = st.selectbox(
        "Period",
        ["All time", "Last 30 days", "Last 90 days", "Last 1 year", "This FY"],
        label_visibility="collapsed",
    )
with f6:
    min_val = st.number_input("Min value (₹)", value=0, step=1000,
                               label_visibility="collapsed")
with f7:
    sort_col = st.selectbox("Sort by", ["Date", "Symbol", "Net (₹)", "Qty"],
                             label_visibility="collapsed")

# ── Apply filters ─────────────────────────────────────────────────────────────
dff = df.copy()

if sym_search:
    dff = dff[dff["Symbol"].isin(sym_search)]
if action_filter:
    dff = dff[dff["Action"].isin(action_filter)]
if broker_filter:
    dff = dff[dff["Broker"].isin(broker_filter)]
if sector_filter:
    dff = dff[dff["Sector"].isin(sector_filter)]

today = date.today()
if date_range == "Last 30 days":
    dff = dff[dff["Date"] >= (today - timedelta(days=30)).isoformat()]
elif date_range == "Last 90 days":
    dff = dff[dff["Date"] >= (today - timedelta(days=90)).isoformat()]
elif date_range == "Last 1 year":
    dff = dff[dff["Date"] >= (today - timedelta(days=365)).isoformat()]
elif date_range == "This FY":
    fy_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1).isoformat()
    dff = dff[dff["Date"] >= fy_start]

if min_val > 0:
    dff = dff[dff["Net (₹)"].abs() >= min_val]

dff = dff.sort_values(sort_col, ascending=(sort_col == "Symbol"))

# ── Summary metrics ───────────────────────────────────────────────────────────
total_buy  = dff[dff["Action"].isin(["BUY", "RIGHTS"])]["Net (₹)"].abs().sum()
total_sell = dff[dff["Action"] == "SELL"]["Net (₹)"].sum()
total_div  = dff[dff["Action"] == "DIVIDEND"]["Net (₹)"].sum()

s1, s2, s3, s4 = st.columns(4)
s1.metric("Records shown",  f"{len(dff):,}")
s2.metric("Total Outflows", fmt_inr(total_buy))
s3.metric("Total Inflows",  fmt_inr(total_sell))
s4.metric("Dividends",      fmt_inr(total_div))

st.markdown("<div style='height:8px'/>", unsafe_allow_html=True)

# ── Styled table ──────────────────────────────────────────────────────────────
def style_action(val):
    c = ACTION_COLOURS.get(str(val).upper(), GREY)
    return f"color: {c}; font-weight: 600"

def style_net(val):
    if val > 0:  return f"color: {TEAL}"
    if val < 0:  return f"color: {RED}"
    return f"color: {GREY}"

def style_broker(val):
    if val:
        return f"color: {ORANGE}; font-size: 0.82rem"
    return f"color: {GREY}"

def style_sector(val):
    if val:
        return f"color: {CYAN}; font-size: 0.82rem"
    return f"color: {GREY}"

styled = (
    dff.style
    .format({
        "Qty":         lambda x: f"{x:,.0f}",
        "Price (₹)":   lambda x: f"₹{x:,.4f}" if x else "—",
        "Charges (₹)": lambda x: f"₹{x:,.2f}" if x else "—",
        "Net (₹)":     lambda x: f"₹{x:,.2f}",
        "Broker":      lambda x: x if x else "—",
        "Sector":      lambda x: x if x else "—",
    })
    .applymap(style_action, subset=["Action"])
    .applymap(style_net,    subset=["Net (₹)"])
    .applymap(style_broker, subset=["Broker"])
    .applymap(style_sector, subset=["Sector"])
    .hide(axis="index")
)

st.dataframe(styled, use_container_width=True, height=520)

# ── Export ────────────────────────────────────────────────────────────────────
st.download_button(
    "⬇️ Export CSV",
    data=dff.to_csv(index=False),
    file_name=f"trade_ledger_{today}.csv",
    mime="text/csv",
)

# ── Breakdown ─────────────────────────────────────────────────────────────────
bc1, bc2 = st.columns(2)

with bc1:
    section_header("By Action")
    agg = (
        dff.groupby("Action")
        .agg(Records=("Action", "count"),
             Value=("Net (₹)", lambda x: x.abs().sum()),
             Scrips=("Symbol", "nunique"))
        .reset_index()
        .sort_values("Records", ascending=False)
    )
    st.dataframe(
        agg.style
        .format({"Value": lambda x: fmt_inr(x)})
        .applymap(style_action, subset=["Action"])
        .hide(axis="index"),
        use_container_width=True, height=220,
    )

with bc2:
    section_header("By Broker")
    if dff["Broker"].replace("", pd.NA).notna().any():
        agg_b = (
            dff[dff["Broker"] != ""]
            .groupby("Broker")
            .agg(Records=("Broker", "count"),
                 Value=("Net (₹)", lambda x: x.abs().sum()),
                 Scrips=("Symbol", "nunique"))
            .reset_index()
            .sort_values("Records", ascending=False)
        )
        st.dataframe(
            agg_b.style
            .format({"Value": lambda x: fmt_inr(x)})
            .applymap(style_broker, subset=["Broker"])
            .hide(axis="index"),
            use_container_width=True, height=220,
        )
    else:
        st.info("No broker tags on any records yet.")
