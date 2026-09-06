"""
pages/5_Settings.py — App settings. Step 2 adds the API key field the
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

import env_store

st.set_page_config(page_title="H4D Interview App — Settings", page_icon="⚙️")

st.title("Settings")

st.subheader("Anthropic API key")

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
st.caption("More settings will land here in later steps.")
