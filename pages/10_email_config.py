"""
pages/10_email_config.py
Email alert configuration — addresses, alert types, weekly digest schedule.
Settings are stored in DynamoDB and take effect immediately.
SES credentials (from/region) must be set in Streamlit Cloud Secrets.
"""
import streamlit as st

from utils.data import load_email_config, save_email_config
from utils.ui import section_header, TEAL, RED, GREY, BORDER, CARD_BG, ORANGE, CYAN

with st.sidebar:
    st.markdown(
        '<div style="font-size:1.3rem;font-weight:800;color:#00A88A;padding:16px 0 24px">'
        "📈 XIRR Tracker</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("""
<h1 style="font-size:1.8rem;font-weight:800;margin-bottom:4px">Email Alerts</h1>
<div style="color:#6B7280;margin-bottom:24px">
    Configure which events trigger email notifications and how often you
    receive portfolio digests. SES credentials are set in Streamlit secrets.
</div>
""", unsafe_allow_html=True)

# ── Read current config from DynamoDB ─────────────────────────────────────────
cfg = load_email_config()

# ── SES credential status (from secrets — read-only here) ─────────────────────
section_header("SES Sender Credentials", "Set in Streamlit Cloud Secrets — not editable here")

try:
    sec        = st.secrets.get("email", {})
    from_addr  = str(sec.get("from_address", "")).strip()
    ses_region = str(sec.get("aws_region", "ap-south-1")).strip()
    configured = bool(from_addr)
except Exception:
    from_addr  = ""
    ses_region = "ap-south-1"
    configured = False

if configured:
    st.success(f"✅ Sender configured: **{from_addr}** (region: {ses_region})")
else:
    st.warning(
        "⚠️ SES sender not configured. Add the following to Streamlit Cloud Secrets:\n\n"
        "```toml\n"
        "[email]\n"
        "from_address = \"portfolio@yourdomain.com\"  # must be SES-verified\n"
        "aws_region   = \"ap-south-1\"\n"
        "```\n\n"
        "Then verify the address in AWS SES → Verified identities."
    )

with st.expander("IAM permission required"):
    st.markdown(
        "The IAM user in `[aws]` secrets needs this permission:\n\n"
        "```json\n"
        "{\n"
        "  \"Effect\": \"Allow\",\n"
        '  "Action": ["ses:SendEmail", "ses:SendRawEmail"],\n'
        '  "Resource": "arn:aws:ses:ap-south-1:ACCOUNT_ID:identity/your@sender.com"\n'
        "}\n"
        "```\n\n"
        "If SES is in **sandbox mode** (new accounts), also verify the recipient "
        "address in AWS SES → Verified identities, or request production access."
    )

st.markdown("---")

# ── Main settings form ────────────────────────────────────────────────────────
section_header("Alert Settings")

with st.form("email_config_form"):

    # Master enable
    enabled = st.toggle(
        "Enable email alerts",
        value=cfg.get("enabled", False),
        help="Master switch. When off, no emails are sent regardless of other settings.",
    )

    st.markdown("<div style='height:4px'/>", unsafe_allow_html=True)

    # Recipient
    to_address = st.text_input(
        "Recipient email address",
        value=cfg.get("to_address", ""),
        placeholder="you@gmail.com",
        help=(
            "Where all alerts are sent. If in SES sandbox mode this address "
            "must also be verified in AWS SES."
        ),
    )

    st.markdown("---")
    section_header("Trade Activity Alerts", "Triggered immediately when a trade event occurs")

    ac1, ac2 = st.columns(2)
    with ac1:
        alert_trade_add = st.checkbox(
            "✅ Trade added",
            value=cfg.get("alert_trade_add", True),
            help="Email when a new trade or corporate action is recorded (Add Trade or Bulk Upload).",
        )
        alert_trade_edit = st.checkbox(
            "✏️ Trade edited",
            value=cfg.get("alert_trade_edit", True),
            help="Email when an existing trade record is modified.",
        )
    with ac2:
        alert_trade_del = st.checkbox(
            "🗑️ Trade deleted",
            value=cfg.get("alert_trade_del", True),
            help="Email when a trade record is deleted.",
        )
        alert_bulk = st.checkbox(
            "📤 Bulk upload complete",
            value=cfg.get("alert_bulk", True),
            help="Single summary email after a bulk CSV upload with row count and scrips affected.",
        )

    st.markdown("---")
    section_header("Weekly Portfolio Digest", "Automated XIRR summary email")

    alert_weekly = st.toggle(
        "Enable weekly digest",
        value=cfg.get("alert_weekly", True),
        help=(
            "Sends a full portfolio XIRR summary email once a week after the "
            "Lambda market-close run. Includes all scrip XIRRs, current values, "
            "and portfolio-level KPIs."
        ),
    )

    weekly_day = st.selectbox(
        "Digest day",
        options=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        index=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"].index(
            cfg.get("weekly_day", "Friday")
        ),
        disabled=not alert_weekly,
        help=(
            "The Lambda runs Mon–Fri at 15:35 IST. The digest fires ~10 min after "
            "the daily run on the chosen day. Friday is recommended — captures the "
            "full week's market close."
        ),
    )

    st.markdown("<div style='height:8px'/>", unsafe_allow_html=True)

    save_btn = st.form_submit_button(
        "💾 Save settings", type="primary", use_container_width=True
    )

if save_btn:
    errs = []
    if enabled and not to_address.strip():
        errs.append("Recipient email address is required when alerts are enabled.")
    if enabled and not configured:
        errs.append("SES sender not configured in secrets — alerts cannot be sent until that is fixed.")

    if errs:
        for e in errs:
            st.error(e)
    else:
        try:
            save_email_config({
                "enabled":          enabled,
                "to_address":       to_address.strip(),
                "alert_trade_add":  alert_trade_add,
                "alert_trade_edit": alert_trade_edit,
                "alert_trade_del":  alert_trade_del,
                "alert_bulk":       alert_bulk,
                "alert_weekly":     alert_weekly,
                "weekly_day":       weekly_day,
            })
            st.success("✅ Settings saved.")
        except Exception as e:
            st.error(f"Failed to save: {e}")

# ── Current config summary ────────────────────────────────────────────────────
st.markdown("---")
section_header("Current Configuration")

fresh = load_email_config()

status_colour = TEAL if fresh.get("enabled") else GREY
status_label  = "Enabled" if fresh.get("enabled") else "Disabled"

st.markdown(
    f'<div style="background:{CARD_BG};border:1px solid {BORDER};border-radius:10px;'
    f'padding:16px 20px;margin-bottom:16px">'
    f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">'
    f'<div style="width:10px;height:10px;border-radius:50%;background:{status_colour}"></div>'
    f'<div style="font-weight:700;color:{status_colour}">{status_label}</div>'
    f'</div>'
    f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.85rem">'
    f'<div style="color:{GREY}">Sender</div>'
    f'<div>{from_addr or "—"}</div>'
    f'<div style="color:{GREY}">Recipient</div>'
    f'<div>{fresh.get("to_address") or "—"}</div>'
    f'<div style="color:{GREY}">Weekly digest</div>'
    f'<div>{"✅ " + fresh.get("weekly_day","Friday") if fresh.get("alert_weekly") else "Off"}</div>'
    f'</div></div>',
    unsafe_allow_html=True,
)

# Alert type summary chips
alert_items = [
    ("alert_trade_add",  "Trade added"),
    ("alert_trade_edit", "Trade edited"),
    ("alert_trade_del",  "Trade deleted"),
    ("alert_bulk",       "Bulk upload"),
    ("alert_weekly",     "Weekly digest"),
]

chips_html = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px">'
for key, label in alert_items:
    on      = fresh.get(key, True)
    colour  = TEAL if on else "#E5E7EB"
    txtcol  = "#FFFFFF" if on else "#9CA3AF"
    icon    = "✓" if on else "✗"
    chips_html += (
        f'<span style="background:{colour};color:{txtcol};border-radius:20px;'
        f'padding:4px 12px;font-size:0.8rem;font-weight:600">'
        f'{icon} {label}</span>'
    )
chips_html += "</div>"
st.markdown(chips_html, unsafe_allow_html=True)

# ── Test email ────────────────────────────────────────────────────────────────
st.markdown("---")
section_header("Send Test Email", "Verify SES is working correctly")

st.markdown(
    f'<div style="color:{GREY};font-size:0.85rem;margin-bottom:12px">'
    "Sends a test alert to the configured recipient using the current SES credentials. "
    "The master switch does not need to be enabled for the test.</div>",
    unsafe_allow_html=True,
)

test_col, _ = st.columns([1, 2])
with test_col:
    if st.button("📧 Send test email", use_container_width=True):
        if not configured:
            st.error("SES sender not configured in secrets. Add `[email]` section first.")
        elif not fresh.get("to_address"):
            st.error("No recipient address. Save a recipient above first.")
        else:
            try:
                import boto3
                aws = st.secrets["aws"]
                ses = boto3.client(
                    "ses",
                    region_name=ses_region,
                    aws_access_key_id=str(aws["access_key_id"]),
                    aws_secret_access_key=str(aws["secret_access_key"]),
                )
                from datetime import datetime
                ts = datetime.now().strftime("%d %b %Y %I:%M %p")
                ses.send_email(
                    Source=from_addr,
                    Destination={"ToAddresses": [fresh["to_address"]]},
                    Message={
                        "Subject": {
                            "Data": "[XIRR Tracker] Test email ✅",
                            "Charset": "UTF-8",
                        },
                        "Body": {
                            "Html": {
                                "Charset": "UTF-8",
                                "Data": f"""
<!DOCTYPE html><html><body style="font-family:sans-serif;padding:24px;color:#111827">
<div style="max-width:480px;margin:0 auto;background:#F9FAFB;border-radius:12px;padding:28px">
  <div style="font-size:1.3rem;font-weight:700;color:#00A88A;margin-bottom:8px">
    📈 XIRR Tracker — Test Email
  </div>
  <p>This is a test email confirming that your SES configuration is working correctly.</p>
  <table style="width:100%;font-size:0.9rem;margin-top:16px">
    <tr><td style="color:#6B7280;padding:6px 0">Sent at</td>
        <td style="font-weight:600">{ts}</td></tr>
    <tr><td style="color:#6B7280;padding:6px 0">From</td>
        <td style="font-weight:600">{from_addr}</td></tr>
    <tr><td style="color:#6B7280;padding:6px 0">To</td>
        <td style="font-weight:600">{fresh["to_address"]}</td></tr>
    <tr><td style="color:#6B7280;padding:6px 0">SES Region</td>
        <td style="font-weight:600">{ses_region}</td></tr>
  </table>
  <p style="margin-top:20px;font-size:0.78rem;color:#9CA3AF">
    Portfolio XIRR Tracker · AWS SES
  </p>
</div>
</body></html>""",
                            }
                        },
                    },
                )
                st.success(f"✅ Test email sent to **{fresh['to_address']}**. Check your inbox.")
            except Exception as exc:
                err = str(exc)
                st.error(f"Failed to send test email: `{err}`")
                if "MessageRejected" in err or "not verified" in err.lower():
                    st.info(
                        "The sender or recipient address is not verified in SES. "
                        "If your account is in **sandbox mode**, both the sender and "
                        "recipient must be verified. Go to AWS Console → SES → "
                        "Verified identities and verify both addresses."
                    )
