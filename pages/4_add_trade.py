"""
pages/4_add_trade.py
Add a trade or corporate action with broker auto-charges and sector tagging.
"""
import streamlit as st
import pandas as pd
from datetime import date

from utils.data import (
    put_record,
    load_all_trades,
    load_broker_configs,
    get_all_broker_names,
    search_tickers,
    NSE_SECTORS,
)
from utils.ui import (
    section_header, metric_card,
    TEAL, RED, GREY, BORDER, CARD_BG,
    CYAN, PURPLE, ORANGE, ACTION_COLOURS,
)

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.3rem;font-weight:800;color:#00A88A;padding:16px 0 24px">'
        "📈 XIRR Tracker</div>",
        unsafe_allow_html=True,
    )

# ── Curated NSE ticker list for symbol suggestions ────────────────────────────
def _validate_symbol_nse(symbol: str) -> tuple[bool, str]:
    """
    Validate a ticker symbol against NSE (primary) then BSE (fallback).
    Returns (is_valid, message).
    Runs from Streamlit Cloud IPs which are not blocked by NSE.
    """
    import requests as _req

    # NSE quote endpoint
    try:
        nse_url  = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
        headers  = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept":   "application/json",
            "Referer":  "https://www.nseindia.com/",
        }
        # Need a session with cookies for NSE API
        session = _req.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
        resp = session.get(nse_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            name = data.get("info", {}).get("companyName", symbol)
            ltp  = data.get("priceInfo", {}).get("lastPrice")
            ltp_str = f" · LTP: ₹{ltp:,.2f}" if ltp else ""
            return True, f"{symbol} — {name}{ltp_str} (NSE)"
    except Exception:
        pass

    # BSE fallback via yfinance
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{symbol}.NS")
        info   = ticker.fast_info
        ltp    = getattr(info, "last_price", None)
        if ltp and float(ltp) > 0:
            name = ticker.info.get("longName", symbol)
            return True, f"{symbol} — {name} · LTP: ₹{float(ltp):,.2f} (via Yahoo)"
    except Exception:
        pass

    return False, (
        f"'{symbol}' not found on NSE or BSE. "
        "Check spelling — use the exact NSE ticker (e.g. HDFCBANK not HDFC-BANK)."
    )


_NSE_TICKERS = sorted(set([
    "ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK",
    "BAJAJ-AUTO","BAJFINANCE","BAJAJFINSV","BPCL","BHARTIARTL",
    "BRITANNIA","CIPLA","COALINDIA","DIVISLAB","DRREDDY",
    "EICHERMOT","GRASIM","HCLTECH","HDFCBANK","HDFCLIFE",
    "HEROMOTOCO","HINDALCO","HINDUNILVR","ICICIBANK","ITC",
    "INDUSINDBK","INFY","JSWSTEEL","KOTAKBANK","LTIM",
    "LT","M&M","MARUTI","NESTLEIND","NTPC",
    "ONGC","POWERGRID","RELIANCE","SBILIFE","SHRIRAMFIN",
    "SBIN","SUNPHARMA","TCS","TATACONSUM","TATAMOTORS",
    "TATASTEEL","TECHM","TITAN","ULTRACEMCO","WIPRO",
    "ABB","ADANIGREEN","ADANIPOWER","AMBUJACEM","APOLLOTYRE",
    "ASHOKLEY","ASTRAL","AUBANK","AUROPHARMA","BALKRISIND",
    "BANDHANBNK","BANKBARODA","BATAINDIA","BERGEPAINT","BIOCON",
    "BOSCHLTD","CANBK","CHOLAFIN","COFORGE","COLPAL",
    "CONCOR","CUMMINSIND","DABUR","DEEPAKNTR","DELHIVERY",
    "DIXON","DLF","DMART","ESCORTS","FEDERALBNK",
    "GAIL","GODREJCP","GODREJPROP","GRANULES","GUJGASLTD",
    "HAL","HAVELLS","HINDPETRO","ICICIGI","IDFCFIRSTB",
    "IEX","INDHOTEL","INDIANB","INDIGO","INDUSTOWER",
    "IOC","IRCTC","JSWENERGY","JUBLFOOD","KANSAINER",
    "LALPATHLAB","LICHSGFIN","LUPIN","MARICO","MAXHEALTH",
    "MFSL","MOTHERSON","MPHASIS","MRF","MUTHOOTFIN",
    "NAUKRI","NAVINFLUOR","NMDC","OBEROIRLTY","OFSS",
    "PAGEIND","PERSISTENT","PETRONET","PHOENIXLTD","PIDILITIND",
    "PIIND","PNB","POLYCAB","POONAWALLA","PVRINOX",
    "RBLBANK","RECLTD","SAIL","SOLARINDS","STARHEALTH",
    "SUPREMEIND","SUZLON","TATACOMM","TATAPOWER","TRENT",
    "TVSMOTOR","UBL","UNIONBANK","UPL","VEDL",
    "VOLTAS","YESBANK","ZOMATO","ZYDUSLIFE",
    "BEL","BHEL","NBCC","NHPC","NLC","PFC","RVNL","SJVN",
    "UCOBANK","IOB","MAHABANK","CENTRALBK","TRIDENT",
    "ALKEM","ATUL","FINEORG","FLUOROCHEM","HAPPSTMNDS",
    "HONAUT","IPCALAB","KAJARIACER","KPITTECH","LAURUSLABS",
    "LTTS","METROPOLIS","NIACL","RADICO","RATEGAIN",
    "ROUTE","SKFINDIA","SONACOMS","SUNDRMFAST","TANLA",
    "TORNTPHARM","TORNTPOWER","VGUARD","VMART","WESTLIFE",
    "ZEEL","HFCL","MINDA","HDFCAMC","LICI","JSWINFRA",
    "ATGL","CGPOWER","NHPC","COCHINSHIP","GRSE","MIDHANI",
]))

ACTION_META = {
    "BUY":      {"icon": "🟢", "colour": TEAL,    "desc": "Purchase of shares",
                 "price_label": "Price per share (Rs.)", "qty_label": "Shares bought",
                 "show_charges": True,  "price_zero_ok": False, "show_notes": True},
    "SELL":     {"icon": "🔴", "colour": RED,     "desc": "Sale of shares",
                 "price_label": "Sale price per share (Rs.)", "qty_label": "Shares sold",
                 "show_charges": True,  "price_zero_ok": False, "show_notes": True},
    "DIVIDEND": {"icon": "💰", "colour": CYAN,    "desc": "Cash dividend received",
                 "price_label": "Dividend per share (Rs.)", "qty_label": "Shares held on record date",
                 "show_charges": False, "price_zero_ok": False, "show_notes": True},
    "BONUS":    {"icon": "🎁", "colour": PURPLE,  "desc": "Bonus shares allotted",
                 "price_label": "Price (always 0)", "qty_label": "New bonus shares allotted",
                 "show_charges": False, "price_zero_ok": True,  "show_notes": True},
    "RIGHTS":   {"icon": "⚡", "colour": ORANGE,  "desc": "Rights issue subscription",
                 "price_label": "Rights price per share (Rs.)", "qty_label": "Shares subscribed",
                 "show_charges": True,  "price_zero_ok": False, "show_notes": True},
    "SPLIT":    {"icon": "✂️", "colour": "#0284C7", "desc": "Stock split — adjusts qty and face value",
                 "price_label": "New face value after split (Rs.)", "qty_label": "New shares per existing share (e.g. 10 for 1:10)",
                 "show_charges": False, "price_zero_ok": False, "show_notes": True},
    "MERGER":   {"icon": "🔗", "colour": "#9333EA", "desc": "Company merged — holdings absorbed",
                 "price_label": "Exchange ratio value (Rs.) — usually 0",
                 "qty_label": "Acquirer shares received per share held",
                 "show_charges": False, "price_zero_ok": True,  "show_notes": True},
    "DEMERGER": {"icon": "✂️", "colour": "#EA580C", "desc": "Demerger — new entity shares allotted",
                 "price_label": "Price (Rs.) — 0 for demerger allotment",
                 "qty_label": "New entity shares allotted",
                 "show_charges": False, "price_zero_ok": True,  "show_notes": True},
}

st.markdown("""
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:4px">Add Trade / Corporate Action</h1>
<div style="color:#6B7280;margin-bottom:24px">Record a transaction with broker and sector tagging</div>
""", unsafe_allow_html=True)

tab_add, tab_brokers = st.tabs(["➕  Add Trade", "🏦  Manage Brokers"])

# ══════════════════════════════════════════════════════════════════════════════
with tab_add:

    broker_configs = load_broker_configs()
    all_broker_names = get_all_broker_names()
    broker_options   = ["(none)"] + all_broker_names
    # Map display name → broker key (uppercase underscored)
    broker_key_map   = {
        name: name.upper().replace(" ", "_")
        for name in all_broker_names
    }
    # Also map from config for backwards compatibility
    for c in broker_configs:
        bname = c.get("broker_name", c.get("broker_key",""))
        bkey  = c.get("broker_key","")
        if bname and bkey:
            broker_key_map[bname] = bkey

    try:
        trade_symbols = set(load_all_trades().keys())
    except Exception:
        trade_symbols = set()
    # Merge user's own scrips with the curated NSE ticker list
    known_symbols = sorted(trade_symbols | set(_NSE_TICKERS))

    st.markdown("#### 1 — Select action type")
    act_cols = st.columns(8)
    selected_action = st.session_state.get("selected_action", "BUY")
    for i, (action, meta) in enumerate(ACTION_META.items()):
        with act_cols[i]:
            if st.button(f"{meta['icon']} **{action}**\n\n{meta['desc']}",
                         key=f"action_btn_{action}", width='stretch',
                         type="primary" if selected_action == action else "secondary"):
                st.session_state["selected_action"] = action
                st.rerun()

    action = st.session_state.get("selected_action", "BUY")
    meta   = ACTION_META[action]
    colour = meta["colour"]

    st.markdown(f'''
    <div style="background:{colour}10;border:1px solid {colour}40;
                border-radius:10px;padding:10px 16px;margin:12px 0 20px 0;
                color:{colour};font-size:0.9rem">
        {meta["icon"]} <strong>{action}</strong>: {meta["desc"]}
    </div>
    ''', unsafe_allow_html=True)

    st.markdown("#### 2 — Trade details")

    if "form_broker" not in st.session_state:
        st.session_state["form_broker"] = "(none)"

    pre1, pre2 = st.columns(2)
    with pre1:
        selected_broker_name = st.selectbox(
            "Broker",
            broker_options,
            index=broker_options.index(st.session_state["form_broker"])
                  if st.session_state["form_broker"] in broker_options else 0,
            key="pre_broker_select",
            help="Select broker to auto-calculate charges. Add brokers in Manage Brokers tab.",
        )
        st.session_state["form_broker"] = selected_broker_name
    with pre2:
        selected_sector = st.selectbox(
            "Sector", ["(none)"] + NSE_SECTORS, key="pre_sector_select",
            help="Tag with NSE sector for sector-level XIRR analysis.",
        )

    # Symbol input with live DynamoDB ticker search
    sym_col, date_col = st.columns(2)
    with sym_col:
        typed = st.text_input(
            "NSE/BSE Symbol *",
            value=st.session_state.get("sym_confirmed", ""),
            placeholder="Type to search — e.g. REL, HDFC, INFY",
            key="symbol_text_input",
            help="Type at least 1 character to see matching tickers from the NSE/BSE master list.",
        )
        typed_upper = typed.strip().upper()

        # Live suggestions from DynamoDB ticker table
        # Cache last search in session_state to avoid hitting DynamoDB every rerun
        cache_key = f"ticker_cache_{typed_upper}"
        if typed_upper and len(typed_upper) >= 1:
            if cache_key not in st.session_state:
                st.session_state[cache_key] = search_tickers(typed_upper, limit=9)
            suggestions = st.session_state[cache_key]
        else:
            suggestions = []

        confirmed = st.session_state.get("sym_confirmed", "")

        if suggestions and typed_upper != confirmed:
            st.caption(f"\U0001f50d {len(suggestions)} match(es) \u2014 click to select:")
            btn_cols = st.columns(min(len(suggestions), 3))
            for idx, s in enumerate(suggestions[:6]):
                with btn_cols[idx % 3]:
                    cname = s["company_name"][:24]
                    if st.button(
                        s["symbol"] + "  " + cname,
                        key=f"sugg_{s['symbol']}_{idx}",
                        width="stretch",
                    ):
                        st.session_state["sym_confirmed"] = s["symbol"]
                        st.session_state["sym_fv"]        = s.get("face_value", 10.0)
                        st.session_state["sym_name"]      = s.get("company_name", "")
                        st.rerun()
        elif confirmed and confirmed == typed_upper:
            name   = st.session_state.get("sym_name", "")
            fv_val = st.session_state.get("sym_fv", "")
            fv_str = f" \u00b7 FV Rs.{fv_val:g}" if fv_val else ""
            st.success(f"\u2705 {confirmed}  {name}{fv_str}")
        elif typed_upper and not suggestions:
            # Try a direct test query to distinguish "empty table" from "query error"
            try:
                from utils.data import get_aws_config
                import boto3
                from boto3.dynamodb.conditions import Key as _Key
                cfg      = get_aws_config()
                _ddb     = boto3.resource("dynamodb", region_name=cfg["region"],
                               aws_access_key_id=cfg["access_key_id"],
                               aws_secret_access_key=cfg["secret_access_key"])
                _tbl_name = st.secrets["dynamodb"].get("tickers_table", "")
                if not _tbl_name:
                    st.warning("tickers_table not set in secrets. Add tickers_table = 'portfolio_tickers_prod' under [dynamodb].")
                else:
                    _tbl = _ddb.Table(_tbl_name)
                    # Check if table has any items at all
                    _scan = _tbl.scan(Limit=3)
                    _count = _scan.get("Count", 0)
                    if _count == 0:
                        st.warning(f"Ticker table '{_tbl_name}' appears empty. Run load_tickers.py to populate it.")
                    else:
                        st.warning(
                            f"'{typed_upper}' not found in ticker master ({_tbl_name}). "
                            f"Table has data ({_count}+ items). Check that load_tickers.py wrote gsi1pk='ALL_TICKERS'."
                        )
            except Exception as _e:
                st.warning(f"'{typed_upper}' not found. Ticker lookup error: {_e}")

        # Confirm or clear
        if typed_upper != confirmed and confirmed:
            st.session_state["sym_confirmed"] = ""
            st.session_state["sym_name"] = ""
            confirmed = ""

        symbol_input = confirmed if (confirmed and confirmed == typed_upper) else typed_upper

    with date_col:
        trade_date = st.date_input(
            "Trade / Ex-Date *", value=date.today(), max_value=date.today()
        )

    with st.form("add_trade_form", clear_on_submit=True):
        c3, c4 = st.columns(2)
        with c3:
            qty = st.number_input(meta["qty_label"] + " *", min_value=0.0, value=0.0, step=1.0, format="%.2f")
        with c4:
            if action == "BONUS":
                price = 0.0
                st.number_input("Price per share (Rs.)", value=0.0, disabled=True)
            else:
                price = st.number_input(meta["price_label"] + " *", min_value=0.0, value=0.0, step=0.25, format="%.4f")

        if meta["show_charges"]:
            broker_key_val = broker_key_map.get(st.session_state.get("form_broker", "(none)"), "")
            auto_charges   = (calc_broker_charges(broker_key_val, action, qty, price, broker_configs)
                              if qty > 0 and price > 0 and broker_key_val else 0.0)

            c5, c6 = st.columns(2)
            with c5:
                broker_hint = ""
                for bc in broker_configs:
                    if bc.get("broker_key") == broker_key_val:
                        p_key = f"{action.lower()}_pct"
                        m_key = f"{action.lower()}_min"
                        pct   = float(bc.get(p_key, bc.get("buy_pct", 0)))
                        mn    = float(bc.get(m_key, bc.get("buy_min", 0)))
                        broker_hint = f"{pct:.4g}%, min Rs.{mn:.0f}"
                charges = st.number_input(
                    "Brokerage + Charges (Rs.)",
                    min_value=0.0, value=auto_charges, step=1.0, format="%.2f",
                    help=f"Auto: {broker_hint}" if broker_hint else "Select a broker above to auto-calculate.",
                )
            with c6:
                if price > 0 and qty > 0:
                    gross   = qty * price
                    net     = gross + charges if action in ("BUY", "RIGHTS") else gross - charges
                    net_lbl = "Net Outflow" if action in ("BUY", "RIGHTS") else "Net Inflow"
                    st.markdown(f'''
                    <div style="background:{CARD_BG};border:1px solid {BORDER};
                                border-radius:10px;padding:14px;margin-top:26px">
                        <div style="color:{GREY};font-size:0.75rem">Gross</div>
                        <div style="color:#111827;font-weight:600">Rs.{gross:,.2f}</div>
                        <div style="color:{GREY};font-size:0.75rem;margin-top:6px">Charges</div>
                        <div style="color:{ORANGE}">Rs.{charges:,.2f}</div>
                        <div style="color:{GREY};font-size:0.75rem;margin-top:6px">{net_lbl}</div>
                        <div style="color:{colour};font-weight:700;font-size:1.1rem">Rs.{net:,.2f}</div>
                    </div>
                    ''', unsafe_allow_html=True)
        else:
            charges = 0.0
            if action == "DIVIDEND" and price > 0 and qty > 0:
                st.info(f"Total dividend: **Rs.{qty * price:,.2f}**")

        notes = st.text_input("Notes (optional)", max_chars=200,
                               placeholder="e.g. FY24 dividend / Added on dip")

        broker_display = st.session_state.get("form_broker", "(none)")
        sector_display = selected_sector if selected_sector != "(none)" else ""
        if symbol_input and qty > 0 and (price > 0 or action == "BONUS"):
            broker_tag = (f'<div><div style="color:{GREY};font-size:0.72rem">Broker</div>'
                          f'<div style="color:{ORANGE}">{broker_display}</div></div>'
                          if broker_display != "(none)" else "")
            sector_tag = (f'<div><div style="color:{GREY};font-size:0.72rem">Sector</div>'
                          f'<div style="color:{CYAN}">{sector_display}</div></div>'
                          if sector_display else "")
            st.markdown(f'''
            <div style="background:{colour}08;border:1px solid {colour}30;
                        border-radius:10px;padding:12px 18px;margin:12px 0">
                <div style="font-size:0.72rem;color:{GREY};margin-bottom:8px;
                            text-transform:uppercase;letter-spacing:0.06em">Preview</div>
                <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:0.9rem">
                    <div><div style="color:{GREY};font-size:0.72rem">Action</div>
                         <div style="color:{colour};font-weight:700">{action}</div></div>
                    <div><div style="color:{GREY};font-size:0.72rem">Symbol</div>
                         <div style="color:#111827;font-weight:600">{symbol_input.upper()}</div></div>
                    <div><div style="color:{GREY};font-size:0.72rem">Date</div>
                         <div style="color:#111827">{trade_date}</div></div>
                    <div><div style="color:{GREY};font-size:0.72rem">Qty</div>
                         <div style="color:#111827">{qty:,.0f}</div></div>
                    <div><div style="color:{GREY};font-size:0.72rem">Price</div>
                         <div style="color:#111827">Rs.{price:,.2f}</div></div>
                    {broker_tag}{sector_tag}
                </div>
            </div>
            ''', unsafe_allow_html=True)

        submitted = st.form_submit_button(f"{meta['icon']} Submit {action}",
                                          type="primary", width='stretch')

    if submitted:
        errs = []
        sym  = symbol_input.strip().upper()
        if not sym or not sym.replace("&", "").replace("-", "").isalpha():
            errs.append("Symbol is required and must be letters only.")
        if qty <= 0:
            errs.append("Quantity must be > 0.")
        if action != "BONUS" and price <= 0:
            errs.append(f"Price must be > 0 for {action}.")
        if action == "BONUS" and price != 0:
            errs.append("Price must be 0 for BONUS.")

        if errs:
            for e in errs:
                st.error(f"x {e}")
        else:
            broker_key_final = broker_key_map.get(st.session_state.get("form_broker", "(none)"), "")
            sector_final     = selected_sector if selected_sector != "(none)" else ""
            record = {
                "symbol":     sym,
                "action":     action,
                "trade_date": trade_date.isoformat(),
                "qty":        qty,
                "price":      price,
                "charges":    charges if meta["show_charges"] else 0.0,
                "notes":      notes,
                "broker":     broker_key_final,
                "sector":     sector_final.upper() if sector_final else "",
            }
            try:
                sk = put_record(record)
                st.success(f"**{action}** recorded for **{sym}** on {trade_date}")
                extras = []
                if broker_key_final:
                    extras.append(f"Broker: {st.session_state.get('form_broker')}")
                if sector_final:
                    extras.append(f"Sector: {sector_final}")
                if extras:
                    st.caption(" · ".join(extras))
                st.markdown(
                    f'<div style="background:{CARD_BG};border:1px solid {BORDER};'
                    f'border-radius:10px;padding:12px;margin-top:8px;color:{GREY};font-size:0.8rem">'
                    f'SK: <code style="color:{TEAL}">{sk}</code></div>',
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.error(f"Failed to write to DynamoDB: {e}")


# ══════════════════════════════════════════════════════════════════════════════
with tab_brokers:
    st.markdown("""
    <h3 style="margin-bottom:4px">Broker Charge Rates</h3>
    <div style="color:#6B7280;font-size:0.85rem;margin-bottom:20px">
        Charges = <code>max(trade_value × rate%, min_charge)</code>
    </div>
    """, unsafe_allow_html=True)

    broker_configs = load_broker_configs()

    if broker_configs:
        section_header("Configured Brokers")
        rows = [{
            "Broker":           c.get("broker_name", c.get("broker_key")),
            "Key":              c.get("broker_key", ""),
            "Buy %":            float(c.get("buy_pct", 0)),
            "Buy Min (Rs.)":    float(c.get("buy_min", 0)),
            "Sell %":           float(c.get("sell_pct", 0)),
            "Sell Min (Rs.)":   float(c.get("sell_min", 0)),
            "Rights %":         float(c.get("rights_pct", 0)),
            "Rights Min (Rs.)": float(c.get("rights_min", 0)),
        } for c in broker_configs]
        st.dataframe(
            pd.DataFrame(rows).style.format({
                "Buy %": "{:.4g}%", "Sell %": "{:.4g}%", "Rights %": "{:.4g}%",
                "Buy Min (Rs.)":    "Rs.{:.0f}",
                "Sell Min (Rs.)":   "Rs.{:.0f}",
                "Rights Min (Rs.)": "Rs.{:.0f}",
            }).hide(axis="index"),
            width='stretch', height=min(300, 60 + len(rows) * 35),
        )

    section_header("Add / Edit Broker")
    existing_keys = [c.get("broker_key") for c in broker_configs]
    edit_options  = ["-- Add new --"] + existing_keys
    edit_choice   = st.selectbox("Edit or add", edit_options, label_visibility="collapsed")
    edit_cfg      = next((c for c in broker_configs if c.get("broker_key") == edit_choice), {})                     if edit_choice != "-- Add new --" else {}

    with st.form("broker_form"):
        bf1, bf2 = st.columns(2)
        with bf1:
            if edit_choice == "-- Add new --":
                new_options = ["CUSTOM"] + [k for k in DEFAULT_BROKERS if k not in existing_keys]
                b_key_sel   = st.selectbox("Select or use CUSTOM", new_options)
                b_key       = st.text_input("Key (CAPS)", value="" if b_key_sel == "CUSTOM" else b_key_sel,
                                             placeholder="MY_BROKER").strip().upper()
                b_name      = st.text_input("Display name", value=b_key.replace("_", " ").title())
            else:
                b_key  = edit_choice
                b_name = st.text_input("Display name", value=edit_cfg.get("broker_name", edit_choice))
                st.caption(f"Key: `{b_key}`")
        with bf2:
            st.markdown(f'<div style="background:{CARD_BG};border:1px solid {BORDER};border-radius:8px;'
                        f'padding:10px 14px;font-size:0.82rem;color:{GREY};margin-top:28px">'
                        f'Charges = max(value × rate%, min)<br>'
                        f'e.g. Rs.1L at 0.03% = Rs.30 &gt; Rs.20 min</div>', unsafe_allow_html=True)

        r1, r2, r3 = st.columns(3)
        with r1:
            st.markdown("**BUY**")
            buy_pct = st.number_input("Rate %", min_value=0.0, value=float(edit_cfg.get("buy_pct", 0.03)),
                                       step=0.001, format="%.4f", key="buy_pct")
            buy_min = st.number_input("Min (Rs.)", min_value=0.0, value=float(edit_cfg.get("buy_min", 20.0)),
                                       step=1.0, format="%.0f", key="buy_min")
        with r2:
            st.markdown("**SELL**")
            sell_pct = st.number_input("Rate %", min_value=0.0, value=float(edit_cfg.get("sell_pct", 0.03)),
                                        step=0.001, format="%.4f", key="sell_pct")
            sell_min = st.number_input("Min (Rs.)", min_value=0.0, value=float(edit_cfg.get("sell_min", 20.0)),
                                        step=1.0, format="%.0f", key="sell_min")
        with r3:
            st.markdown("**RIGHTS**")
            rights_pct = st.number_input("Rate %", min_value=0.0, value=float(edit_cfg.get("rights_pct", 0.03)),
                                          step=0.001, format="%.4f", key="rights_pct")
            rights_min = st.number_input("Min (Rs.)", min_value=0.0, value=float(edit_cfg.get("rights_min", 20.0)),
                                          step=1.0, format="%.0f", key="rights_min")

        save_clicked = st.form_submit_button("Save broker config", type="primary", width='stretch')

    if save_clicked:
        fk = b_key if edit_choice == "-- Add new --" else edit_choice
        if not fk:
            st.error("Broker key is required.")
        else:
            try:
                save_broker_config({"broker_key": fk, "broker_name": b_name or fk,
                                     "buy_pct": buy_pct, "buy_min": buy_min,
                                     "sell_pct": sell_pct, "sell_min": sell_min,
                                     "rights_pct": rights_pct, "rights_min": rights_min})
                st.success(f"Broker **{b_name or fk}** saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save: {e}")

    if broker_configs:
        st.markdown("---")
        section_header("Delete Broker")
        dc, bc = st.columns([2, 1])
        with dc:
            del_choice = st.selectbox("Select broker", existing_keys, label_visibility="collapsed")
        with bc:
            st.markdown("<div style='height:26px'/>", unsafe_allow_html=True)
            if st.button("Delete", type="primary", width='stretch'):
                try:
                    delete_broker_config(del_choice)
                    st.success(f"Broker `{del_choice}` deleted.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")
