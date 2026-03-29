"""
pages/4_analytics.py
Portfolio analytics: XIRR rankings, holding period analysis,
dividend income calendar, winners/losers breakdown.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
from collections import defaultdict

from utils.data import load_all_latest_xirr, load_all_trades, compute_xirr as _compute_xirr
from utils.ui import (
    fmt_inr, fmt_pct, fmt_qty, section_header, metric_card, xirr_colour,
    xirr_bar_chart, holding_period_scatter,
    TEAL, RED, GREY, BORDER, CARD_BG, CYAN, PURPLE, ORANGE,
    ACTION_COLOURS, LAYOUT_DEFAULTS,
)

with st.sidebar:
    st.markdown('<div style="font-size:1.3rem;font-weight:800;color:#00A88A;padding:16px 0 24px">📈 XIRR Tracker</div>', unsafe_allow_html=True)
    st.markdown("---")
    if st.button("🔄  Refresh", use_container_width=True):
        st.cache_data.clear(); st.rerun()


st.markdown("""
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:4px">Analytics</h1>
<div style="color:#6B7280;margin-bottom:24px">Deep-dive into portfolio performance</div>
""", unsafe_allow_html=True)

# ── Load ──────────────────────────────────────────────────────────────────────
# Drive from trades table so new scrips appear immediately without Lambda.
with st.spinner("Loading analytics…"):
    try:
        all_trades = load_all_trades()
    except Exception as e:
        st.error(f"DynamoDB error: {e}")
        st.stop()

if not all_trades:
    st.warning("No trade records found. Upload trades using the Bulk Upload page.")
    st.stop()

# Load snapshots for LMP only
try:
    all_snapshots = load_all_latest_xirr()
except Exception:
    all_snapshots = []

_snap_map = {s.get("symbol", ""): s for s in all_snapshots if s.get("type") == "SCRIP"}

# Build scrips list from raw trades — always accurate
scrips = []
today_str = date.today().isoformat()
for sym, trades in all_trades.items():
    snap    = _snap_map.get(sym, {})
    lmp_val = float(snap.get("lmp", 0))
    if trades and lmp_val > 0:
        c = _compute_xirr(trades, lmp_val, today_str)
        scrips.append({
            "symbol":          sym,
            "xirr_pct":        c.get("xirr_pct"),
            "current_value":   c.get("current_value",   0),
            "total_invested":  c.get("total_invested",  0),
            "total_realised":  c.get("total_realised",  0),
            "total_dividends": c.get("total_dividends", 0),
            "holdings_qty":    c.get("holdings_qty",    0),
            "bonus_shares":    c.get("bonus_shares",    0),
            "rights_shares":   c.get("rights_shares",   0),
            "lmp":             lmp_val,
            "as_of":           snap.get("as_of", ""),
            "type":            "SCRIP",
        })
    else:
        # No LMP yet — include with trade-derived fields, XIRR/value = None
        c = _compute_xirr(trades, 0.01, today_str) if trades else {}
        scrips.append({
            "symbol":          sym,
            "xirr_pct":        None,
            "current_value":   None,
            "total_invested":  c.get("total_invested",  0),
            "total_realised":  c.get("total_realised",  0),
            "total_dividends": c.get("total_dividends", 0),
            "holdings_qty":    c.get("holdings_qty",    0),
            "bonus_shares":    c.get("bonus_shares",    0),
            "rights_shares":   c.get("rights_shares",   0),
            "lmp":             0,
            "as_of":           "Pending Lambda run",
            "type":            "SCRIP",
        })

if not scrips:
    st.warning("No data found.")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🏆  XIRR Rankings",
    "⏳  Holding Period",
    "💰  Dividend Income",
    "📉  Winners & Losers",
])


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1: XIRR Rankings
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    section_header("XIRR Rankings", "Sorted by annualised return")

    top_n = st.slider("Number of scrips to show", 5, min(50, len(scrips)), 20)

    col_top, col_bot = st.columns(2)

    with col_top:
        st.markdown(f"**🟢 Top {top_n // 2} Performers**")
        df_scrips = pd.DataFrame(scrips)
        df_scrips["xirr_pct"] = pd.to_numeric(df_scrips.get("xirr_pct", None), errors="coerce")
        top = df_scrips.nlargest(top_n // 2, "xirr_pct")[["symbol", "xirr_pct", "current_value"]]

        fig_top = go.Figure(go.Bar(
            x=top["xirr_pct"], y=top["symbol"], orientation="h",
            marker_color=TEAL,
            text=top["xirr_pct"].map(lambda x: f"{x:+.1f}%"),
            textposition="outside",
            hovertemplate="<b>%{y}</b>: %{x:.2f}%<extra></extra>",
        ))
        fig_top.add_vline(x=0, line_color=BORDER)
        fig_top.update_layout(
            **LAYOUT_DEFAULTS,
            height=max(280, (top_n // 2) * 30),
            showlegend=False, xaxis_title="XIRR %", yaxis_title="",
            margin=dict(l=8, r=40, t=8, b=8),
        )
        st.plotly_chart(fig_top, use_container_width=True, config={"displayModeBar": False})

    with col_bot:
        st.markdown(f"**🔴 Bottom {top_n // 2} Performers**")
        bot = df_scrips.nsmallest(top_n // 2, "xirr_pct")[["symbol", "xirr_pct", "current_value"]]
        bot = bot.sort_values("xirr_pct", ascending=False)

        fig_bot = go.Figure(go.Bar(
            x=bot["xirr_pct"], y=bot["symbol"], orientation="h",
            marker_color=RED,
            text=bot["xirr_pct"].map(lambda x: f"{x:+.1f}%"),
            textposition="outside",
            hovertemplate="<b>%{y}</b>: %{x:.2f}%<extra></extra>",
        ))
        fig_bot.add_vline(x=0, line_color=BORDER)
        fig_bot.update_layout(
            **LAYOUT_DEFAULTS,
            height=max(280, (top_n // 2) * 30),
            showlegend=False, xaxis_title="XIRR %", yaxis_title="",
            margin=dict(l=8, r=40, t=8, b=8),
        )
        st.plotly_chart(fig_bot, use_container_width=True, config={"displayModeBar": False})

    # Full ranked table
    section_header("Full Rankings Table")
    ranked = df_scrips[["symbol", "xirr_pct", "current_value", "total_invested",
                          "total_dividends", "holdings_qty", "lmp"]].copy()
    # rank() returns NaN for rows where xirr_pct is NaN — fill before casting
    ranked["rank"] = ranked["xirr_pct"].rank(ascending=False).fillna(0).astype(int)
    ranked = ranked.sort_values("rank")

    def colour_xirr_cell(val):
        if pd.isna(val): return f"color: {GREY}"
        return f"color: {TEAL}" if val >= 0 else f"color: {RED}"

    st.dataframe(
        ranked.style
        .format({
            "xirr_pct":       lambda x: f"{x:+.2f}%" if not pd.isna(x) else "—",
            "current_value":  lambda x: fmt_inr(x),
            "total_invested": lambda x: fmt_inr(x),
            "total_dividends":lambda x: fmt_inr(x),
            "holdings_qty":   lambda x: fmt_qty(x) if x is not None else "—",
            "lmp":            lambda x: f"₹{x:,.2f}",
        })
        .applymap(colour_xirr_cell, subset=["xirr_pct"])
        .hide(axis="index"),
        use_container_width=True, height=420,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2: Holding Period Analysis
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    section_header("Holding Period vs XIRR",
                   "Bubble size = current value · Colour = XIRR direction")

    fig_scatter = holding_period_scatter(scrips, all_trades)
    if not fig_scatter.data:
        st.info("No data available for scatter chart.")
    else:
        st.plotly_chart(fig_scatter, use_container_width=True, config={"displayModeBar": False})

    # Holding period buckets
    section_header("Holdings by Tenure Bucket")
    today = date.today()
    buckets = defaultdict(list)

    for s in scrips:
        sym    = s.get("symbol", "")
        trades = all_trades.get(sym, [])
        if not trades:
            continue
        first  = min(t["trade_date"] for t in trades)
        days   = (today - date.fromisoformat(first)).days
        bucket = (
            "< 1 year"   if days < 365   else
            "1–2 years"  if days < 730   else
            "2–3 years"  if days < 1095  else
            "> 3 years"
        )
        buckets[bucket].append({
            "symbol":     sym,
            "days":       days,
            "xirr_pct":   float(s.get("xirr_pct") or 0),
            "value":      float(s.get("current_value") or 0),
        })

    bucket_order = ["< 1 year", "1–2 years", "2–3 years", "> 3 years"]
    bucket_rows  = []
    for b in bucket_order:
        items = buckets.get(b, [])
        if not items:
            continue
        avg_xirr = sum(i["xirr_pct"] for i in items) / len(items)
        total_val = sum(i["value"] for i in items)
        bucket_rows.append({
            "Tenure":        b,
            "Scrips":        len(items),
            "Avg XIRR %":   avg_xirr,
            "Total Value":   total_val,
        })

    if bucket_rows:
        bdf = pd.DataFrame(bucket_rows)
        fig_bucket = go.Figure(go.Bar(
            x=bdf["Tenure"],
            y=bdf["Avg XIRR %"],
            marker_color=[TEAL if x >= 0 else RED for x in bdf["Avg XIRR %"]],
            text=bdf["Avg XIRR %"].map(lambda x: f"{x:+.1f}%"),
            textposition="outside",
            customdata=bdf[["Scrips", "Total Value"]].values,
            hovertemplate=(
                "<b>%{x}</b><br>Avg XIRR: %{y:.2f}%<br>"
                "Scrips: %{customdata[0]}<br>Value: ₹%{customdata[1]:,.0f}<extra></extra>"
            ),
        ))
        fig_bucket.add_hline(y=0, line_color=BORDER)
        fig_bucket.update_layout(
            **LAYOUT_DEFAULTS,
            height=300, showlegend=False,
            title=dict(text="Average XIRR by Holding Period Bucket", font=dict(size=14)),
            yaxis_title="Avg XIRR %",
        )
        st.plotly_chart(fig_bucket, use_container_width=True, config={"displayModeBar": False})


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3: Dividend Income
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    section_header("Dividend Income Tracker", "All dividends received across the portfolio")

    div_rows = []
    for symbol, trades in all_trades.items():
        for t in trades:
            if t.get("action", "").upper() == "DIVIDEND":
                qty   = float(t.get("qty", 0))
                price = float(t.get("price", 0))
                div_rows.append({
                    "Date":       t.get("trade_date", ""),
                    "Symbol":     symbol,
                    "Shares":     qty,
                    "₹/Share":    price,
                    "Total (₹)":  qty * price,
                    "Notes":      t.get("notes", ""),
                })

    if not div_rows:
        st.info("No dividend records found. Add DIVIDEND actions to track income.")
    else:
        df_div = pd.DataFrame(div_rows).sort_values("Date", ascending=False)
        df_div["Year"]    = df_div["Date"].str[:4]
        df_div["Quarter"] = pd.to_datetime(df_div["Date"]).dt.quarter.map(
            {1: "Q1 (Jan-Mar)", 2: "Q2 (Apr-Jun)", 3: "Q3 (Jul-Sep)", 4: "Q4 (Oct-Dec)"}
        )

        # KPIs
        total_div    = df_div["Total (₹)"].sum()
        this_fy_start = str(date(date.today().year if date.today().month >= 4 else date.today().year - 1, 4, 1))
        fy_div       = df_div[df_div["Date"] >= this_fy_start]["Total (₹)"].sum()
        top_payer    = df_div.groupby("Symbol")["Total (₹)"].sum().idxmax()

        d1, d2, d3, d4 = st.columns(4)
        with d1: metric_card("All-Time Dividends", fmt_inr(total_div), colour=CYAN)
        with d2: metric_card("This FY",            fmt_inr(fy_div),    colour=TEAL)
        with d3: metric_card("Payments",           f"{len(df_div):,}", colour=GREY)
        with d4: metric_card("Top Payer",          top_payer,          colour=PURPLE)

        # Annual bar chart
        annual = df_div.groupby("Year")["Total (₹)"].sum().reset_index().sort_values("Year")
        fig_ann = go.Figure(go.Bar(
            x=annual["Year"], y=annual["Total (₹)"],
            marker_color=CYAN,
            text=annual["Total (₹)"].map(fmt_inr),
            textposition="outside",
            hovertemplate="<b>%{x}</b>: ₹%{y:,.0f}<extra></extra>",
        ))
        fig_ann.update_layout(
            **LAYOUT_DEFAULTS,
            height=280, showlegend=False,
            title=dict(text="Annual Dividend Income", font=dict(size=14)),
            yaxis_title="₹",
        )
        st.plotly_chart(fig_ann, use_container_width=True, config={"displayModeBar": False})

        # Per-scrip breakdown
        scrip_div = (
            df_div.groupby("Symbol")["Total (₹)"].sum()
            .sort_values(ascending=False).reset_index()
        )
        fig_scrip = go.Figure(go.Bar(
            x=scrip_div["Symbol"], y=scrip_div["Total (₹)"],
            marker_color=CYAN,
            text=scrip_div["Total (₹)"].map(fmt_inr),
            textposition="outside",
            hovertemplate="<b>%{x}</b>: ₹%{y:,.0f}<extra></extra>",
        ))
        fig_scrip.update_layout(
            **LAYOUT_DEFAULTS,
            height=300, showlegend=False,
            title=dict(text="Dividends by Scrip", font=dict(size=14)),
            yaxis_title="₹",
        )
        st.plotly_chart(fig_scrip, use_container_width=True, config={"displayModeBar": False})

        # Full table
        section_header("Dividend Log")
        st.dataframe(
            df_div[["Date", "Symbol", "Shares", "₹/Share", "Total (₹)", "Notes"]]
            .style.format({
                "Shares":    lambda x: f"{x:,.0f}",
                "₹/Share":   lambda x: f"₹{x:,.4f}",
                "Total (₹)": lambda x: f"₹{x:,.2f}",
            })
            .hide(axis="index"),
            use_container_width=True, height=360,
        )

        st.download_button(
            "⬇️ Export Dividend Log",
            data=df_div.to_csv(index=False),
            file_name=f"dividends_{date.today()}.csv",
            mime="text/csv",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Tab 4: Winners & Losers
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    section_header("Winners & Losers Analysis")

    df_wl = pd.DataFrame(scrips)
    df_wl["xirr_pct"]      = pd.to_numeric(df_wl.get("xirr_pct"), errors="coerce")
    df_wl["current_value"]  = pd.to_numeric(df_wl.get("current_value", 0), errors="coerce").fillna(0)
    df_wl["total_invested"] = pd.to_numeric(df_wl.get("total_invested", 0), errors="coerce").fillna(0)
    df_wl["unrealised_pnl"] = df_wl["current_value"] - df_wl["total_invested"]

    winners = df_wl[df_wl["xirr_pct"] >= 0].sort_values("xirr_pct", ascending=False)
    losers  = df_wl[df_wl["xirr_pct"] <  0].sort_values("xirr_pct")

    w1, w2, w3, w4 = st.columns(4)
    with w1: metric_card("Winners",       f"{len(winners)}",  colour=TEAL)
    with w2: metric_card("Losers",        f"{len(losers)}",   colour=RED)
    with w3: metric_card("Best XIRR",     fmt_pct(winners["xirr_pct"].max() if not winners.empty else None), colour=TEAL)
    with w4: metric_card("Worst XIRR",    fmt_pct(losers["xirr_pct"].min()  if not losers.empty  else None), colour=RED)

    # Unrealised P&L chart
    section_header("Unrealised P&L by Scrip")
    df_pnl = df_wl.sort_values("unrealised_pnl")
    fig_pnl = go.Figure(go.Bar(
        x=df_pnl["unrealised_pnl"],
        y=df_pnl["symbol"],
        orientation="h",
        marker_color=[TEAL if x >= 0 else RED for x in df_pnl["unrealised_pnl"]],
        text=df_pnl["unrealised_pnl"].map(fmt_inr),
        textposition="outside",
        hovertemplate="<b>%{y}</b>: ₹%{x:,.0f}<extra></extra>",
    ))
    fig_pnl.add_vline(x=0, line_color=BORDER)
    fig_pnl.update_layout(
        **LAYOUT_DEFAULTS,
        height=max(400, len(df_pnl) * 22),
        showlegend=False, xaxis_title="Unrealised P&L (₹)", yaxis_title="",
        margin=dict(l=8, r=60, t=40, b=8),
    )
    st.plotly_chart(fig_pnl, use_container_width=True, config={"displayModeBar": False})

    # Value concentration
    section_header("Portfolio Concentration", "Share of total current value")
    top15 = df_wl.nlargest(15, "current_value")
    others_val = df_wl["current_value"].sum() - top15["current_value"].sum()
    pie_labels = list(top15["symbol"]) + (["Others"] if others_val > 0 else [])
    pie_values = list(top15["current_value"]) + ([others_val] if others_val > 0 else [])

    fig_pie = go.Figure(go.Pie(
        labels=pie_labels, values=pie_values,
        hole=0.45,
        marker=dict(colors=px.colors.qualitative.Set3),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>₹%{value:,.0f} (%{percent})<extra></extra>",
    ))
    fig_pie.update_layout(
        **LAYOUT_DEFAULTS,
        height=420,
        title=dict(text="Top 15 Holdings by Value", font=dict(size=14)),
        showlegend=False,
    )
    st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})
