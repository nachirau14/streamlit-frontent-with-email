"""
utils/ui.py
Shared formatting helpers and reusable UI components.
"""
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Any

# ── Colour palette (light theme) ────────────────────────────────────────────

TEAL      = "#00A88A"   # slightly deeper green-teal — readable on white
RED       = "#E53E3E"   # crisp red
PURPLE    = "#7C3AED"   # deep purple
ORANGE    = "#D97706"   # amber
CYAN      = "#0891B2"   # teal-blue
GREY      = "#6B7280"   # neutral mid-grey — same in both themes
BG        = "#FFFFFF"   # page background
CARD_BG   = "#F4F6F8"   # subtle off-white card
BORDER    = "#E2E8F0"   # soft grey border

ACTION_COLOURS = {
    "BUY":      TEAL,
    "SELL":     RED,
    "DIVIDEND": CYAN,
    "BONUS":    PURPLE,
    "RIGHTS":   ORANGE,
}

# Flat dict spread into update_layout() — no go.Layout wrapper, no margin key.
# Each chart sets its own margin so there are never duplicate keyword args.
LAYOUT_DEFAULTS = dict(
    paper_bgcolor=BG,
    plot_bgcolor=CARD_BG,
    font=dict(color="#111827", family="Inter, sans-serif"),
    xaxis=dict(gridcolor=BORDER, zerolinecolor="#CBD5E0"),
    yaxis=dict(gridcolor=BORDER, zerolinecolor="#CBD5E0"),
    # legend intentionally excluded — each chart sets its own or uses showlegend=False
)

# Keep PLOTLY_TEMPLATE as an alias so page files that import it still work
PLOTLY_TEMPLATE = {"layout_defaults": LAYOUT_DEFAULTS}


# ── Number formatting ─────────────────────────────────────────────────────────

def fmt_inr(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1_00_00_000:   # ≥ 1 Cr
        return f"₹{value/1_00_00_000:.2f} Cr"
    if abs(value) >= 1_00_000:      # ≥ 1 L
        return f"₹{value/1_00_000:.2f} L"
    return f"₹{value:,.{decimals}f}"


def fmt_pct(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:+.{decimals}f}%"


def fmt_qty(value: float | None) -> str:
    import math
    if value is None:
        return "—"
    try:
        if math.isnan(float(value)):
            return "—"
        return f"{int(float(value)):,}"
    except (TypeError, ValueError):
        return "—"


def xirr_colour(xirr: float | None) -> str:
    if xirr is None:
        return GREY
    return TEAL if xirr >= 0 else RED


# ── Metric card ──────────────────────────────────────────────────────────────

def metric_card(label: str, value: str, delta: str = "", colour: str = TEAL) -> None:
    delta_html = f'<div style="font-size:0.78rem;color:{GREY};margin-top:2px">{delta}</div>' if delta else ""
    st.markdown(f"""
    <div style="
        background:{CARD_BG};
        border:1px solid {BORDER};
        border-radius:12px;
        padding:18px 20px;
        text-align:center;
        box-shadow:0 1px 3px rgba(0,0,0,0.06);
    ">
        <div style="font-size:0.78rem;color:{GREY};text-transform:uppercase;
                    letter-spacing:0.08em;margin-bottom:6px">{label}</div>
        <div style="font-size:1.55rem;font-weight:700;color:{colour}">{value}</div>
        {delta_html}
    </div>
    """, unsafe_allow_html=True)


def section_header(title: str, subtitle: str = "") -> None:
    sub = f'<div style="color:{GREY};font-size:0.85rem;margin-top:2px">{subtitle}</div>' if subtitle else ""
    st.markdown(f"""
    <div style="margin:28px 0 16px 0">
        <div style="font-size:1.25rem;font-weight:700;color:#111827">{title}</div>
        {sub}
    </div>
    """, unsafe_allow_html=True)


def action_badge(action: str) -> str:
    colour = ACTION_COLOURS.get(action.upper(), GREY)
    return (
        f'<span style="background:{colour}22;color:{colour};'
        f'border:1px solid {colour}55;border-radius:6px;'
        f'padding:2px 8px;font-size:0.75rem;font-weight:600">'
        f'{action.upper()}</span>'
    )


# ── Charts ───────────────────────────────────────────────────────────────────

def xirr_history_chart(history: list[dict], title: str = "XIRR History") -> go.Figure:
    if not history:
        return go.Figure()
    df = pd.DataFrame(history).sort_values("as_of")
    df["xirr_pct"] = pd.to_numeric(df["xirr_pct"], errors="coerce")

    colour_line = TEAL if df["xirr_pct"].iloc[-1] >= 0 else RED

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["as_of"],
        y=df["xirr_pct"],
        mode="lines",
        line=dict(color=colour_line, width=2.5),
        fill="tozeroy",
        fillcolor=("rgba(0,212,170,0.09)" if colour_line == TEAL
                   else "rgba(255,107,107,0.09)"),
        name="XIRR %",
        hovertemplate="<b>%{x}</b><br>XIRR: %{y:.2f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=BORDER, line_width=1)
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(text=title, font=dict(size=14)),
        yaxis_title="XIRR %",
        showlegend=False,
        height=280,
    )
    return fig


def portfolio_treemap(scrips: list[dict]) -> go.Figure:
    """Treemap sized by current_value, coloured by xirr_pct."""
    df = pd.DataFrame([
        s for s in scrips if s.get("type") == "SCRIP" and s.get("current_value", 0) > 0
    ])
    if df.empty:
        return go.Figure()

    df["xirr_pct"]     = pd.to_numeric(df.get("xirr_pct", 0), errors="coerce").fillna(0)
    df["current_value"] = pd.to_numeric(df["current_value"], errors="coerce").fillna(0)
    df["label"]         = df["symbol"] + "<br>" + df["xirr_pct"].map(lambda x: f"{x:+.1f}%")

    fig = go.Figure(go.Treemap(
        labels=df["label"],
        parents=[""] * len(df),
        values=df["current_value"],
        customdata=df[["symbol", "xirr_pct", "current_value"]].values,
        marker=dict(
            colors=df["xirr_pct"],
            colorscale=[[0, "#E53E3E"], [0.5, "#E2E8F0"], [1, "#00A88A"]],
            cmid=0,
            showscale=True,
            colorbar=dict(title="XIRR %", thickness=12),
        ),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "XIRR: %{customdata[1]:.2f}%<br>"
            "Value: ₹%{customdata[2]:,.0f}<extra></extra>"
        ),
        textfont=dict(size=12),
    ))
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        height=420,
        title=dict(text="Portfolio Allocation (sized by value, coloured by XIRR)", font=dict(size=14)),
        margin=dict(l=8, r=8, t=48, b=8),
    )
    return fig


def waterfall_chart(scrip: dict) -> go.Figure:
    """Cash-flow waterfall for a single scrip."""
    invested  = scrip.get("total_invested",  0)
    realised  = scrip.get("total_realised",  0)
    dividends = scrip.get("total_dividends", 0)
    current   = scrip.get("current_value",   0)
    rights    = scrip.get("rights_cost",     0)

    categories = []
    values     = []
    colours    = []

    categories.append("Invested");  values.append(-invested); colours.append(RED)
    if rights > 0:
        categories.append("Rights"); values.append(-rights); colours.append(ORANGE)
    if realised > 0:
        categories.append("Realised"); values.append(realised); colours.append(TEAL)
    if dividends > 0:
        categories.append("Dividends"); values.append(dividends); colours.append(CYAN)
    categories.append("Current Value"); values.append(current); colours.append(PURPLE)

    fig = go.Figure(go.Bar(
        x=categories,
        y=[abs(v) for v in values],
        marker_color=colours,
        text=[fmt_inr(abs(v)) for v in values],
        textposition="outside",
        hovertemplate="%{x}: ₹%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(text="Cash Flow Breakdown", font=dict(size=14)),
        showlegend=False,
        height=300,
        yaxis_title="₹",
    )
    return fig


def xirr_bar_chart(scrips: list[dict], top_n: int = 20) -> go.Figure:
    """Horizontal bar chart of XIRR % for top/bottom N scrips."""
    df = pd.DataFrame([
        s for s in scrips if s.get("type") == "SCRIP" and s.get("xirr_pct") is not None
    ])
    if df.empty:
        return go.Figure()

    df["xirr_pct"] = pd.to_numeric(df["xirr_pct"], errors="coerce")
    df = df.nlargest(top_n, "xirr_pct")
    df = df.sort_values("xirr_pct")

    colours = [TEAL if x >= 0 else RED for x in df["xirr_pct"]]

    fig = go.Figure(go.Bar(
        x=df["xirr_pct"],
        y=df["symbol"],
        orientation="h",
        marker_color=colours,
        text=df["xirr_pct"].map(lambda x: f"{x:+.1f}%"),
        textposition="outside",
        hovertemplate="<b>%{y}</b>: %{x:.2f}%<extra></extra>",
    ))
    fig.add_vline(x=0, line_color=BORDER, line_width=1)
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(text=f"Top {top_n} Scrips by XIRR", font=dict(size=14)),
        height=max(320, top_n * 26),
        xaxis_title="XIRR %",
        yaxis_title="",
        showlegend=False,
    )
    return fig


def holding_period_scatter(scrips: list[dict], all_trades: dict) -> go.Figure:
    """Scatter: holding period (days) vs XIRR %."""
    from datetime import date
    rows = []
    today = date.today()
    for s in scrips:
        if s.get("type") != "SCRIP" or s.get("xirr_pct") is None:
            continue
        sym    = s["symbol"]
        trades = all_trades.get(sym, [])
        if not trades:
            continue
        first_date = min(t["trade_date"] for t in trades)
        days = (today - date.fromisoformat(first_date)).days
        rows.append(dict(
            symbol=sym,
            days=days,
            xirr_pct=float(s["xirr_pct"]),
            current_value=float(s.get("current_value", 0)),
        ))

    if not rows:
        return go.Figure()

    df = pd.DataFrame(rows)
    fig = px.scatter(
        df, x="days", y="xirr_pct",
        size="current_value", size_max=50,
        color="xirr_pct",
        color_continuous_scale=[[0, RED], [0.5, GREY], [1, TEAL]],
        color_continuous_midpoint=0,
        hover_name="symbol",
        hover_data={"days": True, "xirr_pct": ":.2f", "current_value": ":,.0f"},
        labels={"days": "Holding Period (days)", "xirr_pct": "XIRR %", "current_value": "Value (₹)"},
    )
    fig.add_hline(y=0, line_color=BORDER, line_width=1)
    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=dict(text="Holding Period vs XIRR (bubble = portfolio weight)", font=dict(size=14)),
        height=380,
        coloraxis_showscale=False,
    )
    return fig
