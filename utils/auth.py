"""
utils/auth.py
Session-based login gate for the XIRR Tracker dashboard.

Every page calls `require_login()` as its very first statement after
st.set_page_config(). If the user is not authenticated they see the
login form and the rest of the page is blocked.

Credentials are stored in st.secrets:
    [auth]
    username      = "nachi"
    password_hash = "<PBKDF2 hash — generate with utils/auth.py hash_password()>"

To reset the password:
    1. Run:  python -c "from utils.auth import hash_password; print(hash_password('newpassword'))"
    2. Paste the output as the new password_hash in Streamlit Cloud Secrets → [auth]
    3. Redeploy (or just update secrets — Streamlit picks them up within ~60 s)
"""
from __future__ import annotations

import hashlib
import base64
import streamlit as st


# ── Hashing ───────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    Hash a plaintext password with PBKDF2-HMAC-SHA256.
    Run this locally to generate a hash to store in secrets:

        python -c "from utils.auth import hash_password; print(hash_password('mypassword'))"
    """
    import os
    salt = os.urandom(32)
    dk   = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def _verify(password: str, stored_hash: str) -> bool:
    """Return True if password matches the stored PBKDF2 hash."""
    try:
        salt_b64, hash_b64 = stored_hash.strip().split("$")
        salt = base64.b64decode(salt_b64)
        dk   = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
        return base64.b64encode(dk).decode() == hash_b64
    except Exception:
        return False


# ── Secrets reading ───────────────────────────────────────────────────────────

def _get_credentials() -> tuple[str, str]:
    """
    Return (username, password_hash) from st.secrets.
    Raises a clear error if the [auth] section is missing.
    """
    try:
        username      = str(st.secrets["auth"]["username"]).strip()
        password_hash = str(st.secrets["auth"]["password_hash"]).strip()
        return username, password_hash
    except (KeyError, TypeError):
        st.error(
            "**Auth secrets missing.** Add the following to your Streamlit secrets:\n\n"
            "```toml\n"
            "[auth]\n"
            "username      = \"your_username\"\n"
            "password_hash = \"<hash from hash_password()>\"\n"
            "```\n\n"
            "Run `python -c \"from utils.auth import hash_password; "
            "print(hash_password('yourpassword'))\"` to generate the hash."
        )
        st.stop()


# ── Login UI ──────────────────────────────────────────────────────────────────

def _show_login_form() -> None:
    """Render the centred login form. Sets st.session_state.authenticated on success."""
    # Hide sidebar and nav while logged out
    st.markdown("""
    <style>
        [data-testid="stSidebar"]        { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
        section[data-testid="stSidebarNav"] { display: none !important; }
        .block-container { max-width: 420px !important; padding-top: 8vh !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center;margin-bottom:32px">
        <div style="font-size:2.4rem">📈</div>
        <div style="font-size:1.5rem;font-weight:800;margin-top:8px">XIRR Tracker</div>
        <div style="color:#6B7280;font-size:0.9rem;margin-top:4px">Sign in to continue</div>
    </div>
    """, unsafe_allow_html=True)

    expected_user, expected_hash = _get_credentials()

    with st.form("login_form", clear_on_submit=True):
        username = st.text_input("Username", placeholder="Enter username")
        password = st.text_input("Password", type="password", placeholder="Enter password")
        submitted = st.form_submit_button("Sign in", width='stretch', type="primary")

    if submitted:
        if username.strip() == expected_user and _verify(password, expected_hash):
            st.session_state["authenticated"] = True
            st.session_state["auth_user"]     = username.strip()
            st.rerun()
        else:
            st.error("Incorrect username or password.")

    # Show reset hint only in non-production (local) runs
    import os
    if os.environ.get("STREAMLIT_ENV") == "local":
        st.caption("Hint: default password is `changeme`")


# ── Public API ────────────────────────────────────────────────────────────────

def require_login() -> None:
    """
    Call this at the top of every page (after st.set_page_config).
    Blocks the rest of the page until the user is authenticated.
    """
    if not st.session_state.get("authenticated", False):
        _show_login_form()
        st.stop()


def logout() -> None:
    """Clear authentication state and rerun."""
    st.session_state.pop("authenticated", None)
    st.session_state.pop("auth_user",     None)
    st.rerun()


def current_user() -> str:
    """Return the logged-in username, or empty string if not authenticated."""
    return st.session_state.get("auth_user", "")
