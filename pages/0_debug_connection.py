"""
pages/0_debug_connection.py
Connection diagnostics page — use this to verify your secrets are correctly
configured before the main dashboard loads.

Visit /debug_connection on your deployed app.
"""
import streamlit as st

with st.sidebar:
    st.markdown('<div style="font-size:1.3rem;font-weight:800;color:#00A88A;padding:16px 0 24px">📈 XIRR Tracker</div>', unsafe_allow_html=True)

st.title("🔧 Connection Diagnostics")
st.markdown("Use this page to verify your AWS credentials and DynamoDB tables are reachable.")
st.markdown("---")

# ── Step 1: Check secrets are present ────────────────────────────────────────
st.subheader("Step 1 — Secrets check")

REQUIRED = {
    "aws":      ["access_key_id", "secret_access_key", "region"],
    "dynamodb": ["trades_table", "xirr_table"],
}

all_present = True
for section, keys in REQUIRED.items():
    for key in keys:
        full = f"[{section}] → {key}"
        try:
            val = st.secrets[section][key]
            if not val:
                st.warning(f"  {full} is present but **empty**")
                all_present = False
            else:
                # Mask sensitive values
                if "key" in key.lower():
                    display = "*" * (len(str(val)) - 4) + str(val)[-4:]
                else:
                    display = str(val)
                st.success(f"  {full} = `{display}`")
        except (KeyError, TypeError):
            st.error(f"  {full} is **MISSING**")
            all_present = False

if not all_present:
    st.error(
        "One or more secrets are missing. "
        "Go to **App Settings → Secrets** in Streamlit Community Cloud and paste:"
    )
    st.code(
        "[aws]\n"
        "access_key_id     = \"AKIA...\"\n"
        "secret_access_key = \"...\"\n"
        "region            = \"ap-south-1\"\n"
        "\n"
        "[dynamodb]\n"
        "trades_table = \"portfolio_trades_prod\"\n"
        "xirr_table   = \"portfolio_xirr_prod\"",
        language="toml",
    )
    st.stop()

st.success("All required secrets are present.")
st.markdown("---")


# ── Step 2: boto3 import check ────────────────────────────────────────────────
st.subheader("Step 2 — boto3 import")
try:
    import boto3
    st.success(f"boto3 imported successfully (version {boto3.__version__})")
except ImportError as e:
    st.error(f"boto3 not installed: {e}")
    st.info("Make sure `boto3>=1.34.0` is in your `requirements.txt`")
    st.stop()

st.markdown("---")


# ── Step 3: AWS credential validation ─────────────────────────────────────────
st.subheader("Step 3 — AWS credentials")
from utils.data import test_connection, get_aws_config

try:
    cfg = get_aws_config()
    st.info(f"Attempting connection to region `{cfg['region']}`...")
except KeyError as e:
    st.error(f"Secret key error: {e}")
    st.stop()

ok, msg = test_connection()
if ok:
    st.success(f"Connected: {msg}")
else:
    st.error(f"Connection failed: {msg}")
    st.markdown("---")
    st.markdown("### Possible fixes")

    if "ResourceNotFoundException" in msg or "not found" in msg.lower():
        st.markdown(
            f"- The table `{cfg.get('trades_table')}` does not exist in region `{cfg.get('region')}`\n"
            "- Open the AWS DynamoDB console and verify the exact table name and region\n"
            "- Table names are case-sensitive"
        )
    elif "InvalidSignature" in msg or "Invalid credentials" in msg or "Unrecognized" in msg:
        st.markdown(
            "- The `access_key_id` or `secret_access_key` is incorrect\n"
            "- Go to AWS IAM → Users → Security credentials → Create new access key\n"
            "- Make sure you copied the full key without truncation"
        )
    elif "AccessDenied" in msg:
        st.markdown(
            "- The IAM user exists but lacks DynamoDB permissions\n"
            "- Attach this inline policy to the IAM user:\n"
        )
        st.code("""{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:DescribeTable",
        "dynamodb:Query",
        "dynamodb:Scan",
        "dynamodb:GetItem",
        "dynamodb:PutItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/portfolio_trades_prod",
        "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/portfolio_trades_prod/index/*",
        "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/portfolio_xirr_prod",
        "arn:aws:dynamodb:REGION:ACCOUNT_ID:table/portfolio_xirr_prod/index/*"
      ]
    }
  ]
}""", language="json")
    elif "region" in msg.lower() or "endpoint" in msg.lower():
        st.markdown(
            "- Region value is invalid. Use the exact AWS region code e.g. `ap-south-1`\n"
            "- Common Indian region: `ap-south-1` (Mumbai)\n"
            "- Do not include `https://` or any URL"
        )
    st.stop()

st.markdown("---")


# ── Step 4: Table read test ────────────────────────────────────────────────────
st.subheader("Step 4 — Table read test")

try:
    from utils.data import load_all_latest_xirr, load_all_trades
    with st.spinner("Reading XIRR table..."):
        snapshots = load_all_latest_xirr()
    st.success(f"XIRR table: {len(snapshots)} snapshot(s) found")

    if len(snapshots) == 0:
        st.warning(
            "The XIRR table is empty. This is expected if you haven't run the Lambda yet. "
            "The main dashboard will show a warning but won't crash."
        )
    else:
        portfolio = next((s for s in snapshots if s.get("pk") == "PORTFOLIO"), None)
        scrips    = [s for s in snapshots if s.get("type") == "SCRIP"]
        st.info(f"Portfolio snapshot: {'found' if portfolio else 'not found (run Lambda first)'}")
        st.info(f"Scrip snapshots: {len(scrips)}")

except Exception as e:
    st.error(f"XIRR table read failed: `{type(e).__name__}: {e}`")
    st.stop()

try:
    with st.spinner("Reading trades table..."):
        all_trades = load_all_trades()
    total_records = sum(len(v) for v in all_trades.values())
    st.success(f"Trades table: {total_records} record(s) across {len(all_trades)} scrip(s)")

    if total_records == 0:
        st.warning(
            "The trades table is empty. Load trades using `scripts/load_trades.py` "
            "or the Add Trade page."
        )
except Exception as e:
    st.error(f"Trades table read failed: `{type(e).__name__}: {e}`")
    st.stop()

st.markdown("---")
st.success("All checks passed. Your app should load correctly.")
st.markdown("Go to **[Portfolio Overview](/)** to view your dashboard.")
