"""
pages/5_bulk_upload.py
Bulk upload trades from a CSV file — appends to existing DynamoDB records.
"""
import streamlit as st
import pandas as pd
import csv
import io
import re
from datetime import date

from utils.data import batch_put_records, VALID_ACTIONS
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

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:4px">Bulk Upload Trades</h1>
<div style="color:#6B7280;margin-bottom:24px">
    Upload a CSV file to append trades to the portfolio. Existing records are never
    overwritten — every row creates a new entry with a unique key.
</div>
""", unsafe_allow_html=True)


# ── CSV spec ──────────────────────────────────────────────────────────────────
with st.expander("📋 CSV format specification", expanded=False):
    st.markdown("""
**Required columns** (header row mandatory):

| Column | Type | Notes |
|---|---|---|
| `symbol` | text | NSE ticker e.g. `RELIANCE` |
| `trade_date` | date | ISO format `YYYY-MM-DD` |
| `action` | text | `BUY`, `SELL`, `DIVIDEND`, `BONUS`, or `RIGHTS` |
| `qty` | number | Shares bought/sold/held/allotted |
| `price` | number | Price per share in ₹ (use `0` for BONUS) |
| `charges` | number | Optional brokerage + charges in ₹ (default 0) |
| `notes` | text | Optional free-text |
| `broker` | text | Optional — broker key e.g. `ZERODHA`, `GROWW`. Must match a key in Manage Brokers |
| `sector` | text | Optional — NSE sector e.g. `IT`, `BANKING`, `PHARMA` |

**Rules:**
- Lines starting with `#` are treated as comments and ignored
- `BONUS` records must have `price = 0`
- `DIVIDEND` and `BONUS` records should have `charges = 0`
- Dates must be `YYYY-MM-DD`
- All rows are **appended** — duplicates in the CSV will create duplicate records
    """)
    st.markdown("**Sample CSV:**")
    st.code(
        "symbol,trade_date,action,qty,price,charges,notes,broker,sector\n"
        "RELIANCE,2024-01-15,BUY,50,2950.00,42.50,Added on dip\n"
        "TCS,2024-03-28,DIVIDEND,50,28.00,0.00,FY24 final dividend\n"
        "WIPRO,2024-02-10,BONUS,133,0.00,0.00,1:1 bonus issue\n"
        "NTPC,2024-01-20,RIGHTS,28,135.00,5.00,Rights issue",
        language="csv",
    )


# ── CSV validation helpers ────────────────────────────────────────────────────
REQUIRED_COLS = {"symbol", "trade_date", "action", "qty", "price"}

def _parse_csv(content: str) -> tuple[list[dict], list[str]]:
    """Parse and validate CSV content. Returns (valid_rows, errors)."""
    # Strip comment lines
    lines = [ln for ln in content.splitlines(keepends=True)
             if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return [], ["File is empty or contains only comments."]

    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        return [], ["Could not read header row."]

    # Normalise header names
    reader.fieldnames = [h.strip().lower() for h in reader.fieldnames]

    rows, errors = [], []
    for i, row in enumerate(reader, start=2):
        row = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k}
        if not any(row.values()):
            continue

        # Required columns
        missing = REQUIRED_COLS - set(row.keys())
        if missing:
            errors.append(f"Row {i}: missing columns {missing}")
            continue

        action = row.get("action", "").upper()
        symbol = row.get("symbol", "").strip().upper()

        if action not in VALID_ACTIONS:
            errors.append(f"Row {i} ({symbol}): invalid action '{row['action']}' — "
                          f"must be one of {sorted(VALID_ACTIONS)}")
            continue

        # Date
        if not re.match(r"\d{4}-\d{2}-\d{2}$", row.get("trade_date", "")):
            errors.append(f"Row {i} ({symbol}): trade_date '{row['trade_date']}' "
                          "must be YYYY-MM-DD")
            continue

        # Numeric fields
        try:
            qty = float(row["qty"])
            if qty <= 0:
                raise ValueError("must be > 0")
        except ValueError as e:
            errors.append(f"Row {i} ({symbol}): qty '{row['qty']}' invalid — {e}")
            continue

        try:
            price = float(row["price"])
            if price < 0:
                raise ValueError("cannot be negative")
            if action == "BONUS" and price != 0:
                errors.append(f"Row {i} ({symbol}): BONUS price must be 0")
                continue
            if action != "BONUS" and price == 0:
                errors.append(f"Row {i} ({symbol}): price cannot be 0 for {action}")
                continue
        except ValueError as e:
            errors.append(f"Row {i} ({symbol}): price '{row['price']}' invalid — {e}")
            continue

        charges = 0.0
        if row.get("charges"):
            try:
                charges = float(row["charges"])
            except ValueError:
                errors.append(f"Row {i} ({symbol}): charges '{row['charges']}' invalid")
                continue

        rows.append({
            "symbol":     symbol,
            "trade_date": row["trade_date"],
            "action":     action,
            "qty":        qty,
            "price":      price,
            "charges":    charges,
            "notes":      row.get("notes", ""),
            "broker":     row.get("broker", "").strip().upper(),
            "sector":     row.get("sector", "").strip().upper(),
        })

    return rows, errors


def _build_preview_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Symbol":     r["symbol"],
        "Date":       r["trade_date"],
        "Action":     r["action"],
        "Qty":        r["qty"],
        "Price (Rs)": r["price"],
        "Charges":    r["charges"],
        "Broker":     r.get("broker", ""),
        "Sector":     r.get("sector", ""),
        "Notes":      r["notes"],
    } for r in rows])


# ── File upload ───────────────────────────────────────────────────────────────
section_header("Upload CSV")

uploaded = st.file_uploader(
    "Choose a CSV file",
    type=["csv"],
    help="Max 5 MB. All rows are appended — existing records are never deleted.",
    label_visibility="collapsed",
)

if uploaded is None:
    st.info("Upload a CSV file above to get started. See the format specification above.")
    st.stop()

# Parse
raw_content = uploaded.read().decode("utf-8-sig", errors="replace")
rows, errors = _parse_csv(raw_content)


# ── Validation results ────────────────────────────────────────────────────────
section_header("Validation Results")

c1, c2, c3 = st.columns(3)
c1.metric("Total rows parsed",  len(rows) + len(errors))
c2.metric("Valid rows",          len(rows),   delta=None)
c3.metric("Errors",              len(errors), delta=None)

if errors:
    with st.expander(f"⚠️ {len(errors)} validation error(s) — these rows will be skipped",
                     expanded=True):
        for e in errors:
            st.markdown(f"- {e}")

if not rows:
    st.error("No valid rows found. Fix the errors above and re-upload.")
    st.stop()


# ── Preview ───────────────────────────────────────────────────────────────────
section_header("Preview", f"{len(rows)} rows ready to upload")

from collections import Counter
action_counts = Counter(r["action"] for r in rows)
symbol_counts = Counter(r["symbol"] for r in rows)

ac1, ac2, ac3, ac4, ac5 = st.columns(5)
for col, action in zip([ac1, ac2, ac3, ac4, ac5], ["BUY", "SELL", "DIVIDEND", "BONUS", "RIGHTS"]):
    colour = ACTION_COLOURS.get(action, GREY)
    n = action_counts.get(action, 0)
    col.markdown(
        f'<div style="background:{CARD_BG};border:1px solid {colour}44;border-radius:10px;'
        f'padding:12px;text-align:center">'
        f'<div style="color:{colour};font-weight:700;font-size:1.4rem">{n}</div>'
        f'<div style="color:{GREY};font-size:0.78rem">{action}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:12px'/>", unsafe_allow_html=True)

# Styled preview table
df_preview = _build_preview_df(rows)

def _style_action(val):
    c = ACTION_COLOURS.get(str(val).upper(), GREY)
    return f"color: {c}; font-weight: 600"

styled = (
    df_preview.style
    .format({
        "Qty":        lambda x: f"{x:,.0f}",
        "Price (Rs)": lambda x: f"Rs.{x:,.4f}",
        "Charges":    lambda x: f"Rs.{x:,.2f}" if x else "-",
    })
    .applymap(_style_action, subset=["Action"])
    .hide(axis="index")
)
st.dataframe(styled, use_container_width=True, height=min(400, 60 + len(rows) * 35))


# ── Scrip breakdown ───────────────────────────────────────────────────────────
with st.expander("📊 Breakdown by scrip"):
    scrip_rows = []
    for sym, count in sorted(symbol_counts.items()):
        sym_rows   = [r for r in rows if r["symbol"] == sym]
        acts       = Counter(r["action"] for r in sym_rows)
        scrip_rows.append({
            "Symbol":   sym,
            "Records":  count,
            "BUY":      acts.get("BUY", 0),
            "SELL":     acts.get("SELL", 0),
            "DIVIDEND": acts.get("DIVIDEND", 0),
            "BONUS":    acts.get("BONUS", 0),
            "RIGHTS":   acts.get("RIGHTS", 0),
        })
    st.dataframe(pd.DataFrame(scrip_rows).set_index("Symbol"), use_container_width=True)


# ── Upload confirmation ───────────────────────────────────────────────────────
section_header("Confirm Upload")

st.markdown(
    f'<div style="background:{CARD_BG};border:1px solid {BORDER};border-radius:10px;'
    f'padding:16px 20px;margin-bottom:20px">'
    f'<div style="color:#111827;font-size:0.95rem">'
    f'You are about to append <strong style="color:{TEAL}">{len(rows)} records</strong> '
    f'across <strong style="color:{TEAL}">{len(symbol_counts)} scrips</strong> '
    f'to the trades table.<br>'
    f'<span style="color:{GREY};font-size:0.85rem">'
    f'Existing records will not be modified or deleted. '
    f'XIRR will update at next market close when Lambda runs.</span>'
    f'</div></div>',
    unsafe_allow_html=True,
)

col_btn, col_note = st.columns([1, 3])
with col_btn:
    upload_clicked = st.button(
        f"📤 Upload {len(rows)} records",
        type="primary",
        use_container_width=True,
    )

if upload_clicked:
    progress = st.progress(0, text="Uploading…")
    try:
        written, write_errors = batch_put_records(rows)
        progress.progress(100, text="Done")

        if write_errors:
            st.warning(f"Uploaded {written} records with {len(write_errors)} error(s):")
            for e in write_errors:
                st.markdown(f"- {e}")
        else:
            st.success(
                f"✅ Successfully uploaded **{written} records** "
                f"across **{len(symbol_counts)} scrips**."
            )
            st.balloons()

    except Exception as e:
        progress.empty()
        st.error(f"Upload failed: `{type(e).__name__}: {e}`")
