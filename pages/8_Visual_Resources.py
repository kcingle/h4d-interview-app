"""
pages/8_Visual_Resources.py — Every photo, video, and other file uploaded
alongside an interview on Process Interview, browsable and searchable in
one place. Nothing lands here except what was explicitly uploaded there —
same "nothing automatic" spirit as Documents and Dictionary. Filtering by
search text happens page-side (same convention as Metadata/Dictionary),
not a database query.
"""

import streamlit as st

import auth
import storage

st.set_page_config(page_title="H4D Interview App — Visual Resources", page_icon="🖼️")
auth.require_login()

st.title("Visual Resources")
st.caption(
    "Photos, videos, and other files uploaded alongside interviews on "
    "Process Interview. Search by interview, caption, or filename below, "
    "or just scroll through everything."
)

try:
    resources = storage.get_visual_resources()
except Exception:
    st.error(
        "Couldn't load Visual Resources right now — this is usually a "
        "momentary database hiccup (the database can take a few seconds "
        "to wake up after sitting idle), not lost data."
    )
    if st.button("Try again"):
        st.rerun()
    st.stop()

if not resources:
    st.write(
        "Nothing uploaded yet — add photos or videos on the **Process "
        "Interview** page the next time you log one."
    )
    st.stop()

search_query = st.text_input(
    "🔍 Search", placeholder="Filter by interview, caption, or filename..."
)
q = search_query.strip().lower()
filtered = [
    r for r in resources
    if not q
    or q in (r["interview_title"] or "").lower()
    or q in (r["caption"] or "").lower()
    or q in (r["filename"] or "").lower()
]

st.caption(f"{len(filtered)} of {len(resources)} file(s) shown.")

if not filtered:
    st.info("No files match that search.")
    st.stop()

for r in filtered:
    resource_id = r["id"]
    with st.container(border=True):
        when = r["created_at"][:10]
        st.markdown(f"**{r['filename']}**")
        st.caption(f"{r['interview_title']} — {when}")
        if r["caption"]:
            st.write(r["caption"])

        # A broken/corrupt file must never take the whole page down with it —
        # one bad upload would otherwise block browsing every other one too.
        if r["media_kind"] == "image":
            try:
                st.image(r["content"])
            except Exception:
                st.warning("Couldn't preview this image — the file may be corrupted. Try downloading it below.")
        elif r["media_kind"] == "video":
            try:
                st.video(r["content"])
            except Exception:
                st.warning("Couldn't preview this video — the file may be corrupted. Try downloading it below.")
        else:
            size_kb = r["file_size_bytes"] / 1024
            st.write(f"📎 {r['mime_type']} — {size_kb:.0f} KB — no preview for this file type")

        st.download_button(
            "Download",
            data=r["content"],
            file_name=r["filename"],
            mime=r["mime_type"],
            key=f"download_media_{resource_id}",
        )

        with st.expander("Edit caption / delete"):
            new_caption = st.text_input(
                "Caption", value=r["caption"], key=f"caption_input_{resource_id}"
            )
            ec1, ec2 = st.columns(2)
            with ec1:
                if st.button("Save caption", key=f"save_caption_{resource_id}"):
                    storage.update_visual_resource_caption(resource_id, new_caption)
                    st.success("Caption updated.")
                    st.rerun()
            with ec2:
                if not st.session_state.get(f"confirm_delete_media_{resource_id}"):
                    if st.button("🗑️ Delete this file", key=f"delete_media_btn_{resource_id}"):
                        st.session_state[f"confirm_delete_media_{resource_id}"] = True
                        st.rerun()

            if st.session_state.get(f"confirm_delete_media_{resource_id}"):
                st.warning("Delete this file permanently?")
                dc1, dc2 = st.columns(2)
                with dc1:
                    if st.button(
                        "Yes, permanently delete", key=f"confirm_delete_media_btn_{resource_id}"
                    ):
                        storage.delete_visual_resource(resource_id)
                        st.session_state.pop(f"confirm_delete_media_{resource_id}", None)
                        st.success("Deleted.")
                        st.rerun()
                with dc2:
                    if st.button("Cancel", key=f"cancel_delete_media_btn_{resource_id}"):
                        st.session_state.pop(f"confirm_delete_media_{resource_id}", None)
                        st.rerun()
