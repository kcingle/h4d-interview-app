"""
pages/1_Interviews.py — Browse saved interviews, review every past run for
one (each run kept forever, never overwritten), rerun it against a
different hypothesis (adds a brand-new run alongside the old ones), and
confirm interviewee metadata for a freshly-processed interview. That
suggest-and-confirm form used to live on Process Interview, gating the
redirect here on filling it out first — moved here so the handoff from
Process Interview is immediate, never gated on a form (see Process_Interview.py).
"""

import datetime

import streamlit as st

import ai
import auth
import env_store
import storage
from render import build_export_header, render_analysis, render_hypothesis_picker

RELATIONSHIP_OPTIONS = ["", "beneficiary", "adjacent", "expert"]
INTERVIEW_STATUS_OPTIONS = list(storage.ALLOWED_INTERVIEW_STATUSES)

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
with st.expander("Raw interview notes"):
    st.text(selected["raw_text"])
if selected.get("notes"):
    with st.expander("Additional notes"):
        st.text(selected["notes"])

if not st.session_state.get(f"confirm_delete_interview_{interview_id}"):
    if st.button("🗑️ Delete this interview", key=f"delete_interview_btn_{interview_id}"):
        st.session_state[f"confirm_delete_interview_{interview_id}"] = True
        st.rerun()
else:
    st.warning(
        "This cannot be undone and deletes every run this interview has "
        "(the linked person, if any, is kept). Delete this interview permanently?"
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

# Set by Process Interview right before it hands off here for a
# freshly-processed interview. Deliberately NOT popped just for being
# read — it stays set (and the metadata prompt below keeps showing)
# until metadata is actually confirmed or explicitly skipped, so an
# unrelated rerun of this same page view doesn't make the prompt vanish
# before you've dealt with it. It also drives the "auto-expand this run"
# behavior further down.
just_processed_id = st.session_state.get("just_processed_interview_id")
show_metadata_prompt = just_processed_id == interview_id and interview_person is None

if show_metadata_prompt:
    st.divider()
    st.subheader("Interviewee metadata (suggested — review before saving)")

    if st.session_state.get("metadata_suggestion_for") != interview_id:
        with st.spinner("Suggesting interviewee metadata..."):
            st.session_state.metadata_suggestion = ai.suggest_metadata(
                selected["raw_text"], env_store.load_api_key()
            )
            st.session_state.metadata_suggestion_for = interview_id

    suggestion = st.session_state.metadata_suggestion
    with st.form(f"metadata_form_{interview_id}"):
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
        # Never AI-suggested — always defaults to "completed" and is set
        # by hand, since you're confirming this right after finishing
        # that interview's analysis.
        m_status = st.selectbox(
            "Interview status",
            INTERVIEW_STATUS_OPTIONS,
            index=INTERVIEW_STATUS_OPTIONS.index("completed"),
        )
        m_descriptor = st.text_input("One-line descriptor", value=suggestion["descriptor"])

        st.caption(
            "Interviewer(s) — up to 5. One name per box (never AI-suggested); "
            "leave extras blank."
        )
        ic1, ic2, ic3, ic4, ic5 = st.columns(5)
        with ic1:
            m_interviewer_1 = st.text_input("Interviewer 1", key=f"interviewer1_{interview_id}")
        with ic2:
            m_interviewer_2 = st.text_input("Interviewer 2", key=f"interviewer2_{interview_id}")
        with ic3:
            m_interviewer_3 = st.text_input("Interviewer 3", key=f"interviewer3_{interview_id}")
        with ic4:
            m_interviewer_4 = st.text_input("Interviewer 4", key=f"interviewer4_{interview_id}")
        with ic5:
            m_interviewer_5 = st.text_input("Interviewer 5", key=f"interviewer5_{interview_id}")

        mc1, mc2 = st.columns(2)
        with mc1:
            metadata_confirmed = st.form_submit_button("Confirm and save metadata")
        with mc2:
            metadata_skipped = st.form_submit_button("Skip for now")

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
            interviewers=[
                m_interviewer_1, m_interviewer_2, m_interviewer_3,
                m_interviewer_4, m_interviewer_5,
            ],
        )
        storage.set_interview_person(interview_id, person_id)

        # Refresh this interview's latest digest now that the
        # interviewee is known.
        person = storage.get_person(person_id)
        existing_runs = storage.get_runs_for_interview(interview_id)
        if existing_runs:
            latest_run = existing_runs[-1]
            refreshed_digest = ai.build_digest(
                latest_run["hypotheses"],
                latest_run["output"],
                selected["raw_text"],
                env_store.load_api_key(),
                person,
                additional_notes=selected.get("notes") or "",
            )
            storage.update_run_digest(latest_run["id"], refreshed_digest)

        st.session_state.pop("just_processed_interview_id", None)
        st.session_state.pop("metadata_suggestion", None)
        st.session_state.pop("metadata_suggestion_for", None)
        st.success("Metadata saved. View it on the Metadata page.")
        st.rerun()

    if metadata_skipped:
        st.session_state.pop("just_processed_interview_id", None)
        st.session_state.pop("metadata_suggestion", None)
        st.session_state.pop("metadata_suggestion_for", None)
        st.rerun()

st.divider()
st.subheader("Past runs")

runs = storage.get_runs_for_interview(interview_id)
digest_api_key = env_store.load_api_key()

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
