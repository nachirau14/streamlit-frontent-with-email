"""
utils/email_alerts.py
Sends trade activity notifications via AWS SES from the Streamlit dashboard.

Config (add to Streamlit secrets):

    [email]
    enabled        = true
    from_address   = "portfolio@yourdomain.com"   # must be SES-verified
    to_address     = "you@gmail.com"              # recipient
    aws_region     = "ap-south-1"                 # SES region (can differ from DynamoDB region)

The IAM user whose credentials are in [aws] needs:
    ses:SendEmail on arn:aws:ses:REGION:ACCOUNT_ID:identity/from_address

Notifications are fire-and-forget — failures are logged but never raise,
so a broken email config never blocks a trade write.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────

def _email_config() -> dict | None:
    """
    Return email config, or None if disabled / not configured.
    SES credentials come from secrets; enabled flag and to_address
    come from DynamoDB (editable at runtime via the Email Config page).
    Falls back to secrets for backwards compatibility.
    """
    try:
        import streamlit as st

        # SES credentials always from secrets
        sec = st.secrets.get("email", {})
        from_addr = str(sec.get("from_address", "")).strip()
        region    = str(sec.get("aws_region", "ap-south-1")).strip()

        if not from_addr:
            return None   # SES sender not configured in secrets

        # Enabled flag and recipient from DynamoDB (runtime-editable)
        try:
            from utils.data import load_email_config as _load_cfg
            db_cfg = _load_cfg()
        except Exception:
            db_cfg = {}

        # If DynamoDB has a setting, use it; fall back to secrets
        enabled  = db_cfg.get("enabled", sec.get("enabled", False))
        to_addr  = (db_cfg.get("to_address") or
                    str(sec.get("to_address", "")).strip())

        if not enabled or not to_addr:
            return None

        return {
            "from":     from_addr,
            "to":       to_addr,
            "region":   region,
            "prefs":    db_cfg,   # full prefs for alert-type gating
        }
    except Exception:
        return None


def _alert_enabled(alert_key: str) -> bool:
    """Check whether a specific alert type is enabled."""
    try:
        import streamlit as st
        from utils.data import load_email_config as _load_cfg
        prefs = _load_cfg()
        return bool(prefs.get(alert_key, True))
    except Exception:
        return True   # default on if config unreadable


def _ses_client(cfg: dict):
    """Return a boto3 SES client using the credentials from [aws] secrets."""
    import boto3
    import streamlit as st
    aws = st.secrets["aws"]
    return boto3.client(
        "ses",
        region_name=cfg["region"],
        aws_access_key_id=str(aws["access_key_id"]),
        aws_secret_access_key=str(aws["secret_access_key"]),
    )


# ── HTML helpers ──────────────────────────────────────────────────────────────

_ACTION_COLOUR = {
    "BUY":       "#00A88A",
    "SELL":      "#E53E3E",
    "DIVIDEND":  "#0891B2",
    "BONUS":     "#7C3AED",
    "RIGHTS":    "#D97706",
    "SPLIT":     "#0284C7",
    "MERGER":    "#9333EA",
    "DEMERGER":  "#EA580C",
    "DELETE":    "#DC2626",
    "EDIT":      "#D97706",
}

_BASE_STYLE = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #F9FAFB; margin: 0; padding: 24px; color: #111827; }
.card { background: #FFFFFF; border-radius: 12px; padding: 28px 32px;
        max-width: 560px; margin: 0 auto;
        box-shadow: 0 1px 6px rgba(0,0,0,0.08); }
.header { font-size: 1.35rem; font-weight: 700; margin-bottom: 4px; }
.sub    { color: #6B7280; font-size: 0.85rem; margin-bottom: 24px; }
.badge  { display: inline-block; padding: 4px 12px; border-radius: 6px;
          font-size: 0.8rem; font-weight: 700; letter-spacing: 0.04em; }
table   { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
td      { padding: 8px 0; border-bottom: 1px solid #F3F4F6; }
td:last-child { text-align: right; font-weight: 600; color: #111827; }
td:first-child { color: #6B7280; }
.footer { margin-top: 20px; font-size: 0.78rem; color: #9CA3AF; text-align: center; }
"""


def _badge(action: str) -> str:
    colour = _ACTION_COLOUR.get(action.upper(), "#6B7280")
    return (f'<span class="badge" style="background:{colour}18;color:{colour};'
            f'border:1px solid {colour}44">{action.upper()}</span>')


def _html_trade_email(event_type: str, record: dict, extra: str = "") -> tuple[str, str]:
    """Return (subject, html_body) for a trade notification."""
    action = record.get("action", event_type).upper()
    symbol = record.get("symbol", "—").upper()
    ts     = datetime.now().strftime("%d %b %Y, %I:%M %p")

    colour = _ACTION_COLOUR.get(action, "#6B7280")
    badge  = _badge(action)

    subject = f"[XIRR Tracker] {event_type}: {action} {symbol}"

    qty     = record.get("qty",    "—")
    price   = record.get("price",  "—")
    charges = record.get("charges", 0)
    notes   = record.get("notes",  "—") or "—"
    broker  = record.get("broker", "—") or "—"
    sector  = record.get("sector", "—") or "—"
    tdate   = record.get("trade_date", "—")

    def fmt_inr(v):
        try:
            v = float(v)
            if v >= 1e7: return f"₹{v/1e7:.2f} Cr"
            if v >= 1e5: return f"₹{v/1e5:.2f} L"
            return f"₹{v:,.2f}"
        except Exception:
            return str(v)

    body = f"""<!DOCTYPE html><html><head><style>{_BASE_STYLE}</style></head><body>
<div class="card">
  <div class="header" style="color:{colour}">Portfolio XIRR Tracker</div>
  <div class="sub">{ts}</div>

  <div style="margin-bottom:20px">
    {badge}
    <span style="font-size:1.2rem;font-weight:700;margin-left:10px">{symbol}</span>
  </div>

  <table>
    <tr><td>Date</td>         <td>{tdate}</td></tr>
    <tr><td>Quantity</td>     <td>{(f"{qty:,.0f}") if isinstance(qty,(int,float)) else str(qty)}</td></tr>
    <tr><td>Price</td>        <td>{fmt_inr(price)}</td></tr>
    <tr><td>Charges</td>      <td>{fmt_inr(charges)}</td></tr>
    <tr><td>Broker</td>       <td>{broker}</td></tr>
    <tr><td>Sector</td>       <td>{sector}</td></tr>
    <tr><td>Notes</td>        <td>{notes}</td></tr>
  </table>

  {f'<p style="margin-top:16px;font-size:0.88rem;color:#6B7280">{extra}</p>' if extra else ""}

  <div class="footer">Sent by Portfolio XIRR Tracker · AWS SES</div>
</div>
</body></html>"""

    return subject, body


def _html_delete_email(pk: str, sk: str, symbol: str = "") -> tuple[str, str]:
    ts      = datetime.now().strftime("%d %b %Y, %I:%M %p")
    subject = f"[XIRR Tracker] DELETE: record removed{' for ' + symbol if symbol else ''}"
    body = f"""<!DOCTYPE html><html><head><style>{_BASE_STYLE}</style></head><body>
<div class="card">
  <div class="header" style="color:#DC2626">Portfolio XIRR Tracker</div>
  <div class="sub">{ts}</div>
  <div style="margin-bottom:20px">{_badge("DELETE")}
    {"<span style='font-size:1.2rem;font-weight:700;margin-left:10px'>" + symbol + "</span>" if symbol else ""}
  </div>
  <table>
    <tr><td>Record PK</td>  <td style="font-family:monospace;font-size:0.82rem">{pk}</td></tr>
    <tr><td>Record SK</td>  <td style="font-family:monospace;font-size:0.82rem">{sk}</td></tr>
  </table>
  <div class="footer">Sent by Portfolio XIRR Tracker · AWS SES</div>
</div></body></html>"""
    return subject, body


def _html_bulk_email(written: int, errors: int, symbols: list[str]) -> tuple[str, str]:
    ts      = datetime.now().strftime("%d %b %Y, %I:%M %p")
    subject = f"[XIRR Tracker] BULK UPLOAD: {written} records added"
    sym_list = ", ".join(symbols[:20]) + ("…" if len(symbols) > 20 else "")
    body = f"""<!DOCTYPE html><html><head><style>{_BASE_STYLE}</style></head><body>
<div class="card">
  <div class="header" style="color:#00A88A">Portfolio XIRR Tracker</div>
  <div class="sub">{ts}</div>
  <div style="margin-bottom:20px">{_badge("BUY")}
    <span style="font-size:1rem;margin-left:10px">Bulk Upload Complete</span>
  </div>
  <table>
    <tr><td>Records written</td>  <td>{written:,}</td></tr>
    <tr><td>Errors</td>           <td>{errors}</td></tr>
    <tr><td>Scrips</td>           <td>{sym_list}</td></tr>
  </table>
  <div class="footer">Sent by Portfolio XIRR Tracker · AWS SES</div>
</div></body></html>"""
    return subject, body


# ── Public send functions ─────────────────────────────────────────────────────

def _send(subject: str, html: str) -> None:
    """Internal: send via SES. Silently logs on failure."""
    cfg = _email_config()
    if not cfg:
        return
    try:
        client = _ses_client(cfg)
        client.send_email(
            Source=cfg["from"],
            Destination={"ToAddresses": [cfg["to"]]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body":    {"Html": {"Data": html, "Charset": "UTF-8"}},
            },
        )
        logger.info("Email sent: %s", subject)
    except Exception as exc:
        logger.warning("Email send failed (non-fatal): %s", exc)


def notify_trade_added(record: dict) -> None:
    """Call after a single trade is successfully written to DynamoDB."""
    if not _alert_enabled("alert_trade_add"):
        return
    subject, html = _html_trade_email("TRADE ADDED", record)
    _send(subject, html)


def notify_trade_edited(record: dict, old_values: dict | None = None) -> None:
    """Call after a trade is successfully updated in DynamoDB."""
    if not _alert_enabled("alert_trade_edit"):
        return
    extra = ""
    if old_values:
        changes = [f"{k}: {old_values[k]} → {record.get(k, '?')}"
                   for k in old_values if old_values[k] != record.get(k)]
        if changes:
            extra = "Changes: " + " · ".join(changes)
    subject, html = _html_trade_email("TRADE EDITED", record, extra=extra)
    _send(subject, html)


def notify_trade_deleted(pk: str, sk: str, symbol: str = "") -> None:
    """Call after a trade record is successfully deleted from DynamoDB."""
    if not _alert_enabled("alert_trade_del"):
        return
    subject, html = _html_delete_email(pk, sk, symbol)
    _send(subject, html)


def notify_bulk_upload(written: int, errors: int, symbols: list[str]) -> None:
    """Call after a bulk upload completes."""
    if not _alert_enabled("alert_bulk"):
        return
    subject, html = _html_bulk_email(written, errors, symbols)
    _send(subject, html)
