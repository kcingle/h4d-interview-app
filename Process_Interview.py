"""
Process_Interview.py — Entry point for the Streamlit app (renamed from
app.py so the sidebar shows "Process Interview" instead of the filename-
derived, unhelpful "app" — Streamlit's classic multipage nav has no
title override for the entry script, so the actual fix is the filename).
This is the home page: pick which reference documents to include, paste
raw interview notes, run the two-step AI analysis, and save the result
(Step 3). The moment that save succeeds, this page hands off IMMEDIATELY
to the Interviews page for this one interview (pre-selected, its one run
auto-expanded) — that's where the full synthesis lives, and where the
suggest-and-confirm interviewee metadata form now happens too (moved
there so the handoff is never gated on filling out that form first — an
earlier version wasn't redirecting until metadata was confirmed, which
read as "nothing happens" since results already showed inline here
regardless). Reruns against a different hypothesis happen from the
Interviews page instead. Run with:

    streamlit run Process_Interview.py

Other pages live in pages/ and are picked up automatically by Streamlit's
built-in multipage navigation (shown in the sidebar).
"""

import datetime

import streamlit as st

import ai
import env_store
import storage
from render import render_hypothesis_picker

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
    # Capture the checked document set and hypothesis list once, here, and
    # reuse them for the Step 2 / digest calls below — so the whole
    # conversation sees the same reference material and hypotheses.
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

if st.session_state.flow_stage == "awaiting_answers":
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
            # Step 3: persist immediately. This always creates a NEW
            # interview + its first run — rerunning an existing saved
            # interview against a different hypothesis happens on the
            # Interviews page instead, and never overwrites this one.
            # `person=None` here — interviewee metadata isn't confirmed
            # yet; that suggest-and-confirm form now lives on the
            # Interviews page (see just_processed_interview_id below), so
            # the handoff to it never has to wait on filling out a form.
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
            storage.save_run(
                interview_id,
                selected_hypotheses,
                questions,
                answers,
                analysis,
                digest,
                document_ids=document_ids,
            )

            # Hand off IMMEDIATELY to the Interviews page for this one
            # interview — that's where the full synthesis (Mom Test
            # audit, pains/gains, hypothesis ledger, sharper questions,
            # Slack write-up, digest) lives, and where interviewee
            # metadata now gets suggested/confirmed too. Pre-select it
            # (by id, not by assuming index 0, in case ordering ever
            # changes) and flag it so that page both auto-expands its one
            # run and offers the metadata form for it.
            interviews_after_save = storage.get_interviews()
            target_idx = next(
                (i for i, iv in enumerate(interviews_after_save) if iv["id"] == interview_id),
                0,
            )
            st.session_state["interviews_selectbox"] = target_idx
            st.session_state["just_processed_interview_id"] = interview_id
            st.switch_page("pages/1_Interviews.py")
        except ai.AIError as e:
            st.error(str(e))
