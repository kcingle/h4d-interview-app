"""
pages/1_Interviews.py — Browse already-processed interviews: pick one
from the dropdown and see its analysis output, or delete it. Everything
to do with *processing* an interview (running the AI, confirming
interviewee metadata) lives entirely on Process Interview — this page is
a pure browse/view surface for interviews that already exist, kept
deliberately minimal so more browsing/filtering features can be layered
on later without fighting processing-flow state. Reruns against a
different hypothesis aren't supported here (or anywhere) anymore — start
a new interview on Process Interview instead.
"""

import streamlit as st

import auth
import storage
from render import build_export_header, render_analysis

st.set_page_config(page_title="H4D Interview App — Interviews", page_icon="🗂️")
auth.require_login()

st.title("Interviews")

interviews = storage.get_interviews()

if not interviews:
    st.write("No interviews saved yet. Process one on the **Process Interview** page first.")
    st.stop()


def _label(interview: dict) -> str:
    when = interview["created_at"][:19].replace("T", " ")
    return f"{interview['title']} — {when}"


selected_idx = st.selectbox(
    "Select an interview",
    options=range(len(interviews)),
    format_func=lambda i: _label(interviews[i]),
    key="interviews_selectbox",
)
selected = interviews[selected_idx]
interview_id = selected["id"]
interview_person = storage.get_person_for_interview(interview_id)

media_upload_errors = st.session_state.pop("media_upload_errors", None)
if media_upload_errors:
    for msg in media_upload_errors:
        st.warning(msg)

st.subheader(selected["title"])
st.caption(f"Saved {selected['created_at']}")

if not st.session_state.get(f"confirm_delete_interview_{interview_id}"):
    if st.button("🗑️ Delete this interview", key=f"delete_interview_btn_{interview_id}"):
        st.session_state[f"confirm_delete_interview_{interview_id}"] = True
        st.rerun()
else:
    st.warning(
        "This cannot be undone and deletes every run this interview has, "
        "and its interviewee metadata (unless that person is also linked "
        "to another interview, in which case the person is kept). Delete "
        "this interview permanently?"
    )
    dc1, dc2 = st.columns(2)
    with dc1:
        confirm_delete_interview = st.button(
            "Yes, permanently delete", key=f"confirm_delete_interview_btn_{interview_id}"
        )
    with dc2:
        cancel_delete_interview = st.button(
            "Cancel", key=f"cancel_delete_interview_btn_{interview_id}"
        )
    if confirm_delete_interview:
        # Only delete the linked person if they're not linked to any
        # OTHER interview too — a person can legitimately be interviewed
        # more than once, and deleting this interview shouldn't destroy
        # metadata still in use elsewhere.
        if interview_person:
            person_full = storage.get_person(interview_person["id"])
            if person_full and len(person_full["interviews"]) <= 1:
                storage.delete_person(interview_person["id"])
        storage.delete_interview(interview_id)
        st.session_state.pop(f"confirm_delete_interview_{interview_id}", None)
        # The previously-selected index may no longer be valid for the
        # now-shorter interview list — reset it rather than risk a
        # stale out-of-range selectbox value on rerun.
        st.session_state.pop("interviews_selectbox", None)
        st.success("Deleted.")
        st.rerun()
    if cancel_delete_interview:
        st.session_state.pop(f"confirm_delete_interview_{interview_id}", None)
        st.rerun()

st.divider()

runs = storage.get_runs_for_interview(interview_id)
if not runs:
    st.write("No output yet for this interview.")
else:
    for i, run in enumerate(runs, start=1):
        # Every interview processed going forward has exactly one run —
        # reruns are gone. Older interviews from before that change may
        # still have more than one; show each labeled by hypothesis/date
        # so none of that history is lost.
        if len(runs) > 1:
            when = run["created_at"][:19].replace("T", " ")
            st.subheader(f"Run {i} — hypothesis: {run['hypothesis_text']} — {when}")
        export_header = build_export_header(
            selected, interview_person, run, storage.get_document_titles(run["document_ids"])
        )
        render_analysis(
            run["output"],
            run["hypothesis_text"],
            key_prefix=f"run_{run['id']}_",
            export_header=export_header,
        )
        if len(runs) > 1 and i < len(runs):
            st.divider()
