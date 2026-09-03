"""
pages/3_Documents.py — Reference documents the analysis engine can use as
context, including the permanent, protected Mom Test doc (pinned, seeded
automatically, viewable but never editable or deletable).
"""

import streamlit as st

import storage

st.set_page_config(page_title="H4D Interview App — Documents", page_icon="📄")

st.title("Documents")
st.caption(
    "Pinned documents (like the Mom Test) are always included by default when "
    "processing an interview, are protected from editing/deletion, and are "
    "shown first below."
)

documents = storage.get_documents()

st.subheader("All documents")
if not documents:
    st.write("No documents yet — add one below.")
else:
    for doc in documents:
        badge = "📌 Pinned" if doc["is_pinned"] else ""
        when = doc["created_at"][:19].replace("T", " ")
        st.write(f"**{doc['title']}** {badge}  \n_{when}_")

st.divider()
st.subheader("View / edit a document")

if documents:
    labels = [f"{'📌 ' if d['is_pinned'] else ''}{d['title']}" for d in documents]
    selected_idx = st.selectbox(
        "Select a document", options=range(len(documents)), format_func=lambda i: labels[i]
    )
    selected = documents[selected_idx]
    doc_id = selected["id"]

    st.text_area("Content", value=selected["content"], height=200, disabled=True, key=f"view_{doc_id}")

    if selected["is_pinned"]:
        st.caption("🔒 Pinned — protected. This document cannot be edited or deleted.")
    else:
        with st.expander("✏️ Edit this document"):
            with st.form(f"edit_doc_form_{doc_id}"):
                new_title = st.text_input("Title", value=selected["title"], key=f"edit_title_{doc_id}")
                new_content = st.text_area(
                    "Content", value=selected["content"], height=200, key=f"edit_content_{doc_id}"
                )
                save_edit = st.form_submit_button("Save changes")
            if save_edit:
                if new_title.strip() and new_content.strip():
                    try:
                        storage.update_document(doc_id, new_title.strip(), new_content.strip())
                        st.success("Saved.")
                        st.rerun()
                    except storage.DocumentError as e:
                        st.error(str(e))
                else:
                    st.warning("Title and content are both required.")

        st.divider()
        if not st.session_state.get(f"confirm_delete_{doc_id}"):
            if st.button("🗑️ Delete this document", key=f"delete_btn_{doc_id}"):
                st.session_state[f"confirm_delete_{doc_id}"] = True
                st.rerun()
        else:
            st.warning("This cannot be undone. Delete this document permanently?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Yes, permanently delete", key=f"confirm_delete_btn_{doc_id}"):
                    try:
                        storage.delete_document(doc_id)
                        st.session_state.pop(f"confirm_delete_{doc_id}", None)
                        st.success("Deleted.")
                        st.rerun()
                    except storage.DocumentError as e:
                        st.error(str(e))
            with c2:
                if st.button("Cancel", key=f"cancel_delete_btn_{doc_id}"):
                    st.session_state.pop(f"confirm_delete_{doc_id}", None)
                    st.rerun()

st.divider()
st.subheader("Add a document")

with st.form("add_document_form", clear_on_submit=True):
    new_doc_title = st.text_input("Title")
    uploaded_file = st.file_uploader("Upload a .txt or .md file", type=["txt", "md"])
    pasted_text = st.text_area("...or paste text here", height=150)
    add_submitted = st.form_submit_button("Save document")

if add_submitted:
    content = None
    decode_failed = False
    if uploaded_file is not None:
        try:
            content = uploaded_file.read().decode("utf-8")
        except UnicodeDecodeError:
            decode_failed = True
    elif pasted_text.strip():
        content = pasted_text.strip()

    if decode_failed:
        st.error("Couldn't read that file as text (UTF-8). Try a plain .txt or .md file.")
    elif content is None:
        st.warning("Upload a file or paste some text.")
    elif not new_doc_title.strip():
        st.warning("Enter a title.")
    else:
        storage.add_document(new_doc_title.strip(), content, is_pinned=False)
        st.success("Document saved.")
        st.rerun()
