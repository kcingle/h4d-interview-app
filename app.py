"""
app.py — Entry point for the Streamlit app. This is the "Process Interview"
home page: pick which reference documents to include, paste raw interview
notes, run the two-step AI analysis, and review the results as real
tables. On completion the interview and this first run are saved
automatically (Step 3), followed by a suggest-and-confirm interviewee
metadata form (Step 6) — nothing is saved there until you confirm.
Confirming metadata hands off straight to the Interviews page for this
one interview (pre-selected, its one run auto-expanded) instead of
showing the results a second time inline here. Reruns against a
different hypothesis happen from the Interviews page instead. Run with:

    streamlit run app.py

Other pages live in pages/ and are picked up automatically by Streamlit's
built-in multipage navigation (shown in the sidebar).
"""

import datetime

import streamlit as st

import ai
import env_store
import storage  # noqa: F401  (importing this ensures the SQLite DB/tables exist)
from render import build_export_header, render_analysis, render_hypothesis_picker

RELATIONSHIP_OPTIONS = ["", "beneficiary", "adjacent", "expert"]
INTERVIEW_STATUS_OPTIONS = list(storage.ALLOWED_INTERVIEW_STATUSES)

st.set_page_config(page_title="H4D Interview App — Process Interview", page_icon="🎙️")

st.title("Process Interview")
st.caption("Paste raw interview notes, then run the two-step AI analysis below.")

api_key = env_store.load_api_key()
if not api_key:
    st.warning(
        "No Anthropic API key set yet. Enter one on the **Settings** page, then come back here."
    )

st.subheader("Hypotheses being tested")
st.caption(
    "Active hypotheses are pre-checked. Check or uncheck any to test one "
    "or more of them this run."
)
hypothesis_tree = storage.get_hypothesis_tree()
selected_hypotheses = render_hypothesis_picker(hypothesis_tree, key_prefix="process_hyp")
if not selected_hypotheses:
    st.warning("Select at least one hypothesis to test.")

st.subheader("Reference documents to include")
available_documents = storage.get_documents()
selected_documents = []

if not available_documents:
    st.caption("No reference documents yet — add some on the Documents page.")

# Pinned documents (the Mom Test) are a separate, mandatory category —
# always included, first and highest, never a toggle. Everything else
# stays an opt-in checkbox, unchecked by default.
pinned_documents = [d for d in available_documents if d["is_pinned"]]
toggleable_documents = [d for d in available_documents if not d["is_pinned"]]

for doc in pinned_documents:
    if doc["content"]:
        st.success(f"📌 {doc['title']} — always included")
        selected_documents.append(doc)
    else:
        st.caption(
            f"📌 {doc['title']} — not yet uploaded. "
            "Add it on the Documents page to include it."
        )

for doc in toggleable_documents:
    include = st.checkbox(doc["title"], value=False, key=f"include_doc_{doc['id']}")
    if include:
        selected_documents.append(doc)

default_title = f"Interview — {datetime.date.today().isoformat()}"
interview_title = st.text_input("Interview title", value=default_title, key="interview_title")

raw_notes = st.text_area(
    "Raw interview notes",
    height=300,
    key="raw_notes",
    placeholder="Paste the interview transcript or notes here...",
)

additional_notes = st.text_area(
    "Additional Notes (optional)",
    height=120,
    key="additional_notes",
    placeholder=(
        "Anything not captured in the transcript above — nonverbal "
        "communication, tone, body language, the room/setting, or "
        "anything else you noticed but didn't write down as dialogue."
    ),
)

if "flow_stage" not in st.session_state:
    st.session_state.flow_stage = "idle"

start_clicked = st.button(
    "Start", type="primary", disabled=not raw_notes.strip() or not selected_hypotheses
)

if start_clicked:
    st.session_state.pop("step2_result", None)
    st.session_state.pop("saved_message", None)
    # New interview being started — clear any metadata state left over
    # from a previous one so its suggestion/confirmation doesn't bleed in.
    st.session_state.pop("last_saved_interview_id", None)
    st.session_state.pop("metadata_suggestion", None)
    st.session_state.pop("metadata_saved", None)
    # Capture the checked document set and hypothesis list once, here, and
    # reuse them for the Step 2 / digest calls below — so the whole
    # conversation, and the later metadata-confirm digest refresh, all see
    # the same reference material and the same hypotheses.
    st.session_state.selected_documents = selected_documents
    st.session_state.selected_hypotheses = selected_hypotheses
    try:
        with st.spinner("Asking clarifying questions..."):
            step1 = ai.run_step1(
                selected_hypotheses,
                raw_notes,
                api_key,
                documents=selected_documents,
                additional_notes=additional_notes,
            )
        st.session_state.step1_questions = step1["questions"]
        st.session_state.step1_history = step1["history"]
        st.session_state.flow_stage = "awaiting_answers"
    except ai.AIError as e:
        st.error(str(e))

if st.session_state.flow_stage in ("awaiting_answers", "done"):
    st.divider()
    st.subheader("Clarifying questions")
    questions = st.session_state.get("step1_questions", [])

    if not questions:
        st.write("The AI had no clarifying questions for this interview.")

    with st.form("answers_form"):
        answers = [
            st.text_area(f"Q{i + 1}. {q}", key=f"answer_{i}")
            for i, q in enumerate(questions)
        ]
        submitted = st.form_submit_button("Continue → Run full analysis")

    if submitted:
        try:
            docs_for_step2 = st.session_state.get("selected_documents", [])
            with st.spinner("Running the full analysis..."):
                analysis = ai.run_step2(
                    st.session_state.step1_history,
                    questions,
                    answers,
                    api_key,
                    documents=docs_for_step2,
                )
            st.session_state.step2_result = analysis
            st.session_state.flow_stage = "done"

            # Step 3: persist immediately. This always creates a NEW
            # interview + its first run — rerunning an existing saved
            # interview against a different hypothesis happens on the
            # Interviews page instead, and never overwrites this one.
            # `person=None` here — interviewee metadata isn't confirmed
            # until the form just below; the digest is refreshed with the
            # interviewee filled in right after that confirm happens.
            digest = ai.build_digest(
                selected_hypotheses,
                analysis,
                raw_notes,
                api_key,
                person=None,
                additional_notes=additional_notes,
            )
            title = interview_title.strip() or default_title
            interview_id = storage.save_interview(title, raw_notes, notes=additional_notes)
            document_ids = [d["id"] for d in docs_for_step2]
            run_id = storage.save_run(
                interview_id,
                selected_hypotheses,
                questions,
                answers,
                analysis,
                digest,
                document_ids=document_ids,
            )
            st.session_state.saved_message = (
                f"Saved as interview #{interview_id}, run #{run_id}. "
                "View it any time on the Interviews page."
            )
            st.session_state.last_saved_interview_id = interview_id
        except ai.AIError as e:
            st.error(str(e))

if st.session_state.flow_stage == "done" and "step2_result" in st.session_state:
    if st.session_state.get("saved_message"):
        st.success(st.session_state.saved_message)

    # Step 6: suggest-and-confirm interviewee metadata. Fetched once per
    # saved interview (cached in session_state) and NEVER saved until the
    # user explicitly confirms — with no API key, or on any AI failure,
    # ai.suggest_metadata already falls back to all-blank fields.
    interview_id = st.session_state.get("last_saved_interview_id")
    if interview_id is not None:
        st.divider()
        st.subheader("Interviewee metadata (suggested — review before saving)")

        if "metadata_suggestion" not in st.session_state:
            with st.spinner("Suggesting interviewee metadata..."):
                st.session_state.metadata_suggestion = ai.suggest_metadata(raw_notes, api_key)

        if st.session_state.get("metadata_saved"):
            st.success("Metadata saved. View it on the People page.")
        else:
            suggestion = st.session_state.metadata_suggestion
            with st.form("metadata_form"):
                m_name = st.text_input("Name (or a label, if anonymous)", value=suggestion["name_or_label"])
                m_role = st.text_input("Role / title", value=suggestion["role"])
                m_org = st.text_input("Organization / unit", value=suggestion["organization"])
                m_seniority = st.text_input("Seniority level", value=suggestion["seniority_level"])
                m_rank = st.text_input("Rank", value=suggestion["rank"])
                m_branch = st.text_input(
                    "Branch / service", value=suggestion["branch_service"],
                    help="E.g. Army, Air Force, Navy, Marines, Space Force, civilian/other.",
                )
                m_relationship = st.selectbox(
                    "Relationship to the problem",
                    RELATIONSHIP_OPTIONS,
                    index=RELATIONSHIP_OPTIONS.index(suggestion["relationship"])
                    if suggestion["relationship"] in RELATIONSHIP_OPTIONS else 0,
                )
                m_date = st.date_input("Interview date", value=datetime.date.today())
                # Never AI-suggested — always defaults to "completed" and is
                # set by hand, since you're confirming this right after
                # finishing that interview's analysis.
                m_status = st.selectbox(
                    "Interview status",
                    INTERVIEW_STATUS_OPTIONS,
                    index=INTERVIEW_STATUS_OPTIONS.index("completed"),
                )
                m_descriptor = st.text_input("One-line descriptor", value=suggestion["descriptor"])
                metadata_confirmed = st.form_submit_button("Confirm and save metadata")

            if metadata_confirmed:
                person_id = storage.add_person(
                    name=m_name.strip(),
                    role=m_role.strip(),
                    organization=m_org.strip(),
                    seniority_level=m_seniority.strip(),
                    relationship=m_relationship,
                    interview_date=m_date.isoformat(),
                    descriptor=m_descriptor.strip(),
                    rank=m_rank.strip(),
                    branch_service=m_branch.strip(),
                    interview_status=m_status,
                )
                storage.set_interview_person(interview_id, person_id)

                # Refresh this interview's digest now that the interviewee
                # is known — it was built with person=None a few lines up,
                # before this form existed to confirm it.
                person = storage.get_person(person_id)
                existing_runs = storage.get_runs_for_interview(interview_id)
                if existing_runs:
                    latest_run = existing_runs[-1]
                    hypotheses_for_digest = st.session_state.get(
                        "selected_hypotheses", latest_run["hypotheses"]
                    )
                    refreshed_digest = ai.build_digest(
                        hypotheses_for_digest,
                        latest_run["output"],
                        raw_notes,
                        api_key,
                        person,
                        additional_notes=additional_notes,
                    )
                    storage.update_run_digest(latest_run["id"], refreshed_digest)

                st.session_state.metadata_saved = True

                # Hand off to the Interviews page for this one interview —
                # that's where the full synthesis (Mom Test audit,
                # pains/gains, hypothesis ledger, sharper questions, Slack
                # write-up, digest) lives for browsing/rerunning later, and
                # it's scoped to just this interview rather than showing it
                # a second time inline here. Pre-select it (by id, not by
                # assuming index 0, in case ordering ever changes) and flag
                # it so that page auto-expands its one run instead of
                # requiring an extra click right after you just finished it.
                interviews_after_save = storage.get_interviews()
                target_idx = next(
                    (i for i, iv in enumerate(interviews_after_save) if iv["id"] == interview_id),
                    0,
                )
                st.session_state["interviews_selectbox"] = target_idx
                st.session_state["just_processed_interview_id"] = interview_id
                st.switch_page("pages/1_Interviews.py")

    st.divider()
    st.header("Analysis results")

    # Step 7: export header. Resolved fresh each render so it reflects a
    # just-confirmed metadata save (this section is reached again via the
    # st.rerun() above) without any extra session-state tracking.
    export_interview = storage.get_interview(interview_id) if interview_id else None
    export_person = storage.get_person_for_interview(interview_id) if interview_id else None
    export_runs = storage.get_runs_for_interview(interview_id) if interview_id else []
    export_run = export_runs[-1] if export_runs else {}
    export_doc_titles = storage.get_document_titles(export_run.get("document_ids", []))
    export_header = build_export_header(export_interview, export_person, export_run, export_doc_titles)

    hypotheses_display = "; ".join(
        st.session_state.get("selected_hypotheses", [])
    ) or export_run.get("hypothesis_text", "")
    render_analysis(
        st.session_state.step2_result, hypotheses_display, export_header=export_header
    )
