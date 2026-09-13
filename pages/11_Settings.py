"""
pages/11_Settings.py — App settings. Step 2 adds the API key field the
Process Interview page needs.

The key is saved locally to a .env file next to the app (via env_store —
gitignored, never committed) rather than kept only in st.session_state.
That's a deliberate fix, not just a nice-to-have: a value tied to a
widget's `key=` only lives in session_state while that specific widget is
being rendered, so it was disappearing the moment you navigated to any
other page (see env_store.py's docstring for the full explanation). Every
page that makes an API call now reads env_store.load_api_key() directly,
so they all see the same key, and it survives restarting the app too.
"""

import streamlit as st

import auth
import env_store
import storage

st.set_page_config(page_title="H4D Interview App — Settings", page_icon="⚙️")
auth.require_login()

st.title("Settings")

st.subheader("Anthropic API key")

# If this app is deployed with ANTHROPIC_API_KEY set server-side (Streamlit
# secrets), that's the ONE key the whole team uses — no editable box here
# at all: nothing to type, and nothing this page could usefully write to
# a deployed container's filesystem anyway. Only local dev, with no such
# secret configured, gets the editable "paste your own key" flow below.
try:
    key_is_server_managed = "ANTHROPIC_API_KEY" in st.secrets
except Exception:
    key_is_server_managed = False

if key_is_server_managed:
    st.success(
        "API key is configured server-side for the whole team (Streamlit "
        "secrets) — nothing to do here."
    )
else:
    saved_key = env_store.load_api_key()
    entered_key = st.text_input(
        "API key",
        type="password",
        value=saved_key,
        key="api_key_input",
        help="Used to call Claude from every page that processes an interview. "
        "Saved locally to a .env file next to the app (gitignored — never "
        "committed), so it's available on every page and survives restarting "
        "the app.",
    )
    if entered_key != saved_key:
        env_store.save_api_key(entered_key)
        saved_key = entered_key

    if saved_key:
        st.success("API key saved — available on every page, including after a restart.")
    else:
        st.caption("No API key saved yet. Paste one above to enable AI processing.")

st.divider()
st.subheader("Hypothesis label maintenance")
st.caption(
    "Deleting hypotheses leaves gaps — a new root hypothesis fills the "
    "lowest free number, but existing ones are never renumbered, so the "
    "tree can drift to start well above 1. This renumbers every root "
    "label back to a clean 1, 2, 3... sequence (in current order), "
    "shifting each descendant's label to match its parent while leaving "
    "its own letter suffix untouched (e.g. root \"6\" / child \"6a\" "
    "becomes root \"1\" / child \"1a\"). Hypothesis text, state, and tree "
    "structure are untouched — only the label text changes."
)
if st.button("🔧 Renumber hypothesis labels"):
    st.session_state["show_renumber_confirm"] = True

if st.session_state.get("show_renumber_confirm"):
    st.warning("This can't be undone by itself. Renumber every hypothesis label now?")
    rc1, rc2 = st.columns(2)
    with rc1:
        confirm_renumber = st.button("Yes, renumber", key="confirm_renumber_btn")
    with rc2:
        cancel_renumber = st.button("Cancel", key="cancel_renumber_btn")
    if confirm_renumber:
        storage.renumber_root_hypotheses()
        st.session_state.pop("show_renumber_confirm", None)
        st.success("Hypothesis labels renumbered — check the Hypotheses page.")
        st.rerun()
    if cancel_renumber:
        st.session_state.pop("show_renumber_confirm", None)
        st.rerun()

st.divider()
st.caption("More settings will land here in later steps.")
