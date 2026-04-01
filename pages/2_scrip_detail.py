"""
pages/1_scrip_detail.py
Scrip Deep-Dive: XIRR history, cashflow waterfall, trade timeline.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date

from utils.data import (
    load_all_latest_xirr, load_xirr_history,
    load_trades_for_scrip, load_all_trades,
    compute_xirr,
)
from utils.ui import (
    fmt_inr, fmt_pct, fmt_qty, xirr_colour,
    metric_card, section_header, action_badge,
    xirr_history_chart, waterfall_chart,
    TEAL, RED, GREY, BORDER, CARD_BG, CYAN, PURPLE, ORANGE,
    ACTION_COLOURS, LAYOUT_DEFAULTS,
)

# ── Sidebar nav ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="font-size:1.3rem;font-weight:800;color:#00A88A;padding:16px 0 24px">📈 XIRR Tracker</div>', unsafe_allow_html=True)
    st.markdown("---")
    if st.button("🔄  Refresh", width='stretch'):
        st.cache_data.clear(); st.rerun()


# ── Symbol picker ─────────────────────────────────────────────────────────────
# Drive symbol list from the TRADES table so newly uploaded scrips
# appear immediately without waiting for the Lambda to run.
with st.spinner("Loading…"):
    try:
        all_trades_map = load_all_trades()
    except Exception as e:
        st.error(f"DynamoDB connection error: {e}")
        st.stop()

# Also load snapshots for LMP and XIRR history
try:
    all_snapshots = load_all_latest_xirr()
except Exception:
    all_snapshots = []

scrips = sorted(all_trades_map.keys())
if not scrips:
    st.warning("No trade records found. Upload trades using the Bulk Upload page.")
    st.stop()

# Allow pre-selection via URL query param ?symbol=RELIANCE
query_sym   = st.query_params.get("symbol", "")
default_idx = scrips.index(query_sym) if query_sym in scrips else 0

selected = st.selectbox(
    "Select scrip",
    scrips,
    index=default_idx,
    format_func=lambda s: f"  {s}",
)
st.query_params["symbol"] = selected


# ── Load scrip data ───────────────────────────────────────────────────────────
snapshot = next((s for s in all_snapshots if s.get("symbol") == selected), {})
trades   = load_trades_for_scrip(selected)
history  = load_xirr_history(selected, limit=90)

# LMP comes from the snapshot (set by the last Lambda run)
# All other KPIs are always recomputed from raw trades so they are never stale
lmp   = float(snapshot.get("lmp", 0))
as_of = snapshot.get("as_of", date.today().isoformat())

if trades and lmp > 0:
    _calc = compute_xirr(trades, lmp, date.today().isoformat())
    xirr  = _calc.get("xirr_pct")
    cv    = _calc.get("current_value",   0)
    ti    = _calc.get("total_invested",  0)
    tr    = _calc.get("total_realised",  0)
    td    = _calc.get("total_dividends", 0)
    bs    = _calc.get("bonus_shares",    0)
    rs    = _calc.get("rights_shares",   0)
    rc    = _calc.get("rights_cost",     0)
    hq    = _calc.get("holdings_qty",    0)
else:
    # No LMP yet (Lambda hasn't run) — fall back to snapshot values
    xirr  = snapshot.get("xirr_pct")
    cv    = float(snapshot.get("current_value",   0))
    ti    = float(snapshot.get("total_invested",  0))
    tr    = float(snapshot.get("total_realised",  0))
    td    = float(snapshot.get("total_dividends", 0))
    bs    = float(snapshot.get("bonus_shares",    0))
    rs    = float(snapshot.get("rights_shares",   0))
    rc    = float(snapshot.get("rights_cost",     0))
    hq    = float(snapshot.get("holdings_qty",    0))


# ── Header ────────────────────────────────────────────────────────────────────
colour = xirr_colour(xirr)
st.markdown(f"""
<div style="display:flex;align-items:center;gap:16px;margin-bottom:24px">
    <div style="background:{colour}22;border:1px solid {colour}55;
                border-radius:12px;padding:10px 20px">
        <div style="font-size:2rem;font-weight:800;color:{colour}">{selected}</div>
    </div>
    <div>
        <div style="font-size:1rem;color:#6B7280">NSE · Last updated {as_of}</div>
        <div style="font-size:1.6rem;font-weight:700;color:{colour}">
            XIRR {fmt_pct(xirr)}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# ── KPI row ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1: metric_card("LMP",          f"₹{lmp:,.2f}",   colour=TEAL)
with c2: metric_card("Current Value", fmt_inr(cv),       colour=TEAL)
with c3: metric_card("Invested",      fmt_inr(ti),       colour="#6B7280")
with c4: metric_card("Dividends",     fmt_inr(td),       colour=CYAN)
with c5: metric_card("Holdings",      fmt_qty(hq),       colour=TEAL)
with c6: metric_card("Bonus Shares",  fmt_qty(bs) if bs else "—", colour=PURPLE)

# Broker / sector tags from trade records
if trades:
    _brokers = sorted({t.get("broker","").strip() for t in trades if t.get("broker","").strip()})
    _sectors = sorted({t.get("sector","").strip() for t in trades if t.get("sector","").strip()})
    tag_parts = []
    if _brokers:
        tag_parts.append(
            f'<span style="color:#FFA500;font-size:0.82rem">🏦 '
            + " · ".join(_brokers) + "</span>"
        )
    if _sectors:
        tag_parts.append(
            f'<span style="color:#4ECDC4;font-size:0.82rem">🏷️ '
            + " · ".join(_sectors) + "</span>"
        )
    if tag_parts:
        st.markdown(
            f'<div style="margin-top:10px;display:flex;gap:20px;flex-wrap:wrap">'
            + " &nbsp;|&nbsp; ".join(tag_parts) + "</div>",
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:20px'/>", unsafe_allow_html=True)

# ── Charts row ────────────────────────────────────────────────────────────────
left, right = st.columns([3, 2])

with left:
    section_header("XIRR History", "Daily snapshots · last 90 days")
    if history:
        st.plotly_chart(xirr_history_chart(history, f"{selected} XIRR %"),
                        width='stretch', config={"displayModeBar": False})
    else:
        st.info("No history yet — builds up daily after Lambda runs.")

with right:
    section_header("Cash Flow Breakdown")
    if snapshot:
        st.plotly_chart(waterfall_chart(snapshot),
                        width='stretch', config={"displayModeBar": False})


# ── Cumulative cost basis chart ───────────────────────────────────────────────
if trades:
    section_header("Trade Timeline", "Cumulative cost basis over time")

    rows = []
    running_qty  = 0.0
    running_cost = 0.0
    running_div  = 0.0

    for t in sorted(trades, key=lambda x: x["trade_date"]):
        action  = t["action"].upper()
        qty     = float(t["qty"])
        price   = float(t["price"])
        charges = float(t.get("charges", 0))

        if action == "BUY":
            running_cost += qty * price + charges
            running_qty  += qty
        elif action == "SELL":
            running_qty  -= qty
        elif action == "DIVIDEND":
            running_div  += qty * price
        elif action == "BONUS":
            running_qty  += qty
        elif action == "RIGHTS":
            running_cost += qty * price + charges
            running_qty  += qty

        rows.append({
            "date":     t["trade_date"],
            "action":   action,
            "cost":     running_cost,
            "qty":      running_qty,
            "dividends":running_div,
            "price":    price,
            "event_qty":qty,
            "notes":    t.get("notes", ""),
        })

    df_timeline = pd.DataFrame(rows)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_timeline["date"], y=df_timeline["cost"],
        name="Cumulative Cost", line=dict(color=RED, width=2),
        fill="tozeroy", fillcolor="rgba(255,107,107,0.08)",
        hovertemplate="<b>%{x}</b><br>Cost: ₹%{y:,.0f}<extra></extra>",
    ))
    if df_timeline["dividends"].max() > 0:
        fig.add_trace(go.Scatter(
            x=df_timeline["date"], y=df_timeline["dividends"],
            name="Cumulative Dividends", line=dict(color=CYAN, width=1.5, dash="dot"),
            hovertemplate="<b>%{x}</b><br>Dividends: ₹%{y:,.0f}<extra></extra>",
        ))

    # Event markers
    for action, colour in ACTION_COLOURS.items():
        subset = df_timeline[df_timeline["action"] == action]
        if subset.empty:
            continue
        fig.add_trace(go.Scatter(
            x=subset["date"], y=subset["cost"],
            mode="markers",
            name=action,
            marker=dict(color=colour, size=9, symbol="circle",
                        line=dict(color="white", width=1)),
            customdata=subset[["event_qty", "price", "notes"]].values,
            hovertemplate=(
                f"<b>{action}</b><br>"
                "Qty: %{customdata[0]:.0f}<br>"
                "Price: ₹%{customdata[1]:,.2f}<br>"
                "%{customdata[2]}<extra></extra>"
            ),
        ))

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        height=320,
        yaxis_title="₹",
        legend=dict(orientation="h", y=-0.2),
    )
    st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})


# ── Trade ledger for this scrip ───────────────────────────────────────────────
section_header("Transaction History", f"{len(trades)} records")

if trades:
    df_trades = pd.DataFrame([{
        "Date":        t["trade_date"],
        "Action":      t["action"],
        "Broker":      t.get("broker", ""),
        "Sector":      t.get("sector", ""),
        "Qty":         float(t["qty"]),
        "Price (₹)":   float(t["price"]),
        "Charges (₹)": float(t.get("charges", 0)),
        "Value (₹)":   float(t["qty"]) * float(t["price"]),
        "Notes":       t.get("notes", ""),
    } for t in sorted(trades, key=lambda x: x["trade_date"], reverse=True)])

    def style_action(val):
        c = ACTION_COLOURS.get(val.upper(), GREY)
        return f"color: {c}; font-weight: 600"

    def style_broker_sec(val):
        return f"color: #FFA500; font-size: 0.82rem" if val else f"color: {GREY}"
    def style_sector_col(val):
        return f"color: #4ECDC4; font-size: 0.82rem" if val else f"color: {GREY}"

    styled_trades = (
        df_trades.style
        .format({
            "Qty":         lambda x: f"{x:,.0f}",
            "Price (₹)":   lambda x: f"₹{x:,.2f}",
            "Charges (₹)": lambda x: f"₹{x:,.2f}" if x else "—",
            "Value (₹)":   lambda x: f"₹{x:,.0f}",
            "Broker":      lambda x: x if x else "—",
            "Sector":      lambda x: x if x else "—",
        })
        .map(style_action,    subset=["Action"])
        .map(style_broker_sec, subset=["Broker"])
        .map(style_sector_col, subset=["Sector"])
        .hide(axis="index")
    )
    st.dataframe(styled_trades, width='stretch', height=320)
else:
    st.info("No transactions found for this scrip.")


# ── What-if XIRR calculator ───────────────────────────────────────────────────
section_header("What-If Calculator", "How does XIRR change at a different price?")

wi_col1, wi_col2 = st.columns([1, 2])
with wi_col1:
    what_if_price = st.number_input(
        "Hypothetical LMP (₹)",
        min_value=0.01,
        value=float(lmp) if lmp else 100.0,
        step=10.0,
        format="%.2f",
    )

if trades and what_if_price:
    wi_result = compute_xirr(trades, what_if_price, date.today().isoformat())
    wi_xirr   = wi_result.get("xirr_pct")
    wi_val    = wi_result.get("current_value", 0)

    with wi_col2:
        wc1, wc2, wc3 = st.columns(3)
        with wc1:
            metric_card("XIRR at New Price", fmt_pct(wi_xirr), colour=xirr_colour(wi_xirr))
        with wc2:
            metric_card("New Current Value", fmt_inr(wi_val), colour=TEAL)
        with wc3:
            delta = (wi_xirr or 0) - (xirr or 0)
            metric_card("XIRR Change", fmt_pct(delta), colour=xirr_colour(delta))
