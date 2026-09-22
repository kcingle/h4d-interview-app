"""
pages/7_Metadata.py — Everyone interviewed, as one editable spreadsheet:
click a cell to edit it in place, then Save changes. Interviewee metadata
is suggested and confirmed on Process Interview; this page is purely for
correcting it afterward — no filters, no separate edit form, no delete,
no linked-interview browsing. Rows are matched back to people by
position (the editor is fixed-size — no adding/removing/reordering rows
here), so a save always lands on the right person.
"""

import streamlit as st

import auth
import storage

RELATIONSHIP_OPTIONS = ["", "beneficiary", "adjacent", "expert"]
INTERVIEW_STATUS_OPTIONS = list(storage.ALLOWED_INTERVIEW_STATUSES)

st.set_page_config(page_title="H4D Interview App — Metadata", page_icon="🧑‍🤝‍🧑")
auth.require_login()

st.title("Metadata")
st.caption("Everyone interviewed. Click any cell to edit it, then Save changes.")

people = storage.get_people()

if not people:
    st.write("No people yet.")
    st.stop()

rows = [
    {
        "Name": p["name"] or "",
        "Role": p["role"] or "",
        "Organization": p["organization"] or "",
        "Rank": p["rank"] or "",
        "Branch / service": p["branch_service"] or "",
        "Seniority": p["seniority_level"] or "",
        "Relationship": p["relationship"] or "",
        "Interview status": p["interview_status"] or "completed",
        "Interview date": p["interview_date"] or "",
        "Descriptor": p["descriptor"] or "",
        "Interviewer(s)": ", ".join(p["interviewers"]),
    }
    for p in people
]

edited_rows = st.data_editor(
    rows,
    use_container_width=True,
    num_rows="fixed",
    hide_index=True,
    column_config={
        "Relationship": st.column_config.SelectboxColumn(options=RELATIONSHIP_OPTIONS),
        "Interview status": st.column_config.SelectboxColumn(options=INTERVIEW_STATUS_OPTIONS),
        "Interviewer(s)": st.column_config.TextColumn(help="Comma-separated, up to 5 names"),
    },
    key="metadata_editor",
)

if st.button("Save changes", type="primary"):
    changed = 0
    for person, before, after in zip(people, rows, edited_rows):
        if before == after:
            continue
        changed += 1
        interviewers = [
            n.strip() for n in (after["Interviewer(s)"] or "").split(",") if n.strip()
        ]
        storage.update_person(
            person["id"],
            name=(after["Name"] or "").strip(),
            role=(after["Role"] or "").strip(),
            organization=(after["Organization"] or "").strip(),
            seniority_level=(after["Seniority"] or "").strip(),
            relationship=after["Relationship"] or "",
            interview_date=(after["Interview date"] or "").strip(),
            descriptor=(after["Descriptor"] or "").strip(),
            rank=(after["Rank"] or "").strip(),
            branch_service=(after["Branch / service"] or "").strip(),
            interview_status=after["Interview status"] or "completed",
            interviewers=interviewers,
        )
        # Keep every linked interview's title in sync with the standard
        # "(rank name, date)" format — a correction here shouldn't leave
        # a stale title behind on its interview(s).
        for linked_interview in person["interviews"]:
            storage.sync_interview_title(linked_interview["id"])

    if changed:
        st.success(f"Saved {changed} change{'s' if changed != 1 else ''}.")
        st.rerun()
    else:
        st.info("No changes to save.")
