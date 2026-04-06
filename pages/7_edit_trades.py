"""
pages/7_edit_trades.py
Edit, delete, or bulk-delete trade records from DynamoDB.
"""
import streamlit as st
import pandas as pd
from datetime import date

from utils.data import (
    load_all_trades, load_trades_for_scrip,
    delete_record, update_record, rename_symbol_record,
    search_tickers, VALID_ACTIONS,
)
from utils.ui import (
    section_header, ACTION_COLOURS,
    TEAL, RED, GREY, BORDER, CARD_BG, ORANGE,
)

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.3rem;font-weight:800;color:#00A88A;padding:16px 0 24px">'
        '📈 XIRR Tracker</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("🔄 Refresh", width='stretch'):
        st.cache_data.clear()
        st.rerun()

st.markdown("""
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:4px">Edit Trades</h1>
<div style="color:#6B7280;margin-bottom:24px">
    Edit, delete, or bulk-delete trade records. Changes take effect immediately.
</div>
""", unsafe_allow_html=True)

with st.spinner("Loading trades…"):
    try:
        all_trades = load_all_trades()
    except Exception as e:
        st.error(f"Could not load trades: `{e}`")
        st.stop()

if not all_trades:
    st.warning("No trade records found.")
    st.stop()

symbols = sorted(all_trades.keys())

tab_bulk, tab_single = st.tabs(["🗑️  Bulk Delete", "✏️  Edit / Delete Single"])


# ══════════════════════════════════════════════════════════════════════════════
with tab_bulk:
    st.markdown(
        f'<div style="color:{GREY};font-size:0.88rem;margin-bottom:16px">'
        "Filter records, tick the checkboxes on the left to select rows, "
        "then type DELETE and confirm.</div>",
        unsafe_allow_html=True,
    )

    f1, f2, f3, f4 = st.columns([2, 2, 1, 1])
    with f1:
        bulk_symbols = st.multiselect("Scrip", symbols, placeholder="All scrips",
                                      label_visibility="collapsed")
    with f2:
        bulk_actions = st.multiselect("Action", sorted(VALID_ACTIONS),
                                      placeholder="All actions",
                                      label_visibility="collapsed")
    with f3:
        date_from = st.date_input("From", value=None, label_visibility="collapsed")
    with f4:
        date_to   = st.date_input("To",   value=None, label_visibility="collapsed")

    all_rows = []
    for sym, trades in all_trades.items():
        for t in trades:
            all_rows.append({
                "_pk":     t.get("pk", ""),
                "_sk":     t.get("sk", ""),
                "Symbol":  sym,
                "Date":    t.get("trade_date", ""),
                "Action":  t.get("action", "").upper(),
                "Qty":     float(t.get("qty", 0)),
                "Price":   float(t.get("price", 0)),
                "Charges": float(t.get("charges", 0)),
                "Notes":   t.get("notes", ""),
                "Broker":  t.get("broker", ""),
            })

    bulk_df = pd.DataFrame(all_rows).sort_values(
        ["Date", "Symbol"], ascending=[False, True]
    ).reset_index(drop=True)

    if bulk_symbols:
        bulk_df = bulk_df[bulk_df["Symbol"].isin(bulk_symbols)].reset_index(drop=True)
    if bulk_actions:
        bulk_df = bulk_df[bulk_df["Action"].isin(bulk_actions)].reset_index(drop=True)
    if date_from:
        bulk_df = bulk_df[bulk_df["Date"] >= date_from.isoformat()].reset_index(drop=True)
    if date_to:
        bulk_df = bulk_df[bulk_df["Date"] <= date_to.isoformat()].reset_index(drop=True)

    if bulk_df.empty:
        st.info("No records match the current filters.")
    else:
        st.caption(f"{len(bulk_df)} record(s) — tick rows on the left to select for deletion.")

        display_cols = ["Symbol","Date","Action","Qty","Price","Charges","Notes","Broker"]

        edited = st.data_editor(
            bulk_df[display_cols],
            hide_index=False,
            num_rows="fixed",
            width='stretch',
            height=min(520, 60 + len(bulk_df) * 36),
            column_config={
                "Symbol":  st.column_config.TextColumn(width="small"),
                "Date":    st.column_config.TextColumn(width="small"),
                "Action":  st.column_config.TextColumn(width="small"),
                "Qty":     st.column_config.NumberColumn(format="%.0f", width="small"),
                "Price":   st.column_config.NumberColumn(format="₹%.2f", width="small"),
                "Charges": st.column_config.NumberColumn(format="₹%.2f", width="small"),
                "Notes":   st.column_config.TextColumn(width="medium"),
                "Broker":  st.column_config.TextColumn(width="small"),
            },
            disabled=display_cols,
            key="bulk_edit_table",
        )

        editor_state  = st.session_state.get("bulk_edit_table", {})
        selected_idxs = sorted(editor_state.get("selected_rows", []))

        if selected_idxs:
            sel_summary = ", ".join(
                f"{bulk_df.iloc[i]['Symbol']} {bulk_df.iloc[i]['Action']} {bulk_df.iloc[i]['Date']}"
                for i in selected_idxs[:5]
            ) + (f" … +{len(selected_idxs)-5} more" if len(selected_idxs) > 5 else "")

            st.markdown(
                f'<div style="background:{RED}10;border:1px solid {RED}40;'
                f'border-radius:8px;padding:10px 16px;margin:12px 0;font-size:0.88rem">'
                f'<strong style="color:{RED}">⚠️ {len(selected_idxs)} record(s) selected:</strong> '
                f'{sel_summary}</div>',
                unsafe_allow_html=True,
            )

            confirm_bulk = st.text_input(
                f"Type DELETE to confirm removal of {len(selected_idxs)} record(s)",
                placeholder="Type DELETE to confirm",
                key="bulk_delete_confirm",
            )

            if st.button(
                f"🗑️ Delete {len(selected_idxs)} selected record(s)",
                type="primary",
                disabled=(confirm_bulk.strip().upper() != "DELETE"),
                key="bulk_delete_btn",
            ) and confirm_bulk.strip().upper() == "DELETE":
                success = failed = 0
                for i in selected_idxs:
                    try:
                        row = bulk_df.iloc[i]
                        delete_record(row["_pk"], row["_sk"], symbol=row["Symbol"])
                        success += 1
                    except Exception as exc:
                        st.error(f"Row {i}: {exc}")
                        failed += 1
                if success:
                    st.cache_data.clear()
                    st.success(f"✅ Deleted {success} record(s)" +
                               (f" · {failed} failed" if failed else ""))
                    st.rerun()
        else:
            st.info("Tick the checkbox on the left of each row you want to delete.")


# ══════════════════════════════════════════════════════════════════════════════
with tab_single:
    section_header("Step 1 — Select a scrip")
    col_sym, col_filter = st.columns([2, 3])
    with col_sym:
        selected_symbol = st.selectbox(
            "Scrip", symbols,
            label_visibility="collapsed",
            format_func=lambda s: f"  {s}  ({len(all_trades.get(s, []))} records)",
        )

    trades = load_trades_for_scrip(selected_symbol)
    if not trades:
        st.warning(f"No records for {selected_symbol}.")
        st.stop()

    with col_filter:
        action_filter = st.multiselect(
            "Filter by action", options=sorted(VALID_ACTIONS),
            default=[], placeholder="All actions",
            label_visibility="collapsed",
        )

    if action_filter:
        trades = [t for t in trades if t.get("action","").upper() in action_filter]
    if not trades:
        st.info("No records match the filter.")
        st.stop()

    section_header("Step 2 — Select a record",
                   f"{len(trades)} record(s) for {selected_symbol}")

    rows = []
    for t in sorted(trades, key=lambda x: x.get("trade_date",""), reverse=True):
        rows.append({
            "_pk":     t.get("pk",""),
            "_sk":     t.get("sk",""),
            "_raw":    t,
            "Symbol":  t.get("symbol", selected_symbol).upper(),
            "Date":    t.get("trade_date",""),
            "Action":  t.get("action","").upper(),
            "Qty":     float(t.get("qty",0)),
            "Price":   float(t.get("price",0)),
            "Charges": float(t.get("charges",0)),
            "Notes":   t.get("notes",""),
        })

    df = pd.DataFrame(rows)

    def _style_action(val):
        c = ACTION_COLOURS.get(str(val).upper(), GREY)
        return f"color: {c}; font-weight: 600"

    styled = (
        df.drop(columns=["_pk","_sk"]).reset_index(drop=True).style
        .format({
            "Qty":     lambda x: f"{x:,.0f}",
            "Price":   lambda x: f"₹{x:,.4f}",
            "Charges": lambda x: f"₹{x:,.2f}" if x else "—",
        })
        .map(_style_action, subset=["Action"])
        .hide(axis="index")
    )
    st.dataframe(styled, width='stretch',
                 height=min(380, 60 + len(rows) * 35), hide_index=True)

    section_header("Step 3 — Choose a record")

    def _label(row):
        return (
            f"{row['Date']}  ·  {row['Action']}  ·  "
            f"Qty {row['Qty']:,.0f}  ·  ₹{row['Price']:,.2f}"
            + (f"  ·  {row['Notes'][:30]}" if row["Notes"] else "")
        )

    options        = {_label(r): i for i, r in enumerate(rows)}
    selected_label = st.selectbox("Select record", list(options.keys()),
                                  label_visibility="collapsed")
    selected_idx   = options[selected_label]
    selected_row   = rows[selected_idx]
    pk, sk         = selected_row["_pk"], selected_row["_sk"]
    action         = selected_row["Action"]
    act_colour     = ACTION_COLOURS.get(action, GREY)

    section_header("Step 4 — Edit or delete")
    st.markdown(
        f'<div style="background:{CARD_BG};border:1px solid {BORDER};border-radius:10px;'
        f'padding:14px 18px;margin-bottom:20px;display:flex;gap:24px;flex-wrap:wrap">'
        f'<span style="background:{act_colour}22;color:{act_colour};border:1px solid {act_colour}55;'
        f'border-radius:6px;padding:3px 10px;font-weight:700">{action}</span>'
        f'<span style="color:#6B7280">{selected_row["Date"]}</span>'
        f'<span style="color:#111827">Qty: {selected_row["Qty"]:,.0f}</span>'
        f'<span style="color:#111827">₹{selected_row["Price"]:,.4f}</span>'
        f'<span style="color:#6B7280;font-size:0.85rem;font-style:italic">{sk}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    tab_edit, tab_del = st.tabs(["✏️  Edit", "🗑️  Delete"])

    with tab_edit:
        # Symbol field — outside form so ticker search works live
        current_symbol = selected_row.get("Symbol", selected_symbol)
        sym_typed = st.text_input(
            "Symbol",
            value=st.session_state.get("edit_sym_input", current_symbol),
            key="edit_symbol_input",
            help="Change the ticker symbol. Type to search the NSE/BSE master list.",
        )
        sym_typed_upper = sym_typed.strip().upper()

        if sym_typed_upper and sym_typed_upper != current_symbol:
            cache_key = f"edit_ticker_{sym_typed_upper}"
            if cache_key not in st.session_state:
                st.session_state[cache_key] = search_tickers(sym_typed_upper, limit=6)
            sugg = st.session_state.get(cache_key, [])
            if sugg:
                st.caption(f"Matches — click to select:")
                scols = st.columns(min(len(sugg), 3))
                for idx, s in enumerate(sugg[:6]):
                    with scols[idx % 3]:
                        cname = s["company_name"][:24]
                        if st.button(
                            s["symbol"] + "  " + cname,
                            key=f"edit_sugg_{s['symbol']}_{idx}",
                            width="stretch",
                        ):
                            st.session_state["edit_sym_confirmed"] = s["symbol"]
                            st.session_state["edit_sym_input"]     = s["symbol"]
                            st.rerun()

        confirmed_sym = st.session_state.get("edit_sym_confirmed", "")
        if confirmed_sym and confirmed_sym == sym_typed_upper:
            st.success(f"Confirmed: {confirmed_sym}")
            new_symbol = confirmed_sym
        else:
            new_symbol = sym_typed_upper
            if confirmed_sym and confirmed_sym != sym_typed_upper:
                st.session_state.pop("edit_sym_confirmed", None)

        symbol_changed = bool(new_symbol and new_symbol != current_symbol)

        with st.form("edit_form"):
            e1, e2 = st.columns(2)
            with e1:
                new_date = st.date_input("Date",
                    value=date.fromisoformat(selected_row["Date"]),
                    max_value=date.today())
            with e2:
                st.text_input("Action (read-only)", value=action, disabled=True)

            e3, e4, e5 = st.columns(3)
            with e3:
                new_qty = st.number_input("Qty", min_value=0.01,
                    value=float(selected_row["Qty"]), step=1.0, format="%.2f")
            with e4:
                new_price = st.number_input("Price", min_value=0.0,
                    value=float(selected_row["Price"]), step=0.25, format="%.4f",
                    disabled=(action=="BONUS"))
            with e5:
                new_charges = st.number_input("Charges", min_value=0.0,
                    value=float(selected_row["Charges"]), step=1.0, format="%.2f",
                    disabled=(action in ("DIVIDEND","BONUS")))

            new_notes = st.text_input("Notes", value=selected_row["Notes"], max_chars=200)

            changes = {}
            if symbol_changed:
                changes["symbol"] = new_symbol
            if new_date.isoformat() != selected_row["Date"]:
                changes["trade_date"] = new_date.isoformat()
            if abs(new_qty - float(selected_row["Qty"])) > 0.001:
                changes["qty"] = new_qty
            if action != "BONUS" and abs(new_price - float(selected_row["Price"])) > 0.0001:
                changes["price"] = new_price
            if action not in ("DIVIDEND","BONUS") and abs(new_charges - float(selected_row["Charges"])) > 0.001:
                changes["charges"] = new_charges
            if new_notes.strip() != selected_row["Notes"].strip():
                changes["notes"] = new_notes.strip()

            if changes:
                change_labels = []
                if "symbol" in changes:
                    change_labels.append(f"symbol: {current_symbol} to {new_symbol}")
                change_labels += [k for k in changes if k != "symbol"]
                st.markdown(
                    f'<div style="background:{TEAL}10;border:1px solid {TEAL}40;'
                    f'border-radius:8px;padding:10px 14px;margin:8px 0;font-size:0.85rem">'
                    f'<strong style="color:{TEAL}">Changes:</strong> '
                    + ", ".join(f"<code>{c}</code>" for c in change_labels) + "</div>",
                    unsafe_allow_html=True,
                )

            save_clicked = st.form_submit_button("Save changes", type="primary",
                width="stretch", disabled=(not changes))

        if save_clicked and changes:
            err = (
                f"Price cannot be 0 for {action}."
                if "price" in changes and changes["price"] == 0 and action != "BONUS"
                else ("Quantity must be > 0." if "qty" in changes and changes["qty"] <= 0 else None)
            )
            if err:
                st.error(err)
            else:
                try:
                    if "symbol" in changes:
                        rename_symbol_record(pk, sk, new_symbol, selected_row["_raw"])
                        msg = f"Symbol renamed {current_symbol} to {new_symbol}"
                    else:
                        update_record(pk, sk, changes)
                        keys = ", ".join(k for k in changes)
                        msg = f"Updated: {keys}"
                    st.cache_data.clear()
                    st.session_state.pop("edit_sym_confirmed", None)
                    st.session_state.pop("edit_sym_input", None)
                    st.success(msg)
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

    with tab_del:
        st.markdown(
            f'<div style="background:{RED}10;border:1px solid {RED}40;border-radius:10px;'
            f'padding:14px 18px;margin-bottom:20px">'
            f'<div style="color:{RED};font-weight:700;margin-bottom:6px">⚠️ Permanent deletion</div>'
            f'<div style="font-size:0.9rem">Deletes the <strong>{action}</strong> record for '
            f'<strong>{selected_symbol}</strong> on <strong>{selected_row["Date"]}</strong>.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        confirm_input = st.text_input(
            "Type the symbol to confirm",
            placeholder=f"Type {selected_symbol} to confirm",
            label_visibility="collapsed",
        )
        if st.button("🗑️ Delete this record", type="primary",
                     disabled=(confirm_input.strip().upper() != selected_symbol),
                     width='content') and confirm_input.strip().upper() == selected_symbol:
            try:
                delete_record(pk, sk)
                st.cache_data.clear()
                st.success(f"✅ Deleted {action} on {selected_row['Date']} for {selected_symbol}.")
                st.rerun()
            except Exception as e:
                st.error(f"Delete failed: `{e}`")
        if confirm_input and confirm_input.strip().upper() != selected_symbol:
            st.caption(f"Type exactly `{selected_symbol}` to enable deletion.")
