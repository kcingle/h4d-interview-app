"""
auth.py — Simple single shared-password gate for the whole team (not
individual accounts). The password lives ONLY in Streamlit secrets
(TEAM_PASSWORD) — never in code, never committed.

Call require_login() as the very first Streamlit command on EVERY page,
right after st.set_page_config(...). This has to happen on every page
individually, not just the entry point: Streamlit's classic multipage
nav (the pages/ directory convention this app uses) executes a page's
entire script fresh whenever it's selected — via the sidebar, or by
navigating straight to that page's URL — so a gate placed only on
Process_Interview.py would do nothing to stop someone from opening
".../Interviews" directly. Putting the check at the top of every file
is what actually makes it unbypassable.
"""

import hmac

import streamlit as st


def require_login() -> None:
    """Block the rest of this page from running until the correct team
    password has been entered this session. Returns immediately (no-op)
    once st.session_state.authenticated is True — set only by a correct
    password, and only in memory for this one browser session, never
    persisted anywhere."""
    if st.session_state.get("authenticated"):
        return

    team_password = st.secrets.get("TEAM_PASSWORD")
    if not team_password:
        st.error(
            "This app's TEAM_PASSWORD secret isn't configured yet — it "
            "can't start until that's set (see Settings/secrets)."
        )
        st.stop()

    st.title("🔒 Team Access")
    st.caption("Enter the shared team password to continue.")
    with st.form("login_form"):
        entered = st.text_input("Team password", type="password")
        submitted = st.form_submit_button("Enter")

    if submitted:
        if hmac.compare_digest(entered, team_password):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    # Whether or not a (wrong) password was just submitted, nothing below
    # this point on the calling page should ever render pre-auth.
    st.stop()
