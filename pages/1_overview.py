"""
pages/1_overview.py  —  Portfolio Overview
Filters (broker / sector / XIRR / search) appear first.
All KPIs, charts, treemap, and the Recalculate button respond to the filtered set.
"""
import streamlit as st
import logging
logger = logging.getLogger(__name__)
import pandas as pd
from datetime import date

from utils.data import (
    load_all_latest_xirr,
    load_xirr_history,
    load_snapshot_on_date,
    load_all_trades,
    test_connection,
    get_aws_config,
    trigger_lambda,
    compute_xirr,
    fetch_face_values_yfinance,
    get_company_names,
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
# Filter by pk prefix scrip# to exclude the PORTFOLIO row and email config items,
# but do NOT filter by type= since older snapshots may not have that field.
_snapshot_map: dict = {
    s.get("symbol", ""): s
    for s in all_snapshots
    if str(s.get("pk", "")).startswith("scrip#") and s.get("symbol")
}

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

# Fetch company names from ticker master table (cached 1h)
_name_map: dict = {}
try:
    _name_map = get_company_names(all_scrips_syms)
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

    _c = {}
    if trades_for_sym:
        try:
            _lmp_for_calc = lmp_val if lmp_val > 0 else 0.01
            _c = _compute_xirr(trades_for_sym, _lmp_for_calc, date.today().isoformat())
        except Exception as _exc:
            logger.warning("compute_xirr failed for %s: %s", sym, _exc)
            _c = {}

    if trades_for_sym and lmp_val > 0 and _c:
        xirr_pct  = _c.get("xirr_pct")
        cur_val   = _c.get("current_value",   0)
        invested  = _c.get("total_invested",  0)
        realised  = _c.get("total_realised",  0)
        dividends = _c.get("total_dividends", 0)
        holdings  = _c.get("holdings_qty",    0)
        bonus     = _c.get("bonus_shares",    0)
        rights    = _c.get("rights_shares",   0)
    elif trades_for_sym and _c:
        # Trades exist but no LMP — show cost metrics, not current value/XIRR
        xirr_pct  = None
        cur_val   = None
        invested  = _c.get("total_invested",  0)
        realised  = _c.get("total_realised",  0)
        dividends = _c.get("total_dividends", 0)
        holdings  = _c.get("holdings_qty",    0)
        bonus     = _c.get("bonus_shares",    0)
        rights    = _c.get("rights_shares",   0)
    else:
        xirr_pct  = None
        cur_val   = None if trades_for_sym else 0.0
        invested  = snap.get("total_invested",  0) or 0.0
        realised  = snap.get("total_realised",  0) or 0.0
        dividends = snap.get("total_dividends", 0) or 0.0
        holdings  = snap.get("holdings_qty",    0) or 0.0
        bonus     = snap.get("bonus_shares",    0) or 0.0
        rights    = snap.get("rights_shares",   0) or 0.0

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
        "Company":       _name_map.get(sym, ""),
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
    if st.button(recalc_label, type="primary", width='stretch', help=recalc_help):
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
    PAGE_SIZE = 20

    # All scrips with value > 0, sorted by current value descending
    tree_scrips = sorted(
        [s for s in filtered_snaps if s.get("type") == "SCRIP"
         and float(s.get("current_value", 0)) > 0],
        key=lambda x: float(x.get("current_value", 0)),
        reverse=True,
    )
    total_scrips = len(tree_scrips)
    total_pages  = max(1, (total_scrips + PAGE_SIZE - 1) // PAGE_SIZE)

    # Page state
    if "treemap_page" not in st.session_state:
        st.session_state["treemap_page"] = 0
    # Clamp to valid range when filter changes
    st.session_state["treemap_page"] = min(
        st.session_state["treemap_page"], total_pages - 1
    )
    page = st.session_state["treemap_page"]

    # Slice for current page
    page_scrips = tree_scrips[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    # Header row with title + pagination controls
    th1, th2 = st.columns([3, 2])
    with th1:
        treemap_title = (
            f"Holdings Map · {filter_label}" if is_filtered else "Holdings Map"
        )
        page_subtitle = (
            f"Top {PAGE_SIZE} by value · Colour = XIRR"
            if total_scrips > PAGE_SIZE
            else "Sized by current value · Colour = XIRR"
        )
        section_header(treemap_title, page_subtitle)
    with th2:
        if total_pages > 1:
            pc1, pc2, pc3 = st.columns([1, 2, 1])
            with pc1:
                if st.button("◀", key="tree_prev",
                             disabled=(page == 0), width="stretch"):
                    st.session_state["treemap_page"] -= 1
                    st.rerun()
            with pc2:
                st.markdown(
                    f'<div style="text-align:center;padding-top:8px;'
                    f'font-size:0.85rem;color:{GREY}">'
                    f'Page {page + 1} / {total_pages}'
                    f'<br><span style="font-size:0.72rem">'
                    f'scrips {page * PAGE_SIZE + 1}–{min((page+1)*PAGE_SIZE, total_scrips)} of {total_scrips}'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )
            with pc3:
                if st.button("▶", key="tree_next",
                             disabled=(page >= total_pages - 1), width="stretch"):
                    st.session_state["treemap_page"] += 1
                    st.rerun()

    # Render treemap for current page slice
    # Pass as generic scrip dicts — portfolio_treemap filters by type="SCRIP"
    fig_tree = portfolio_treemap(page_scrips)
    st.plotly_chart(fig_tree, width='stretch', config={"displayModeBar": False})

with right:
    # Determine symbol context for history — single scrip filter or portfolio
    trend_symbol = None
    trend_title  = "Portfolio XIRR %"
    if is_filtered and f_count == 1:
        trend_symbol = df["Symbol"].iloc[0] if not df.empty else None
        trend_title  = f"{trend_symbol} XIRR %" if trend_symbol else "Portfolio XIRR %"

    section_header("XIRR Trend", "Last 90 daily snapshots")
    hist = load_xirr_history(trend_symbol, limit=90)
    if hist:
        st.plotly_chart(
            xirr_history_chart(hist, trend_title),
            width='stretch',
            config={"displayModeBar": False},
        )
    else:
        st.info("No XIRR history yet. History builds up daily after the Lambda runs.")

    # ── Price & value comparison panel ───────────────────────────────────────
    from datetime import date as _date, timedelta as _td
    today        = _date.today()
    prev_day     = today - _td(days=1)
    # Go back a few days to find a trading day (skip weekends)
    prev_trading = today - _td(days=3)   # Friday if today is Monday
    prev_month   = today.replace(day=1) - _td(days=1)   # last day of prev month

    # Latest snapshot for current lmp
    snap_today = None
    if hist:
        snap_today = hist[0]   # most recent (ScanIndexForward=False)

    snap_prev_day   = load_snapshot_on_date(trend_symbol, prev_trading.isoformat())
    snap_prev_month = load_snapshot_on_date(trend_symbol, prev_month.isoformat())

    def _lmp(snap):
        return float(snap.get("lmp", 0)) if snap else None

    def _val(snap):
        return float(snap.get("current_value", 0)) if snap else None

    lmp_now   = _lmp(snap_today)
    lmp_1d    = _lmp(snap_prev_day)
    lmp_1m    = _lmp(snap_prev_month)
    val_now   = _val(snap_today)
    val_1d    = _val(snap_prev_day)
    val_1m    = _val(snap_prev_month)

    def _pct(now, prev):
        if now and prev and prev > 0:
            return (now - prev) / prev * 100
        return None

    def _pct_html(pct):
        if pct is None:
            return f'<span style="color:{GREY}">—</span>'
        colour = TEAL if pct >= 0 else RED
        arrow  = "▲" if pct >= 0 else "▼"
        return f'<span style="color:{colour};font-weight:700">{arrow} {abs(pct):.2f}%</span>'

    def _price_row(label: str, lmp_then, val_then, lmp_cur, val_cur, as_of: str = ""):
        """Render one comparison row."""
        use_val  = trend_symbol is None   # portfolio: compare value, not price
        now_num  = val_cur  if use_val else lmp_cur
        then_num = val_then if use_val else lmp_then
        pct      = _pct(now_num, then_num)
        fmt      = fmt_inr(then_num) if then_num else "—"
        date_lbl = f'<span style="color:{GREY};font-size:0.75rem"> ({as_of})</span>' if as_of else ""
        return (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:8px 0;border-bottom:1px solid {BORDER}">'
            f'<div style="color:{GREY};font-size:0.85rem">{label}{date_lbl}</div>'
            f'<div style="text-align:right">'
            f'<span style="font-weight:600;margin-right:8px">{fmt}</span>'
            f'{_pct_html(pct)}'
            f'</div></div>'
        )

    label_field = "Portfolio Value" if trend_symbol is None else "Price (LMP)"
    as_of_1d    = snap_prev_day.get("as_of", "")   if snap_prev_day   else ""
    as_of_1m    = snap_prev_month.get("as_of", "") if snap_prev_month else ""

    rows_html = ""
    if lmp_1d or val_1d:
        rows_html += _price_row("vs Prev Trading Day", lmp_1d, val_1d,
                                 lmp_now, val_now, as_of_1d)
    if lmp_1m or val_1m:
        rows_html += _price_row("vs Prev Month End",   lmp_1m, val_1m,
                                 lmp_now, val_now, as_of_1m)

    if rows_html and (lmp_now or val_now):
        current_label = fmt_inr(val_now if trend_symbol is None else lmp_now)
        st.markdown(
            f'<div style="background:{CARD_BG};border:1px solid {BORDER};'
            f'border-radius:10px;padding:14px 18px;margin-top:8px">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;margin-bottom:10px">'
            f'<div style="font-size:0.78rem;color:{GREY};text-transform:uppercase;'
            f'letter-spacing:0.06em">{label_field}</div>'
            f'<div style="font-size:1.2rem;font-weight:700;color:{TEAL}">'
            f'{current_label}</div></div>'
            f'{rows_html}</div>',
            unsafe_allow_html=True,
        )
    elif not hist:
        pass  # already shown info above

# ── Scrip table ───────────────────────────────────────────────────────────────
section_header(
    f"{'Filtered' if is_filtered else 'All'} Scrips",
    f"{f_count} position{'s' if f_count != 1 else ''}"
    + (f" · {filter_label}" if is_filtered else "")
)

def colour_xirr(val):
    if val is None or pd.isna(val): return f"color: {GREY}"
    return f"color: {TEAL}" if val >= 0 else f"color: {RED}"

# Build display df — Company right after Symbol
_col_order = ["Symbol", "Company", "XIRR %", "Current Value", "Invested",
              "Realised", "Dividends", "Holdings", "Face Value (₹)", "LMP (₹)",
              "Bonus Shares", "Rights Shares", "As Of", "Broker", "Sector"]
_base    = df.drop(columns=["_snap"])
_ordered = [c for c in _col_order if c in _base.columns]
_extra   = [c for c in _base.columns if c not in _ordered]
display_df = _base[[*_ordered, *_extra]]

styled = (
    display_df.style
    .format({
        "Company":       lambda x: x if x else "—",
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
    .map(colour_xirr, subset=["XIRR %"])
    .set_properties(**{"background-color": CARD_BG, "border-color": BORDER})
    .hide(axis="index")
)

st.dataframe(styled, width='stretch', height=420)

# Download
csv = display_df.to_csv(index=False)
st.download_button(
    "⬇️ Download as CSV",
    data=csv,
    file_name=f"portfolio_{filter_label.replace(' ', '_').replace(':', '')}_{date.today()}.csv",
    mime="text/csv",
)
