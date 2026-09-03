"""
pages/6_People.py — Browsable table of everyone interviewed. Selecting a
person shows their editable metadata plus their linked interview(s) and
each interview's runs (reusing the same table rendering as elsewhere).
"""

import streamlit as st

import storage
from render import build_export_header, render_analysis

RELATIONSHIP_OPTIONS = ["", "beneficiary", "adjacent", "expert"]

st.set_page_config(page_title="H4D Interview App — People", page_icon="🧑‍🤝‍🧑")

st.title("People")
st.caption("Everyone interviewed, with metadata confirmed on the Process Interview page.")

people = storage.get_people()

if not people:
    st.write("No people yet.")
    st.stop()

st.subheader("All people")
st.dataframe(
    [
        {
            "Name": p["name"],
            "Role": p["role"],
            "Organization": p["organization"],
            "Seniority": p["seniority_level"],
            "Relationship": p["relationship"],
            "Interview date": p["interview_date"],
            "Descriptor": p["descriptor"],
        }
        for p in people
    ],
    use_container_width=True,
)

st.divider()
st.subheader("View / edit a person")

labels = [p["name"] or f"(unnamed, id {p['id']})" for p in people]
selected_idx = st.selectbox("Select a person", options=range(len(people)), format_func=lambda i: labels[i])
selected = people[selected_idx]
person_id = selected["id"]

with st.form(f"edit_person_form_{person_id}"):
    e_name = st.text_input("Name (or a label, if anonymous)", value=selected["name"])
    e_role = st.text_input("Role / title", value=selected["role"] or "")
    e_org = st.text_input("Organization / unit", value=selected["organization"] or "")
    e_seniority = st.text_input("Seniority level", value=selected["seniority_level"] or "")
    current_relationship = selected["relationship"] or ""
    e_relationship = st.selectbox(
        "Relationship to the problem",
        RELATIONSHIP_OPTIONS,
        index=RELATIONSHIP_OPTIONS.index(current_relationship)
        if current_relationship in RELATIONSHIP_OPTIONS else 0,
    )
    e_date = st.text_input("Interview date", value=selected["interview_date"] or "")
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
