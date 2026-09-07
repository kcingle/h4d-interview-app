"""
pages/6_Documents.py — Reference documents the analysis engine can use as
context, including the permanent, protected Mom Test PDF slot (pinned,
always included on every analysis — never a toggle — viewable and
replaceable via upload, but never deletable).
"""

import streamlit as st

import auth
import storage

st.set_page_config(page_title="H4D Interview App — Documents", page_icon="📄")
auth.require_login()

st.title("Documents")
st.caption(
    "Pinned documents (like the Mom Test) are always included on every "
    "analysis — not a toggle — are protected from deletion, and are shown "
    "first below. Everything else can be turned on or off per-interview on "
    "the Process Interview page."
)

documents = storage.get_documents()


def _format_badge(doc: dict) -> str:
    pinned = "📌 Pinned" if doc["is_pinned"] else ""
    fmt = "PDF" if doc["content_format"] == "pdf" else ""
    return "  ".join(b for b in (pinned, fmt) if b)


st.subheader("All documents")
if not documents:
    st.write("No documents yet — add one below.")
else:
    for doc in documents:
        badge = _format_badge(doc)
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
    is_pdf = selected["content_format"] == "pdf"

    if is_pdf:
        if selected["content"]:
            size_kb = len(selected["content"]) / 1024
            st.write(f"📄 PDF document — {size_kb:.1f} KB")
            st.download_button(
                "Download PDF",
                data=selected["content"],
                file_name=f"{selected['title']}.pdf",
                mime="application/pdf",
                key=f"download_pdf_{doc_id}",
            )
        else:
            st.info("No PDF uploaded yet.")
    else:
        st.text_area(
            "Content", value=selected["content"], height=200, disabled=True, key=f"view_{doc_id}"
        )

    if selected["is_pinned"]:
        st.caption(
            "🔒 Pinned — protected from deletion. Its title can't change, but "
            "the PDF below can be uploaded or replaced any time."
        )
        if is_pdf:
            with st.form(f"replace_pdf_form_{doc_id}"):
                new_pdf = st.file_uploader("Upload / replace PDF", type=["pdf"], key=f"pdf_up_{doc_id}")
                replace_submitted = st.form_submit_button("Save PDF")
            if replace_submitted:
                if new_pdf is not None:
                    storage.replace_document_pdf(doc_id, new_pdf.read())
                    st.success("PDF saved.")
                    st.rerun()
                else:
                    st.warning("Choose a PDF file first.")
    elif is_pdf:
        # Non-pinned PDF: no in-place "edit" affordance (there's no text
        # to type into a box) — download to check it, or delete and
        # re-add if it's wrong.
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
    uploaded_file = st.file_uploader("Upload a .txt, .md, or .pdf file", type=["txt", "md", "pdf"])
    pasted_text = st.text_area("...or paste text here (not used for a PDF upload)", height=150)
    add_submitted = st.form_submit_button("Save document")

if add_submitted:
    content = None
    content_format = "text"
    decode_failed = False

    if uploaded_file is not None:
        if uploaded_file.name.lower().endswith(".pdf") or uploaded_file.type == "application/pdf":
            content = uploaded_file.read()
            content_format = "pdf"
        else:
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
        storage.add_document(new_doc_title.strip(), content, is_pinned=False, content_format=content_format)
        st.success("Document saved.")
        st.rerun()
