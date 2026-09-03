"""
pages/5_Settings.py — App settings. Step 2 adds the API key field the
Process Interview page needs.

The key is kept only in st.session_state for this run of the app — it is
NOT written to disk. Persisting it locally (.env / secrets) is planned for
a later step.
"""

import streamlit as st

st.set_page_config(page_title="H4D Interview App — Settings", page_icon="⚙️")

st.title("Settings")

st.subheader("Anthropic API key")
st.text_input(
    "API key",
    type="password",
    key="api_key",
    help="Used to call Claude from the Process Interview page. "
    "Kept only in this browser session — not saved to disk yet.",
)
if st.session_state.get("api_key"):
    st.success("API key set for this session.")
else:
    st.caption("No API key set yet. Paste one above to enable AI processing.")

st.divider()
st.caption("More settings will land here in later steps.")
