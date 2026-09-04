"""
pages/1_Interviews.py — Browse saved interviews, review every past run for
one (each run kept forever, never overwritten), and rerun it against a
different hypothesis, which adds a brand-new run alongside the old ones.
"""

import streamlit as st

import ai
import env_store
import storage
from render import build_export_header, render_analysis, render_hypothesis_picker

st.set_page_config(page_title="H4D Interview App — Interviews", page_icon="🗂️")

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

st.subheader(selected["title"])
st.caption(f"Saved {selected['created_at']}")
with st.expander("Raw interview notes"):
    st.text(selected["raw_text"])
if selected.get("notes"):
    with st.expander("Additional notes"):
        st.text(selected["notes"])

st.divider()
st.subheader("Past runs")

runs = storage.get_runs_for_interview(selected["id"])
# Step 7: same person for every run of this interview — look up once.
interview_person = storage.get_person_for_interview(selected["id"])
digest_api_key = env_store.load_api_key()

# Set by Process Interview right before it hands off here after you finish
# and confirm metadata for a brand-new interview — auto-expand that one
# run so the synthesis is visible immediately, no extra click needed.
# Popped (not just read) so this only fires once, on the landing view.
just_processed_id = st.session_state.pop("just_processed_interview_id", None)

if not runs:
    st.write("No runs yet for this interview.")
else:
    for i, run in enumerate(runs, start=1):
        when = run["created_at"][:19].replace("T", " ")
        auto_expand = just_processed_id == selected["id"] and i == len(runs)
        with st.expander(
            f"Run {i} — hypothesis: {run['hypothesis_text']} — {when}", expanded=auto_expand
        ):
            export_header = build_export_header(
                selected, interview_person, run, storage.get_document_titles(run["document_ids"])
            )
            render_analysis(
                run["output"],
                run["hypothesis_text"],
                key_prefix=f"run_{run['id']}_",
                export_header=export_header,
            )

            st.divider()
            st.subheader("Digest (for corpus features)")
            digest = run.get("digest") or {}
            if digest.get("digest_version", 1) >= 2:
                st.json(digest)
            else:
                st.caption(
                    "This run has an old, thin digest from before the richer "
                    "format existed — regenerate it below."
                )
            if st.button("🔄 Regenerate digest", key=f"regen_digest_{run['id']}"):
                new_digest = ai.build_digest(
                    run["hypotheses"],
                    run["output"],
                    selected["raw_text"],
                    digest_api_key,
                    interview_person,
                    additional_notes=selected.get("notes") or "",
                )
                storage.update_run_digest(run["id"], new_digest)
                st.success("Digest regenerated.")
                st.rerun()

st.divider()
st.subheader("Rerun this interview")
st.caption(
    "Runs the same two-step AI flow on this interview's saved notes against "
    "the hypotheses checked below, and adds the result as a new run — "
    "earlier runs are kept."
)

api_key = env_store.load_api_key()
if not api_key:
    st.warning("No Anthropic API key set yet. Enter one on the **Settings** page first.")

interview_id = selected["id"]
rerun_stage_key = f"rerun_stage_{interview_id}"
if rerun_stage_key not in st.session_state:
    st.session_state[rerun_stage_key] = "idle"

rerun_hypothesis_tree = storage.get_hypothesis_tree()
rerun_hypotheses = render_hypothesis_picker(
    rerun_hypothesis_tree, key_prefix=f"rerun_hyp_{interview_id}"
)
if not rerun_hypotheses:
    st.warning("Select at least one hypothesis to test.")

if st.button(
    "Start rerun",
    key=f"start_rerun_{interview_id}",
    disabled=not rerun_hypotheses,
):
    try:
        with st.spinner("Asking clarifying questions..."):
            step1 = ai.run_step1(
                rerun_hypotheses,
                selected["raw_text"],
                api_key,
                additional_notes=selected.get("notes") or "",
            )
        st.session_state[f"rerun_questions_{interview_id}"] = step1["questions"]
        st.session_state[f"rerun_history_{interview_id}"] = step1["history"]
        st.session_state[f"rerun_hypotheses_used_{interview_id}"] = rerun_hypotheses
        st.session_state[rerun_stage_key] = "awaiting_answers"
    except ai.AIError as e:
        st.error(str(e))

if st.session_state[rerun_stage_key] == "awaiting_answers":
    rerun_questions = st.session_state.get(f"rerun_questions_{interview_id}", [])

    if not rerun_questions:
        st.write("The AI had no clarifying questions for this interview.")

    with st.form(f"rerun_answers_form_{interview_id}"):
        rerun_answers = [
            st.text_area(f"Q{i + 1}. {q}", key=f"rerun_answer_{interview_id}_{i}")
            for i, q in enumerate(rerun_questions)
        ]
        rerun_submitted = st.form_submit_button("Continue → Run full analysis")

    if rerun_submitted:
        try:
            with st.spinner("Running the full analysis..."):
                rerun_history = st.session_state[f"rerun_history_{interview_id}"]
                analysis = ai.run_step2(rerun_history, rerun_questions, rerun_answers, api_key)
            hypotheses_used = st.session_state[f"rerun_hypotheses_used_{interview_id}"]
            digest = ai.build_digest(
                hypotheses_used,
                analysis,
                selected["raw_text"],
                api_key,
                interview_person,
                additional_notes=selected.get("notes") or "",
            )
            # Step 5: no document checklist on this rerun control yet
            # (only the Process Interview page has one) — record an empty
            # document set rather than omitting provenance entirely.
            new_run_id = storage.save_run(
                interview_id, hypotheses_used, rerun_questions, rerun_answers, analysis, digest,
                document_ids=[],
            )
            st.session_state[rerun_stage_key] = "idle"
            st.success(f"Saved as run #{new_run_id}. Earlier runs for this interview are unchanged.")
            st.rerun()
        except ai.AIError as e:
            st.error(str(e))
