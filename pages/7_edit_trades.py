"""
pages/6_edit_trades.py
Edit or delete individual trade records from the DynamoDB trades table.
"""
import streamlit as st
import pandas as pd
from datetime import date, datetime

from utils.data import (
    load_all_trades, load_trades_for_scrip,
    delete_record, update_record,
    VALID_ACTIONS,
)
from utils.ui import (
    section_header, ACTION_COLOURS,
    TEAL, RED, GREY, BORDER, CARD_BG, CYAN, PURPLE, ORANGE,
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

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:4px">Edit Trades</h1>
<div style="color:#6B7280;margin-bottom:24px">
    Find, edit, or delete individual trade records. Changes take effect immediately in DynamoDB.
    XIRR recalculates at next market close.
</div>
""", unsafe_allow_html=True)


# ── Load all symbols ──────────────────────────────────────────────────────────
with st.spinner("Loading trades…"):
    try:
        all_trades = load_all_trades()
    except Exception as e:
        st.error(f"Could not load trades: `{e}`")
        st.stop()

if not all_trades:
    st.warning("No trade records found in the table.")
    st.stop()

symbols = sorted(all_trades.keys())


# ── Symbol selector ───────────────────────────────────────────────────────────
section_header("Step 1 — Select a scrip")

col_sym, col_filter = st.columns([2, 3])
with col_sym:
    selected_symbol = st.selectbox(
        "Scrip",
        symbols,
        label_visibility="collapsed",
        format_func=lambda s: f"  {s}  ({len(all_trades.get(s, []))} records)",
    )

# Reload from DynamoDB (not cache) so edits are reflected immediately
trades = load_trades_for_scrip(selected_symbol)

if not trades:
    st.warning(f"No records found for {selected_symbol}.")
    st.stop()


# ── Build display dataframe ───────────────────────────────────────────────────
with col_filter:
    action_filter = st.multiselect(
        "Filter by action",
        options=sorted(VALID_ACTIONS),
        default=[],
        placeholder="All actions",
        label_visibility="collapsed",
    )

if action_filter:
    trades = [t for t in trades if t.get("action", "").upper() in action_filter]

if not trades:
    st.info("No records match the filter.")
    st.stop()

# ── Records table ─────────────────────────────────────────────────────────────
section_header("Step 2 — Select a record to edit or delete",
               f"{len(trades)} record(s) for {selected_symbol}")

rows = []
for t in sorted(trades, key=lambda x: x.get("trade_date", ""), reverse=True):
    rows.append({
        "_pk":        t.get("pk", ""),
        "_sk":        t.get("sk", ""),
        "Date":       t.get("trade_date", ""),
        "Action":     t.get("action", "").upper(),
        "Qty":        float(t.get("qty", 0)),
        "Price":      float(t.get("price", 0)),
        "Charges":    float(t.get("charges", 0)),
        "Notes":      t.get("notes", ""),
    })

df = pd.DataFrame(rows)

def _style_action(val):
    c = ACTION_COLOURS.get(str(val).upper(), GREY)
    return f"color: {c}; font-weight: 600"

display_df = df.drop(columns=["_pk", "_sk"])
styled = (
    display_df.style
    .format({
        "Qty":     lambda x: f"{x:,.0f}",
        "Price":   lambda x: f"Rs.{x:,.4f}",
        "Charges": lambda x: f"Rs.{x:,.2f}" if x else "-",
    })
    .map(_style_action, subset=["Action"])
    .hide(axis="index")
)
st.dataframe(styled, width='stretch', height=min(380, 60 + len(rows) * 35))


# ── Record picker ─────────────────────────────────────────────────────────────
section_header("Step 3 — Choose a record")

# Build readable labels for each record
def _label(row: dict) -> str:
    return (
        f"{row['Date']}  ·  {row['Action']}  ·  "
        f"Qty {row['Qty']:,.0f}  ·  Rs.{row['Price']:,.2f}"
        + (f"  ·  {row['Notes'][:30]}" if row["Notes"] else "")
    )

options = {_label(r): i for i, r in enumerate(rows)}

selected_label = st.selectbox(
    "Select record",
    list(options.keys()),
    label_visibility="collapsed",
)
selected_idx = options[selected_label]
selected_row = rows[selected_idx]
pk = selected_row["_pk"]
sk = selected_row["_sk"]


# ── Action: Edit or Delete ────────────────────────────────────────────────────
section_header("Step 4 — Edit or delete")

# Colour badge for current action
action      = selected_row["Action"]
act_colour  = ACTION_COLOURS.get(action, GREY)
st.markdown(
    f'<div style="background:{CARD_BG};border:1px solid {BORDER};border-radius:10px;'
    f'padding:14px 18px;margin-bottom:20px;display:flex;gap:24px;flex-wrap:wrap">'
    f'<span style="background:{act_colour}22;color:{act_colour};border:1px solid {act_colour}55;'
    f'border-radius:6px;padding:3px 10px;font-weight:700">{action}</span>'
    f'<span style="color:#6B7280">{selected_row["Date"]}</span>'
    f'<span style="color:#111827">Qty: {selected_row["Qty"]:,.0f}</span>'
    f'<span style="color:#111827">Price: Rs.{selected_row["Price"]:,.4f}</span>'
    f'<span style="color:#6B7280;font-size:0.85rem;font-style:italic">{sk}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

tab_edit, tab_delete = st.tabs(["✏️  Edit record", "🗑️  Delete record"])


# ── Edit tab ──────────────────────────────────────────────────────────────────
with tab_edit:
    st.markdown(
        f'<div style="color:{GREY};font-size:0.85rem;margin-bottom:16px">'
        'Edit any field below. Symbol and action cannot be changed — '
        'delete the record and re-add it instead.</div>',
        unsafe_allow_html=True,
    )

    with st.form("edit_form"):
        e1, e2 = st.columns(2)
        with e1:
            new_date = st.date_input(
                "Trade / ex-date",
                value=date.fromisoformat(selected_row["Date"]),
                max_value=date.today(),
            )
        with e2:
            # Action display only — not editable
            st.text_input("Action (read-only)", value=action, disabled=True)

        e3, e4, e5 = st.columns(3)
        with e3:
            new_qty = st.number_input(
                "Quantity",
                min_value=0.01,
                value=float(selected_row["Qty"]),
                step=1.0,
                format="%.2f",
            )
        with e4:
            new_price = st.number_input(
                "Price per share (Rs.)",
                min_value=0.0,
                value=float(selected_row["Price"]),
                step=0.25,
                format="%.4f",
                disabled=(action == "BONUS"),
                help="Price is always 0 for BONUS — not editable",
            )
        with e5:
            new_charges = st.number_input(
                "Charges (Rs.)",
                min_value=0.0,
                value=float(selected_row["Charges"]),
                step=1.0,
                format="%.2f",
                disabled=(action in ("DIVIDEND", "BONUS")),
            )

        new_notes = st.text_input(
            "Notes",
            value=selected_row["Notes"],
            max_chars=200,
        )

        # Show what's changed
        changes = {}
        if new_date.isoformat() != selected_row["Date"]:
            changes["trade_date"] = new_date.isoformat()
        if abs(new_qty - float(selected_row["Qty"])) > 0.001:
            changes["qty"] = new_qty
        if action != "BONUS" and abs(new_price - float(selected_row["Price"])) > 0.0001:
            changes["price"] = new_price
        if action not in ("DIVIDEND", "BONUS") and abs(new_charges - float(selected_row["Charges"])) > 0.001:
            changes["charges"] = new_charges
        if new_notes.strip() != selected_row["Notes"].strip():
            changes["notes"] = new_notes.strip()

        if changes:
            st.markdown(
                f'<div style="background:{TEAL}10;border:1px solid {TEAL}40;'
                f'border-radius:8px;padding:10px 14px;margin:8px 0;font-size:0.85rem">'
                f'<strong style="color:{TEAL}">Changes detected:</strong> '
                + ", ".join(f"<code>{k}</code>" for k in changes.keys())
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div style="color:{GREY};font-size:0.85rem;margin:8px 0">'
                'No changes detected.</div>',
                unsafe_allow_html=True,
            )

        save_clicked = st.form_submit_button(
            "💾 Save changes",
            type="primary",
            width='stretch',
            disabled=(not changes),
        )

    if save_clicked and changes:
        # Extra validation
        err = None
        if "price" in changes and changes["price"] == 0 and action != "BONUS":
            err = f"Price cannot be 0 for {action}."
        if "qty" in changes and changes["qty"] <= 0:
            err = "Quantity must be greater than 0."

        if err:
            st.error(f"✗ {err}")
        else:
            try:
                update_record(pk, sk, changes)
                st.cache_data.clear()
                st.success(
                    f"✅ Record updated. Changed: {', '.join(changes.keys())}"
                )
                st.rerun()
            except Exception as e:
                st.error(f"Update failed: `{type(e).__name__}: {e}`")


# ── Delete tab ────────────────────────────────────────────────────────────────
with tab_delete:
    st.markdown(
        f'<div style="background:{RED}10;border:1px solid {RED}40;border-radius:10px;'
        f'padding:14px 18px;margin-bottom:20px">'
        f'<div style="color:{RED};font-weight:700;margin-bottom:6px">⚠️ Permanent deletion</div>'
        f'<div style="color:#111827;font-size:0.9rem">'
        f'This will permanently delete the <strong>{action}</strong> record for '
        f'<strong>{selected_symbol}</strong> on <strong>{selected_row["Date"]}</strong>. '
        f'This cannot be undone. The XIRR for this scrip will update at next market close.'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("**Type the symbol to confirm deletion:**")
    confirm_input = st.text_input(
        "Type symbol to confirm",
        placeholder=f"Type {selected_symbol} to confirm",
        label_visibility="collapsed",
    )

    delete_clicked = st.button(
        f"🗑️ Delete this record",
        type="primary",
        disabled=(confirm_input.strip().upper() != selected_symbol),
        width='content',
    )

    if confirm_input and confirm_input.strip().upper() != selected_symbol:
        st.caption(f"Type exactly `{selected_symbol}` to enable the delete button.")

    if delete_clicked and confirm_input.strip().upper() == selected_symbol:
        try:
            delete_record(pk, sk)
            st.cache_data.clear()
            st.success(
                f"✅ Record deleted — {action} on {selected_row['Date']} "
                f"for {selected_symbol}."
            )
            st.rerun()
        except Exception as e:
            st.error(f"Delete failed: `{type(e).__name__}: {e}`")
