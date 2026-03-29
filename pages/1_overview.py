"""
pages/1_overview.py  —  Portfolio Overview
Filters (broker / sector / XIRR / search) appear first.
All KPIs, charts, treemap, and the Recalculate button respond to the filtered set.
"""
import streamlit as st
import pandas as pd
from datetime import date

from utils.data import (
    load_all_latest_xirr,
    load_xirr_history,
    load_all_trades,
    test_connection,
    get_aws_config,
    trigger_lambda,
    compute_xirr,
    fetch_face_values_yfinance,
)
from utils.ui import (
    fmt_inr, fmt_pct, fmt_qty, xirr_colour,
    metric_card, section_header,
    xirr_history_chart, portfolio_treemap,
    TEAL, RED, GREY, BORDER, CARD_BG, CYAN,
)

# ── Connection check ──────────────────────────────────────────────────────────
_ok, _msg = test_connection()
if not _ok:
    st.error("### Cannot connect to DynamoDB")
    st.markdown(f"> **{_msg}**")
    with st.expander("Troubleshooting guide", expanded=True):
        try:
            cfg = get_aws_config()
            st.markdown("**Secrets detected (keys present):**")
            st.code(
                "[aws]\n"
                f"access_key_id     = \"{'*' * 16}{cfg['access_key_id'][-4:]}\"\n"
                f"secret_access_key = \"{'*' * 36}{cfg['secret_access_key'][-4:]}\"\n"
                f"region            = \"{cfg['region']}\"\n"
                "\n[dynamodb]\n"
                f"trades_table = \"{cfg['trades_table']}\"\n"
                f"xirr_table   = \"{cfg['xirr_table']}\"",
                language="toml",
            )
        except KeyError as missing:
            st.error(f"Missing secret key: **{missing}**")
        st.markdown(
            "**Common causes:**\n"
            "- Wrong key names: must be exactly `access_key_id`, `secret_access_key`, `region`\n"
            "- Wrong section headers: must be `[aws]` and `[dynamodb]` (case-sensitive)\n"
            "- Table name mismatch: check DynamoDB console for exact table names\n"
            "- IAM permissions: user needs `dynamodb:DescribeTable`, `Query`, `Scan`, `GetItem`, `PutItem`\n"
        )
        if st.button("Retry connection"):
            st.cache_data.clear()
            st.rerun()
    st.stop()

# ── Load raw data ─────────────────────────────────────────────────────────────
# Drive the symbol list from the TRADES table — every scrip with at least one
# trade record appears here, even before the Lambda has run.
# Snapshots are loaded separately and used only for LMP and XIRR history.
with st.spinner("Loading portfolio…"):
    try:
        _all_trades_map = load_all_trades()
    except Exception as e:
        st.error(f"DynamoDB read failed: `{type(e).__name__}: {e}`")
        st.stop()

if not _all_trades_map:
    st.warning("No trade records found. Upload trades using the Bulk Upload page.")
    st.stop()

# Load XIRR snapshots — used only for LMP (last market price) and XIRR history.
# Scrips without a snapshot yet are shown with LMP = 0 and XIRR = —.
try:
    all_snapshots = load_all_latest_xirr()
except Exception:
    all_snapshots = []

# Build a quick lookup: symbol → snapshot
_snapshot_map: dict = {s.get("symbol", ""): s
                       for s in all_snapshots if s.get("type") == "SCRIP"}

# all_scrips is now driven by trades, not snapshots
all_scrips_syms = sorted(_all_trades_map.keys())

def _tags(sym: str, field: str) -> set[str]:
    return {r.get(field, "").strip() for r in _all_trades_map.get(sym, [])
            if r.get(field, "").strip()}

# Fetch face values via yfinance (Streamlit Cloud IPs not blocked — cached 1h)
_fv_map: dict = {}
try:
    _fv_map = fetch_face_values_yfinance(all_scrips_syms)
except Exception:
    pass

# Build full dataframe — all numeric fields computed from raw trades.
# LMP comes from the snapshot (set by the last Lambda run).
# Snapshot XIRR % is also used for display so the table matches the Lambda output.
from utils.data import compute_xirr as _compute_xirr

all_rows = []
for sym in all_scrips_syms:
    snap           = _snapshot_map.get(sym, {})   # empty dict if no snapshot yet
    lmp_val        = float(snap.get("lmp", 0))
    brokers        = " | ".join(sorted(_tags(sym, "broker")))
    sectors        = " | ".join(sorted(_tags(sym, "sector")))
    trades_for_sym = _all_trades_map.get(sym, [])

    if trades_for_sym and lmp_val > 0:
        # Full compute from raw trades — always accurate
        _c = _compute_xirr(trades_for_sym, lmp_val, date.today().isoformat())
        xirr_pct  = _c.get("xirr_pct")
        cur_val   = _c.get("current_value",   0)
        invested  = _c.get("total_invested",  0)
        realised  = _c.get("total_realised",  0)
        dividends = _c.get("total_dividends", 0)
        holdings  = _c.get("holdings_qty",    0)
        bonus     = _c.get("bonus_shares",    0)
        rights    = _c.get("rights_shares",   0)
    elif trades_for_sym:
        # Trades exist but no LMP yet — compute invested/holdings from trades,
        # show XIRR and current value as None until Lambda runs
        _c = _compute_xirr(trades_for_sym, 0.01, date.today().isoformat())
        xirr_pct  = None          # can't compute without a real price
        cur_val   = None          # unknown without LMP
        invested  = _c.get("total_invested",  0)
        realised  = _c.get("total_realised",  0)
        dividends = _c.get("total_dividends", 0)
        holdings  = _c.get("holdings_qty",    0)
        bonus     = _c.get("bonus_shares",    0)
        rights    = _c.get("rights_shares",   0)
    else:
        xirr_pct  = None
        cur_val   = 0.0
        invested  = 0.0
        realised  = 0.0
        dividends = 0.0
        holdings  = 0.0
        bonus     = 0.0
        rights    = 0.0

    # Face value priority:
    # 1. SPLIT trade record (user-specified, most accurate)
    # 2. yfinance lookup (Streamlit Cloud, not blocked)
    # 3. Lambda snapshot (Lambda NSE fetch blocked, often None)
    fv_trade = _c.get("face_value") if trades_for_sym else None
    fv_yf    = _fv_map.get(sym)
    fv_snap  = snap.get("face_value")
    face_val = fv_trade or fv_yf or fv_snap

    all_rows.append({
        "Symbol":        sym,
        "XIRR %":        xirr_pct,
        "Current Value": cur_val,
        "Invested":      invested,
        "Realised":      realised,
        "Dividends":     dividends,
        "Holdings":      holdings,
        "Face Value (₹)": face_val,
        "LMP (₹)":       lmp_val if lmp_val > 0 else None,
        "Bonus Shares":  bonus,
        "Rights Shares": rights,
        "As Of":         snap.get("as_of", "Pending Lambda run"),
        "Broker":        brokers,
        "Sector":        sectors,
        "_snap":         snap,
    })

df_all = pd.DataFrame(all_rows)

# ── Page title ────────────────────────────────────────────────────────────────
st.markdown("""
<h1 style="font-size:1.8rem;font-weight:800;margin:0 0 4px 0">Portfolio Overview</h1>
<div style="color:#6B7280;font-size:0.9rem;margin-bottom:20px">
    All figures as of latest market close · Apply filters to narrow the view
</div>
""", unsafe_allow_html=True)

# ── Filters — BEFORE everything else ─────────────────────────────────────────
st.markdown(
    f'<div style="background:{CARD_BG};border:1px solid {BORDER};'
    f'border-radius:10px;padding:14px 18px;margin-bottom:20px">',
    unsafe_allow_html=True,
)

fcol1, fcol2, fcol3, fcol4, fcol5 = st.columns([2, 1, 1, 1, 1])

with fcol1:
    _all_symbols = sorted(df_all["Symbol"].dropna().unique().tolist())
    search = st.multiselect(
        "🔍 Symbol",
        options=_all_symbols,
        default=[],
        placeholder="All scrips",
    )

with fcol2:
    show = st.selectbox("XIRR Filter", ["All", "Positive XIRR", "Negative XIRR"])

with fcol3:
    sort_by = st.selectbox("Sort By", ["XIRR %", "Current Value", "Invested", "Dividends"])

with fcol4:
    _broker_opts = sorted({b for b in df_all["Broker"].str.split(" | ").explode() if b})
    broker_filter = st.selectbox("Broker", ["All"] + _broker_opts)

with fcol5:
    _sector_opts = sorted({s for s in df_all["Sector"].str.split(" | ").explode() if s})
    sector_filter = st.selectbox("Sector", ["All"] + _sector_opts)

st.markdown("</div>", unsafe_allow_html=True)

# ── Apply filters ─────────────────────────────────────────────────────────────
df = df_all.copy()

if search:
    df = df[df["Symbol"].isin(search)]
if show == "Positive XIRR":
    df = df[df["XIRR %"].apply(lambda x: (x or 0) >= 0)]
elif show == "Negative XIRR":
    df = df[df["XIRR %"].apply(lambda x: (x or 0) < 0)]
if broker_filter != "All":
    df = df[df["Broker"].str.contains(broker_filter, na=False)]
if sector_filter != "All":
    df = df[df["Sector"].str.contains(sector_filter, na=False)]

df = df.sort_values(sort_by, ascending=(sort_by == "Symbol"))

# Is any filter active?
is_filtered = bool(search or show != "All" or broker_filter != "All" or sector_filter != "All")
# search is now a list — rewrite filter_parts accordingly
filtered_symbols = df["Symbol"].tolist()
filtered_snaps   = df["_snap"].tolist()

# Build filter label for display
filter_parts = []
if broker_filter != "All": filter_parts.append(f"Broker: {broker_filter}")
if sector_filter != "All": filter_parts.append(f"Sector: {sector_filter}")
if show != "All":           filter_parts.append(show)
if search:                  filter_parts.append(", ".join(search))
filter_label = " · ".join(filter_parts) if filter_parts else "Full Portfolio"

# ── Filtered KPIs — always derived from raw trades, not snapshots ─────────────
# Snapshots can be stale or incomplete. Raw trades are always the source of truth.
from utils.data import compute_xirr as _compute_xirr

f_count   = len(filtered_symbols)
f_value   = 0.0
f_invest  = 0.0
f_divs    = 0.0
f_real    = 0.0
f_holdings = 0.0
f_pos     = 0

for sym in filtered_symbols:
    trades = _all_trades_map.get(sym, [])
    lmp    = float(next(
        (s.get("lmp", 0) for s in filtered_snaps if s.get("symbol") == sym), 0
    ))
    if not trades or lmp <= 0:
        continue
    r = _compute_xirr(trades, lmp, date.today().isoformat())
    f_value    += r.get("current_value",   0) or 0
    f_invest   += r.get("total_invested",  0) or 0
    f_real     += r.get("total_realised",  0) or 0
    f_divs     += r.get("total_dividends", 0) or 0
    f_holdings += r.get("holdings_qty",    0) or 0
    if (r.get("xirr_pct") or 0) >= 0:
        f_pos += 1

f_returns = f_value - f_invest + f_real

# Blended XIRR across all filtered symbols (merge all cashflows)
f_xirr: float | None = None
if filtered_symbols and _all_trades_map:
    try:
        from utils.data import _xirr_newton, _parse_date
        from datetime import date as _date
        as_of        = _date.today()
        combined_cfs = []
        for sym in filtered_symbols:
            trades = _all_trades_map.get(sym, [])
            lmp    = float(next(
                (s.get("lmp", 0) for s in filtered_snaps if s.get("symbol") == sym), 0
            ))
            if not trades or lmp <= 0:
                continue
            holdings = 0.0
            for t in sorted(trades, key=lambda x: x["trade_date"]):
                d       = _parse_date(t["trade_date"])
                qty     = float(t["qty"])
                price   = float(t["price"])
                charges = float(t.get("charges", 0))
                action  = t["action"].upper()
                if action == "BUY":
                    combined_cfs.append((d, -(qty * price + charges)))
                    holdings += qty
                elif action == "SELL":
                    combined_cfs.append((d, qty * price - charges))
                    holdings -= qty
                elif action == "DIVIDEND":
                    combined_cfs.append((d, qty * price))
                elif action == "BONUS":
                    holdings += qty
                elif action == "RIGHTS":
                    combined_cfs.append((d, -(qty * price + charges)))
                    holdings += qty
            if holdings > 0:
                combined_cfs.append((as_of, holdings * lmp))
        if combined_cfs:
            rate   = _xirr_newton(combined_cfs)
            f_xirr = round(rate * 100, 2) if rate is not None else None
    except Exception:
        f_xirr = None

# ── Header row: filter badge + Recalculate button ────────────────────────────
hdr_col, btn_col = st.columns([3, 1])
with hdr_col:
    if is_filtered:
        st.markdown(
            f'<div style="background:{CYAN}15;border:1px solid {CYAN}40;'
            f'border-radius:8px;padding:6px 14px;display:inline-block;'
            f'color:{CYAN};font-size:0.85rem;margin-bottom:12px">'
            f'🔎 Filtered view: <strong>{filter_label}</strong> '
            f'· {f_count} of {len(all_scrips_syms)} scrips</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="color:{GREY};font-size:0.85rem;margin-bottom:12px">'
            f'Showing full portfolio · {f_count} scrips</div>',
            unsafe_allow_html=True,
        )

with btn_col:
    recalc_label = (
        f"⚡ Recalculate ({f_count} scrips)"
        if is_filtered else "⚡ Recalculate XIRR"
    )
    recalc_help = (
        f"Recalculates XIRR for the {f_count} filtered scrips only."
        if is_filtered else
        "Recalculates XIRR for all scrips in the portfolio."
    )
    if st.button(recalc_label, type="primary", use_container_width=True, help=recalc_help):
        with st.spinner(
            f"Fetching prices and recalculating {f_count} scrips…"
            if is_filtered else "Fetching prices and recalculating all scrips…"
        ):
            ok, msg = trigger_lambda(
                symbols=filtered_symbols if is_filtered else None
            )
        if ok:
            st.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.error(msg)

# ── KPI strip ─────────────────────────────────────────────────────────────────
cols = st.columns(6)
with cols[0]:
    metric_card("XIRR" + (" (filtered)" if is_filtered else ""),
                fmt_pct(f_xirr), colour=xirr_colour(f_xirr))
with cols[1]:
    metric_card("Current Value",    fmt_inr(f_value),   colour=TEAL)
with cols[2]:
    metric_card("Total Invested",   fmt_inr(f_invest),  colour="#6B7280")
with cols[3]:
    metric_card("Total Returns",    fmt_inr(f_returns), colour=xirr_colour(f_returns))
with cols[4]:
    metric_card("Dividends",        fmt_inr(f_divs),    colour="#4ECDC4")
with cols[5]:
    metric_card("Scrips",           f"{f_pos}/{f_count} ↑", colour=TEAL)

# ── Treemap + XIRR trend ──────────────────────────────────────────────────────
st.markdown("<div style='height:20px'/>", unsafe_allow_html=True)
left, right = st.columns([3, 2])

with left:
    treemap_title = (
        f"Holdings Map · {filter_label}" if is_filtered else "Holdings Map"
    )
    section_header(treemap_title, "Sized by current value · Colour = XIRR")
    fig_tree = portfolio_treemap(filtered_snaps)
    st.plotly_chart(fig_tree, use_container_width=True, config={"displayModeBar": False})

with right:
    section_header("Portfolio XIRR Trend", "Last 90 daily snapshots")
    hist = load_xirr_history(None, limit=90)
    if hist:
        st.plotly_chart(
            xirr_history_chart(hist, "Portfolio XIRR %"),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    else:
        st.info("No XIRR history yet. History builds up daily after the Lambda runs.")

# ── Scrip table ───────────────────────────────────────────────────────────────
section_header(
    f"{'Filtered' if is_filtered else 'All'} Scrips",
    f"{f_count} position{'s' if f_count != 1 else ''}"
    + (f" · {filter_label}" if is_filtered else "")
)

def colour_xirr(val):
    if val is None or pd.isna(val): return f"color: {GREY}"
    return f"color: {TEAL}" if val >= 0 else f"color: {RED}"

display_df = df.drop(columns=["_snap"])

styled = (
    display_df.style
    .format({
        "XIRR %":        lambda x: f"{x:+.2f}%" if x is not None and not pd.isna(x) else "—",
        "Current Value": lambda x: fmt_inr(x),
        "Invested":      lambda x: fmt_inr(x),
        "Dividends":     lambda x: fmt_inr(x),
        "LMP (₹)":       lambda x: f"₹{x:,.2f}",
        "Holdings":      lambda x: fmt_qty(x) if pd.notna(x) else "—",
        "Bonus Shares":  lambda x: fmt_qty(x) if x and pd.notna(x) else "—",
        "Rights Shares": lambda x: fmt_qty(x) if x and pd.notna(x) else "—",
        "Broker":        lambda x: x if x else "—",
        "Sector":        lambda x: x if x else "—",
        "Realised":      lambda x: fmt_inr(x),
        "Face Value (₹)": lambda x: f"₹{x:,.2f}" if x else "—",
    })
    .applymap(colour_xirr, subset=["XIRR %"])
    .set_properties(**{"background-color": CARD_BG, "border-color": BORDER})
    .hide(axis="index")
)

st.dataframe(styled, use_container_width=True, height=420)

# Download
csv = display_df.to_csv(index=False)
st.download_button(
    "⬇️ Download as CSV",
    data=csv,
    file_name=f"portfolio_{filter_label.replace(' ', '_').replace(':', '')}_{date.today()}.csv",
    mime="text/csv",
)
