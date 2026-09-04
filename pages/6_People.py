"""
pages/6_People.py — Browsable table of everyone interviewed. Selecting a
person shows their editable metadata plus their linked interview(s) and
each interview's runs (reusing the same table rendering as elsewhere).
Also offers a one-click Excel export of the (filtered) roster — see
people_export.build_people_excel.
"""

import streamlit as st

import people_export
import storage
from render import build_export_header, render_analysis

RELATIONSHIP_OPTIONS = ["", "beneficiary", "adjacent", "expert"]
INTERVIEW_STATUS_OPTIONS = list(storage.ALLOWED_INTERVIEW_STATUSES)
ALL_OPTION = "All"

st.set_page_config(page_title="H4D Interview App — People", page_icon="🧑‍🤝‍🧑")

st.title("People")
st.caption("Everyone interviewed, with metadata confirmed on the Process Interview page.")

people = storage.get_people()

if not people:
    st.write("No people yet.")
    st.stop()

st.subheader("All people")

# Filters. Relationship/status use their fixed option sets; branch/service
# is free text, so its filter options are built from whatever values
# actually exist among current people. Sorting itself is Streamlit's
# built-in click-a-column-header sort on st.dataframe below — no custom
# sort control needed on top of these filters.
f1, f2, f3 = st.columns(3)
with f1:
    relationship_filter = st.selectbox(
        "Filter by relationship", [ALL_OPTION] + [r for r in RELATIONSHIP_OPTIONS if r]
    )
with f2:
    branch_options = sorted({p["branch_service"] for p in people if p["branch_service"]})
    branch_filter = st.selectbox("Filter by branch / service", [ALL_OPTION] + branch_options)
with f3:
    status_filter = st.selectbox("Filter by interview status", [ALL_OPTION] + INTERVIEW_STATUS_OPTIONS)

filtered_people = [
    p for p in people
    if (relationship_filter == ALL_OPTION or p["relationship"] == relationship_filter)
    and (branch_filter == ALL_OPTION or p["branch_service"] == branch_filter)
    and (status_filter == ALL_OPTION or p["interview_status"] == status_filter)
]

st.dataframe(
    [
        {
            "Name": p["name"],
            "Role": p["role"],
            "Organization": p["organization"],
            "Rank": p["rank"],
            "Branch / service": p["branch_service"],
            "Seniority": p["seniority_level"],
            "Relationship": p["relationship"],
            "Interview status": p["interview_status"],
            "Interview date": p["interview_date"],
            "Descriptor": p["descriptor"],
        }
        for p in filtered_people
    ],
    use_container_width=True,
)
st.caption("Click a column header above to sort.")

if not filtered_people:
    st.info("No people match the current filters.")
    st.stop()

st.download_button(
    "📊 Export to Excel",
    data=people_export.build_people_excel(filtered_people),
    file_name="people.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="Downloads the table above (respecting the filters set here) as a .xlsx file.",
)

st.divider()
st.subheader("View / edit a person")

labels = [p["name"] or f"(unnamed, id {p['id']})" for p in filtered_people]
selected_idx = st.selectbox(
    "Select a person", options=range(len(filtered_people)), format_func=lambda i: labels[i]
)
selected = filtered_people[selected_idx]
person_id = selected["id"]

with st.form(f"edit_person_form_{person_id}"):
    e_name = st.text_input("Name (or a label, if anonymous)", value=selected["name"])
    e_role = st.text_input("Role / title", value=selected["role"] or "")
    e_org = st.text_input("Organization / unit", value=selected["organization"] or "")
    e_seniority = st.text_input("Seniority level", value=selected["seniority_level"] or "")
    e_rank = st.text_input("Rank", value=selected["rank"] or "")
    e_branch = st.text_input(
        "Branch / service", value=selected["branch_service"] or "",
        help="E.g. Army, Air Force, Navy, Marines, Space Force, civilian/other.",
    )
    current_relationship = selected["relationship"] or ""
    e_relationship = st.selectbox(
        "Relationship to the problem",
        RELATIONSHIP_OPTIONS,
        index=RELATIONSHIP_OPTIONS.index(current_relationship)
        if current_relationship in RELATIONSHIP_OPTIONS else 0,
    )
    e_date = st.text_input("Interview date", value=selected["interview_date"] or "")
    current_status = selected["interview_status"] or "completed"
    e_status = st.selectbox(
        "Interview status",
        INTERVIEW_STATUS_OPTIONS,
        index=INTERVIEW_STATUS_OPTIONS.index(current_status)
        if current_status in INTERVIEW_STATUS_OPTIONS else INTERVIEW_STATUS_OPTIONS.index("completed"),
    )
    e_descriptor = st.text_input("One-line descriptor", value=selected["descriptor"] or "")
    save_edit = st.form_submit_button("Save changes")

if save_edit:
    storage.update_person(
        person_id,
        name=e_name.strip(),
        role=e_role.strip(),
        organization=e_org.strip(),
        seniority_level=e_seniority.strip(),
        relationship=e_relationship,
        interview_date=e_date.strip(),
        descriptor=e_descriptor.strip(),
        rank=e_rank.strip(),
        branch_service=e_branch.strip(),
        interview_status=e_status,
    )
    st.success("Saved.")
    st.rerun()

st.divider()
st.subheader("Linked interview(s)")

if not selected["interviews"]:
    st.write("Not linked to any interview yet.")
else:
    for interview in selected["interviews"]:
        when = interview["created_at"][:19].replace("T", " ")
        # A bordered container, not st.expander, here — each run below
        # gets its own expander, and Streamlit doesn't allow nesting one
        # expander inside another (this combination has crashed the page
        # for any person with a linked run since Step 6; fixed now as
        # part of Step 7, whose export controls sit inside that same
        # per-run expander).
        with st.container(border=True):
            st.markdown(f"**{interview['title']}** — {when}")
            runs = storage.get_runs_for_interview(interview["id"])
            if not runs:
                st.write("No runs yet for this interview.")
            else:
                for i, run in enumerate(runs, start=1):
                    run_when = run["created_at"][:19].replace("T", " ")
                    with st.expander(f"Run {i} — hypothesis: {run['hypothesis_text']} — {run_when}"):
                        export_header = build_export_header(
                            interview, selected, run, storage.get_document_titles(run["document_ids"])
                        )
                        render_analysis(
                            run["output"],
                            run["hypothesis_text"],
                            key_prefix=f"person_run_{run['id']}_",
                            export_header=export_header,
                        )
