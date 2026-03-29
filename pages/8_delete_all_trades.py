"""
pages/7_delete_all_trades.py
Delete ALL records from both the trades table and the XIRR table.
Requires typed confirmation before anything is touched.
"""
import streamlit as st
from boto3.dynamodb.conditions import Attr

from utils.data import load_all_trades, _get_table
from utils.ui import TEAL, RED, GREY, BORDER, CARD_BG

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.3rem;font-weight:800;color:#00A88A;padding:16px 0 24px">'
        "📈 XIRR Tracker</div>",
        unsafe_allow_html=True,
    )


def _scan_all_keys(table) -> list[dict]:
    """Full table scan returning only pk+sk for every item."""
    keys     = []
    response = table.scan(ProjectionExpression="pk, sk")
    keys    += [{"pk": i["pk"], "sk": i["sk"]} for i in response.get("Items", [])]
    while response.get("LastEvaluatedKey"):
        response = table.scan(
            ProjectionExpression="pk, sk",
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        keys += [{"pk": i["pk"], "sk": i["sk"]} for i in response.get("Items", [])]
    return keys


def _batch_delete(table, keys: list[dict], progress_offset: int,
                  progress_total: int, progress_bar) -> tuple[int, list[str]]:
    """Delete a list of {pk, sk} dicts in batches of 25. Returns (deleted, errors)."""
    deleted    = 0
    errors     = []
    chunk_size = 25

    for i in range(0, len(keys), chunk_size):
        chunk = keys[i:i + chunk_size]
        try:
            with table.batch_writer() as batch:
                for key in chunk:
                    batch.delete_item(Key=key)
            deleted += len(chunk)
        except Exception as e:
            errors.append(str(e))

        done = progress_offset + deleted
        pct  = min(int(done / progress_total * 100), 99)
        progress_bar.progress(pct, text=f"Deleted {done:,} / {progress_total:,}…")

    return deleted, errors


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:{RED}10;border:1px solid {RED}40;border-radius:12px;
            padding:20px 24px;margin-bottom:28px">
    <div style="font-size:1.6rem;font-weight:800;color:{RED};margin-bottom:6px">
        🗑️ Delete All Trades &amp; XIRR Data
    </div>
    <div style="color:#111827;font-size:0.95rem">
        This will permanently delete <strong>every record</strong> in both the
        trades table and the XIRR snapshots table. This cannot be undone.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Load current counts ───────────────────────────────────────────────────────
with st.spinner("Counting records in both tables…"):
    try:
        trades_tbl     = _get_table("trades_table")
        xirr_tbl       = _get_table("xirr_table")
        trades_keys    = _scan_all_keys(trades_tbl)
        xirr_keys      = _scan_all_keys(xirr_tbl)
        all_trades_map = load_all_trades()
    except Exception as e:
        st.error(f"Could not load table data: `{e}`")
        st.stop()

total_trades = len(trades_keys)
total_xirr   = len(xirr_keys)
total_scrips = len(all_trades_map)
grand_total  = total_trades + total_xirr

if grand_total == 0:
    st.info("Both tables are already empty — nothing to delete.")
    st.stop()

# ── Summary ───────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:{CARD_BG};border:1px solid {BORDER};border-radius:10px;
            padding:18px 22px;margin-bottom:24px">
    <div style="color:{GREY};font-size:0.8rem;text-transform:uppercase;
                letter-spacing:0.08em;margin-bottom:14px">What will be deleted</div>
    <div style="display:flex;gap:40px;flex-wrap:wrap">
        <div>
            <div style="font-size:2rem;font-weight:800;color:{RED}">{total_trades:,}</div>
            <div style="color:{GREY};font-size:0.85rem">Trade records</div>
        </div>
        <div>
            <div style="font-size:2rem;font-weight:800;color:{RED}">{total_xirr:,}</div>
            <div style="color:{GREY};font-size:0.85rem">XIRR snapshots</div>
        </div>
        <div>
            <div style="font-size:2rem;font-weight:800;color:{RED}">{total_scrips:,}</div>
            <div style="color:{GREY};font-size:0.85rem">Scrips affected</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Confirmation ──────────────────────────────────────────────────────────────
CONFIRM_PHRASE = "delete all trades"

st.markdown(
    f'<div style="color:#111827;margin-bottom:8px;font-size:0.95rem">'
    f'Type <code style="color:{RED};font-size:0.95rem">{CONFIRM_PHRASE}</code> to confirm:</div>',
    unsafe_allow_html=True,
)

confirm_input = st.text_input(
    "Confirmation phrase",
    placeholder=CONFIRM_PHRASE,
    label_visibility="collapsed",
)

confirmed = confirm_input.strip().lower() == CONFIRM_PHRASE

if confirm_input and not confirmed:
    st.caption(f"Type exactly: **{CONFIRM_PHRASE}**")

st.markdown("<div style='height:8px'/>", unsafe_allow_html=True)

delete_clicked = st.button(
    f"🗑️ Delete all {grand_total:,} records",
    type="primary",
    disabled=not confirmed,
    use_container_width=True,
)

# ── Delete both tables ────────────────────────────────────────────────────────
if delete_clicked and confirmed:
    all_errors = []
    progress   = st.progress(0, text="Starting…")

    # Step 1: trades table
    progress.progress(0, text=f"Deleting {total_trades:,} trade records…")
    t_deleted, t_errors = _batch_delete(
        trades_tbl, trades_keys,
        progress_offset=0,
        progress_total=grand_total,
        progress_bar=progress,
    )
    all_errors.extend([f"Trades — {e}" for e in t_errors])

    # Step 2: XIRR table
    progress.progress(
        min(int(t_deleted / grand_total * 100), 99),
        text=f"Deleting {total_xirr:,} XIRR snapshots…",
    )
    x_deleted, x_errors = _batch_delete(
        xirr_tbl, xirr_keys,
        progress_offset=t_deleted,
        progress_total=grand_total,
        progress_bar=progress,
    )
    all_errors.extend([f"XIRR — {e}" for e in x_errors])

    progress.progress(100, text="Done")
    st.cache_data.clear()

    if all_errors:
        st.warning(
            f"Deleted {t_deleted:,} trade records and {x_deleted:,} XIRR snapshots "
            f"with {len(all_errors)} error(s):"
        )
        for e in all_errors:
            st.markdown(f"- `{e}`")
    else:
        st.success(
            f"✅ Deleted **{t_deleted:,} trade records** and "
            f"**{x_deleted:,} XIRR snapshots** across {total_scrips} scrips."
        )
        st.rerun()
