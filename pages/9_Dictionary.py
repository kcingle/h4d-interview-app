"""
pages/9_Dictionary.py — Terms saved from Chat's "Background &
Definitions" tab (see ai.define_terms). Nothing lands here
automatically — every entry was explicitly added via that tab's
"➕ Add to dictionary" button. This page is purely browsing/managing
what's already saved: search, mark important, and delete — no AI calls.
"""

import streamlit as st

import auth
import storage

st.set_page_config(page_title="H4D Interview App — Dictionary", page_icon="📖")
auth.require_login()

st.title("Dictionary")
st.caption(
    "Terms, acronyms, and concepts saved from Chat's Background & "
    "Definitions tab. Nothing is added here automatically."
)

entries = storage.get_dictionary_entries()

if not entries:
    st.write(
        "No terms saved yet. Go to **Chat → Background & Definitions**, "
        "ask what something means, and click \"Add to dictionary\"."
    )
    st.stop()

search_query = st.text_input(
    "🔍 Search", placeholder="Filter by term or definition text..."
)
q = search_query.strip().lower()
filtered_entries = [
    e for e in entries
    if not q
    or q in (e["term"] or "").lower()
    or q in (e["definition"] or "").lower()
    or q in (e["expansion"] or "").lower()
]

st.caption(f"{len(filtered_entries)} of {len(entries)} entries shown.")

if not filtered_entries:
    st.info("No entries match that search.")
    st.stop()

for entry in filtered_entries:
    entry_id = entry["id"]
    with st.container(border=True):
        title = f"⭐ **{entry['term']}**" if entry["is_important"] else f"**{entry['term']}**"
        if entry["is_acronym"] and entry["expansion"]:
            title += f" — {entry['expansion']}"
        st.markdown(title)
        st.write(entry["definition"])

        c1, c2 = st.columns(2)
        with c1:
            if entry["is_important"]:
                if st.button("☆ Unmark important", key=f"unmark_{entry_id}"):
                    storage.set_dictionary_importance(entry_id, False)
                    st.rerun()
            else:
                if st.button("⭐ Mark important", key=f"mark_{entry_id}"):
                    storage.set_dictionary_importance(entry_id, True)
                    st.rerun()
        with c2:
            if not st.session_state.get(f"confirm_delete_dict_{entry_id}"):
                if st.button("🗑️ Delete", key=f"delete_dict_btn_{entry_id}"):
                    st.session_state[f"confirm_delete_dict_{entry_id}"] = True
                    st.rerun()

        if st.session_state.get(f"confirm_delete_dict_{entry_id}"):
            st.warning("Delete this entry permanently?")
            dc1, dc2 = st.columns(2)
            with dc1:
                confirm_delete_dict = st.button(
                    "Yes, permanently delete", key=f"confirm_delete_dict_btn_{entry_id}"
                )
            with dc2:
                cancel_delete_dict = st.button("Cancel", key=f"cancel_delete_dict_btn_{entry_id}")
            if confirm_delete_dict:
                storage.delete_dictionary_entry(entry_id)
                st.session_state.pop(f"confirm_delete_dict_{entry_id}", None)
                st.success("Deleted.")
                st.rerun()
            if cancel_delete_dict:
                st.session_state.pop(f"confirm_delete_dict_{entry_id}", None)
                st.rerun()
