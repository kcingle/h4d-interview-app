"""
Process_Interview.py — Entry point for the Streamlit app (renamed from
app.py so the sidebar shows "Process Interview" instead of the filename-
derived, unhelpful "app" — Streamlit's classic multipage nav has no
title override for the entry script, so the actual fix is the filename).
This is the home page: pick which reference documents to include, paste
raw interview notes, run the two-step AI analysis, save the result (Step
3), and confirm interviewee metadata (Step 6) — everything to do with
*processing* an interview, in the moment, lives here. Only once metadata
is confirmed (or explicitly skipped) does this hand off to the Interviews
page, pre-selected — that page is a pure browse/view surface for
already-processed interviews (select one from a dropdown, see its
output, or delete it) and no longer does any processing of its own.
Reruns against a different hypothesis aren't supported anywhere anymore
— rerun manually by starting a new interview here if you need one. Run
with:

    streamlit run Process_Interview.py

Other pages live in pages/ and are picked up automatically by Streamlit's
built-in multipage navigation (shown in the sidebar).
"""

import datetime

import streamlit as st

import ai
import auth
import env_store
import report_import
import storage
import ui_feedback
from render import render_hypothesis_picker

RELATIONSHIP_OPTIONS = ["", "beneficiary", "adjacent", "expert"]
INTERVIEW_STATUS_OPTIONS = list(storage.ALLOWED_INTERVIEW_STATUSES)

st.set_page_config(page_title="H4D Interview App — Process Interview", page_icon="🎙️")
auth.require_login()

st.title("Process Interview")

api_key = env_store.load_api_key()
if not api_key:
    st.warning(
        "No Anthropic API key set yet. Enter one on the **Settings** page, then come back here."
    )

if "flow_stage" not in st.session_state:
    st.session_state.flow_stage = "idle"


def _go_to_interviews(interview_id: int):
    """Hand off to the Interviews page (a pure browse/view surface),
    pre-selecting the interview just processed. By id, not index 0, in
    case ordering ever changes."""
    interviews_after_save = storage.get_interviews()
    target_idx = next(
        (i for i, iv in enumerate(interviews_after_save) if iv["id"] == interview_id), 0,
    )
    st.session_state["interviews_selectbox"] = target_idx
    st.session_state.flow_stage = "idle"
    st.switch_page("pages/1_Interviews.py")


# The metadata sheet takes over the whole page once an interview has been
# saved (processed or imported) — it renders first and nothing else on the
# page does, so you land directly on it rather than scrolling to find it.
if st.session_state.flow_stage == "metadata":
    st.success(
        "✅ Interview saved. Review the interviewee details below "
        "(pre-filled from the interview), then confirm."
    )
    st.subheader("Interviewee metadata (suggested — review before saving)")

    meta_interview_id = st.session_state.pending_metadata_interview_id
    meta_raw_text = st.session_state.pending_metadata_raw_text
    meta_notes = st.session_state.pending_metadata_notes
    meta_run_id = st.session_state.pending_metadata_run_id
    meta_hypotheses = st.session_state.pending_metadata_hypotheses
    meta_analysis = st.session_state.pending_metadata_analysis

    if st.session_state.get("metadata_suggestion_for") != meta_interview_id:
        with ui_feedback.heartbeat("Suggesting interviewee metadata..."):
            st.session_state.metadata_suggestion = ai.suggest_metadata(meta_raw_text, api_key)
            st.session_state.metadata_suggestion_for = meta_interview_id

    suggestion = st.session_state.metadata_suggestion
    with st.form(f"metadata_form_{meta_interview_id}"):
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
        try:
            suggested_date = datetime.date.fromisoformat(suggestion.get("interview_date") or "")
        except ValueError:
            suggested_date = datetime.date.today()
        m_date = st.date_input("Interview date", value=suggested_date)
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
            "Interviewer(s) — up to 5. One name per box (only pre-filled when "
            "an imported write-up names them); leave extras blank."
        )
        suggested_interviewers = list(suggestion.get("interviewers") or []) + [""] * 5
        ic1, ic2, ic3, ic4, ic5 = st.columns(5)
        with ic1:
            m_interviewer_1 = st.text_input(
                "Interviewer 1", value=suggested_interviewers[0],
                key=f"interviewer1_{meta_interview_id}",
            )
        with ic2:
            m_interviewer_2 = st.text_input(
                "Interviewer 2", value=suggested_interviewers[1],
                key=f"interviewer2_{meta_interview_id}",
            )
        with ic3:
            m_interviewer_3 = st.text_input(
                "Interviewer 3", value=suggested_interviewers[2],
                key=f"interviewer3_{meta_interview_id}",
            )
        with ic4:
            m_interviewer_4 = st.text_input(
                "Interviewer 4", value=suggested_interviewers[3],
                key=f"interviewer4_{meta_interview_id}",
            )
        with ic5:
            m_interviewer_5 = st.text_input(
                "Interviewer 5", value=suggested_interviewers[4],
                key=f"interviewer5_{meta_interview_id}",
            )

        mc1, mc2 = st.columns(2)
        with mc1:
            metadata_confirmed = st.form_submit_button("Confirm and save metadata")
        with mc2:
            metadata_skipped = st.form_submit_button("Skip for now")

    if metadata_confirmed:
        try:
            with storage.raise_db_errors():
                # Remembered across a failed attempt, so clicking Confirm
                # again after a database hiccup never adds the person twice.
                person_id = st.session_state.get("proc_meta_person_id")
                if person_id is None:
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
                    st.session_state.proc_meta_person_id = person_id
                # Linking the person retitles the interview to the standard
                # "(rank name, date)" format off the metadata just confirmed —
                # picking up any correction made to the suggested name above.
                storage.set_interview_person(meta_interview_id, person_id)

                # Refresh this run's digest now that the interviewee is known.
                person = storage.get_person(person_id)
                with ui_feedback.heartbeat("Saving the interviewee details (a few seconds)..."):
                    refreshed_digest = ai.build_digest(
                        meta_hypotheses, meta_analysis, meta_raw_text, api_key,
                        person, additional_notes=meta_notes or "",
                    )
                storage.update_run_digest(meta_run_id, refreshed_digest)
        except storage.DatabaseUnavailable as e:
            st.warning(f"⚠️ {e} Then click **Confirm and save metadata** again.")
            st.stop()

        for key in (
            "pending_metadata_interview_id", "pending_metadata_run_id",
            "pending_metadata_raw_text", "pending_metadata_notes",
            "pending_metadata_hypotheses", "pending_metadata_analysis",
            "metadata_suggestion", "metadata_suggestion_for", "proc_meta_person_id",
        ):
            st.session_state.pop(key, None)
        _go_to_interviews(meta_interview_id)

    if metadata_skipped:
        # Skipping saves no person, but the title still follows whatever
        # name is in the form — a correction to the suggested name
        # shouldn't be thrown away just because the rest was skipped.
        storage.update_interview_title(
            meta_interview_id,
            storage.build_interview_title(m_name, m_rank, m_date.isoformat()),
        )
        for key in (
            "pending_metadata_interview_id", "pending_metadata_run_id",
            "pending_metadata_raw_text", "pending_metadata_notes",
            "pending_metadata_hypotheses", "pending_metadata_analysis",
            "metadata_suggestion", "metadata_suggestion_for", "proc_meta_person_id",
        ):
            st.session_state.pop(key, None)
        _go_to_interviews(meta_interview_id)
    st.stop()

MODE_NEW = "🎙️ New interview — transcript or notes"
MODE_IMPORT = "📥 Pre-processed interview — upload a file"

st.subheader("What are you adding?")
input_mode = st.radio(
    "What are you adding?",
    [MODE_NEW, MODE_IMPORT],
    key="input_mode",
    horizontal=True,
    label_visibility="collapsed",
)
importing_processed_result = input_mode == MODE_IMPORT

if importing_processed_result:
    st.info(
        "Upload the finished write-up for ONE interview — e.g. a report "
        "exported from this app, or one a teammate produced elsewhere. No "
        "clarifying questions: it's read in, then you go straight to the "
        "interviewee metadata sheet to confirm. Its full text is kept as "
        "this interview's source material, so Corpus Chat and Search can "
        "use all of it."
    )
    uploaded_report = st.file_uploader(
        "Processed interview file (.docx, .pdf, .md, or .txt)",
        type=report_import.SUPPORTED_EXTENSIONS,
        key="processed_report_file",
    )
    report_text = ""
    if uploaded_report is not None:
        try:
            report_text = report_import.extract_text(
                uploaded_report.name, uploaded_report.getvalue()
            )
        except report_import.ReportImportError as e:
            st.error(str(e))
        else:
            st.success(
                f"Read {len(report_text.split()):,} words from “{uploaded_report.name}”."
            )
            with st.expander("Preview the extracted text"):
                st.text(report_text[:20000] + ("\n…" if len(report_text) > 20000 else ""))
    with st.expander("…or paste the write-up instead / add more text"):
        pasted_report = st.text_area(
            "Pasted write-up (added after the file's text if you use both)",
            height=150,
            key="raw_notes",
        )
        additional_notes = st.text_area(
            "Additional Notes (optional)",
            height=100,
            key="additional_notes",
            placeholder="Anything about this interview the write-up doesn't capture.",
        )
    raw_notes = "\n\n".join(t for t in (report_text.strip(), pasted_report.strip()) if t)
else:
    st.caption("Paste raw interview notes, then run the two-step AI analysis below.")

st.subheader(
    "Hypotheses this write-up covers" if importing_processed_result
    else "Hypotheses being tested"
)
st.caption(
    "Active hypotheses are pre-checked. Check or uncheck any to test one "
    "or more of them this run."
    if not importing_processed_result else
    "Active hypotheses are pre-checked. The write-up's verdict on each "
    "checked one is pulled into the hypothesis ledger (Untested if it "
    "doesn't address it)."
)
hypothesis_tree = storage.get_hypothesis_tree()
selected_hypotheses = render_hypothesis_picker(hypothesis_tree, key_prefix="process_hyp")
if not selected_hypotheses:
    st.warning("Select at least one hypothesis to test.")

selected_documents = []
uploaded_media = []
media_caption = ""

if not importing_processed_result:
    st.subheader("Reference documents to include")
    available_documents = storage.get_documents()

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

    st.subheader("Interview notes")
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

    st.subheader("Photos, videos & other media (optional)")
    _media_max_mb = storage.VISUAL_RESOURCE_MAX_BYTES / (1024 * 1024)
    st.caption(
        f"Whiteboard photos, screen recordings, short clips — anything visual "
        f"from this interview. Saved the moment this interview saves, and "
        f"browsable later on the Visual Resources page. {_media_max_mb:.0f} MB max per file."
    )
    uploaded_media = st.file_uploader(
        "Upload photos, videos, or other files",
        type=[
            "png", "jpg", "jpeg", "gif", "webp", "heic", "heif", "bmp", "tiff", "svg",
            "mp4", "mov", "webm", "avi", "m4v", "mkv", "3gp",
        ],
        accept_multiple_files=True,
        key="media_uploader",
    )
    media_caption = st.text_input(
        "Caption for these files (optional — applies to everything uploaded "
        "above; edit individually later on Visual Resources)",
        key="media_caption",
    )


def _finish_analysis_and_save(
    analysis: dict,
    clarifying_skipped: bool = False,
    imported_result: bool = False,
    metadata_suggestion: dict | None = None,
):
    """Step 2 onward, given an already-computed Step 2 `analysis`: save
    the interview + run + any media, then move into the metadata-
    confirmation stage below (still on this page — that's still
    "processing this interview in the moment"). Shared by every path
    that can reach "no more clarifying questions to ask" — the model
    needing nothing at all on round 1, the adaptive loop below finishing
    naturally, and the "already-processed result" import path, which
    skips the clarifying loop and this app's own analysis entirely.
    `clarifying_skipped`/`imported_result` record which of those applies
    (both False for the normal adaptive-clarifying path) so a run this
    page can display or export distinguishes "asked, model needed
    nothing" from "imported, never asked or analyzed here".
    `metadata_suggestion` (import path only) is the interviewee metadata
    ai.parse_processed_result already read off the write-up — used
    instead of a separate ai.suggest_metadata call, and it can carry the
    real interview date and interviewers too.

    Safe to call again after a database failure: whatever already saved
    (the interview row, its run) is remembered in session_state and not
    written twice, so "Try again" never creates a duplicate interview."""
    docs_for_step2 = st.session_state.get("selected_documents", [])
    hypotheses_for_run = st.session_state.get("selected_hypotheses") or selected_hypotheses
    # Step 3: persist immediately. This always creates a NEW interview +
    # its first run. `person=None` here — interviewee metadata isn't
    # confirmed yet; that happens in the metadata stage right below,
    # which regenerates this digest once the person is known.
    if st.session_state.get("proc_digest") is None:
        with ui_feedback.heartbeat("Indexing quotes and topics for search (a few seconds)..."):
            st.session_state.proc_digest = ai.build_digest(
                hypotheses_for_run, analysis, raw_notes, api_key,
                person=None, additional_notes=additional_notes,
            )
    digest = st.session_state.proc_digest
    # Identify the interviewee BEFORE the interview row is created, so it
    # is saved under their name on the very first write — there is never a
    # moment where a provisional, nameless title exists to be left behind
    # if the confirmation step below is skipped. This is the same single
    # Haiku call the metadata form used to make on arrival, just moved
    # earlier; it's stashed below so that form reuses it rather than
    # paying for it twice, and it never raises (blank dict on failure).
    if metadata_suggestion is not None:
        suggestion = metadata_suggestion
    elif st.session_state.get("proc_suggestion") is not None:
        suggestion = st.session_state.proc_suggestion
    else:
        with ui_feedback.heartbeat("Identifying the interviewee (a few seconds)..."):
            suggestion = ai.suggest_metadata(raw_notes, api_key)
    st.session_state.proc_suggestion = suggestion
    title = storage.build_interview_title(
        suggestion["name_or_label"],
        suggestion["rank"],
        suggestion.get("interview_date") or datetime.date.today().isoformat(),
    )
    with storage.raise_db_errors():
        interview_id = st.session_state.get("proc_saved_interview_id")
        if interview_id is None:
            interview_id = storage.save_interview(title, raw_notes, notes=additional_notes)
            st.session_state.proc_saved_interview_id = interview_id
        document_ids = [d["id"] for d in docs_for_step2]
        answered = st.session_state.get("adaptive_answered", [])
        run_id = st.session_state.get("proc_saved_run_id")
        if run_id is None:
            run_id = storage.save_run(
                interview_id,
                hypotheses_for_run,
                [q for q, _ in answered],
                [a for _, a in answered],
                analysis,
                digest,
                document_ids=document_ids,
                clarifying_skipped=clarifying_skipped,
                imported_result=imported_result,
            )
            st.session_state.proc_saved_run_id = run_id

        # Save any uploaded media against this interview. A file over the
        # size cap doesn't block the interview itself from saving — that
        # analysis work is done and shouldn't be lost over one oversized
        # upload — it's just skipped, with the reason shown once we land on
        # Interviews.
        media_errors = []
        for filename, content, mime_type in st.session_state.get("pending_media", []):
            try:
                storage.add_visual_resource(
                    interview_id, filename, content, mime_type,
                    caption=st.session_state.get("pending_media_caption", ""),
                )
            except storage.VisualResourceError as e:
                media_errors.append(str(e))
        if media_errors:
            st.session_state["media_upload_errors"] = media_errors

    # Move into the metadata-confirmation stage, still on this page —
    # stash what that stage needs, since the widgets above (raw_notes,
    # additional_notes, etc.) won't be there once flow_stage changes.
    st.session_state["pending_metadata_interview_id"] = interview_id
    st.session_state["pending_metadata_run_id"] = run_id
    st.session_state["pending_metadata_raw_text"] = raw_notes
    st.session_state["pending_metadata_notes"] = additional_notes
    st.session_state["pending_metadata_hypotheses"] = hypotheses_for_run
    st.session_state["pending_metadata_analysis"] = analysis
    st.session_state["metadata_suggestion"] = suggestion
    st.session_state["metadata_suggestion_for"] = interview_id
    for key in (
        "pending_media", "pending_media_caption", "adaptive_history",
        "adaptive_current_question", "adaptive_round", "adaptive_answered",
        *_PROC_PENDING_KEYS,
    ):
        st.session_state.pop(key, None)
    ui_feedback.clear_failure("process")
    st.session_state.flow_stage = "metadata"
    st.rerun()


# Everything a half-finished run remembers between a failure and its
# "Try again", so a retry resumes where it stopped instead of starting
# over (or saving twice). Cleared on success and on every fresh Start.
_PROC_PENDING_KEYS = (
    "proc_pending_analysis", "proc_pending_flags", "proc_digest",
    "proc_suggestion", "proc_saved_interview_id", "proc_saved_run_id",
    "proc_pending_answer", "proc_retry_action",
)

WAIT_FIRST_QUESTION = (
    "Reading the interview and choosing the first clarifying question "
    "(a few seconds)..."
)
WAIT_NEXT_QUESTION = "Choosing the next question based on your answer (a few seconds)..."
WAIT_ANALYSIS = (
    "Analyzing the interview against the selected hypotheses. This usually "
    "takes about a minute and can take up to 3 minutes. Please keep this tab open..."
)
WAIT_IMPORT = (
    "Reading the processed interview into this app's structure. This takes "
    "about a minute..."
)


def _analyze_and_save():
    """Run the graded analysis (unless an earlier attempt already finished
    it) and save. Keeping the finished analysis in session_state means a
    database failure during the save never costs another minute-long AI
    call on retry."""
    if st.session_state.get("proc_pending_analysis") is None:
        with ui_feedback.heartbeat(WAIT_ANALYSIS):
            st.session_state.proc_pending_analysis = ai.run_step2_after_adaptive_clarifying(
                st.session_state.adaptive_history, api_key,
                documents=st.session_state.get("selected_documents", []),
            )
    flags = st.session_state.get("proc_pending_flags") or {}
    _finish_analysis_and_save(st.session_state.proc_pending_analysis, **flags)


def _do_start():
    if importing_processed_result:
        # Nothing to clarify and nothing to analyze — the write-up
        # already exists; just reformat it into this app's structure.
        # flow_stage never enters "clarifying" on this path.
        if st.session_state.get("proc_pending_analysis") is None:
            with ui_feedback.heartbeat(WAIT_IMPORT):
                analysis, imported_metadata = ai.parse_processed_result(
                    st.session_state.get("selected_hypotheses") or selected_hypotheses,
                    raw_notes,
                    api_key,
                    additional_notes=additional_notes,
                )
            st.session_state.proc_pending_analysis = analysis
            st.session_state.proc_pending_flags = {
                "imported_result": True, "metadata_suggestion": imported_metadata,
            }
        _analyze_and_save()
        return
    with ui_feedback.heartbeat(WAIT_FIRST_QUESTION):
        step1 = ai.start_adaptive_clarifying(
            st.session_state.get("selected_hypotheses") or selected_hypotheses,
            raw_notes,
            api_key,
            documents=st.session_state.get("selected_documents", []),
            additional_notes=additional_notes,
        )
    st.session_state.adaptive_history = step1["history"]
    if step1["question"]:
        st.session_state.adaptive_current_question = step1["question"]
        st.session_state.adaptive_round = step1["round"]
        st.session_state.flow_stage = "clarifying"
        st.rerun()
    else:
        # The model decided it needs nothing at all for this interview —
        # go straight to the full analysis rather than showing an empty
        # clarifying step with nothing to answer.
        st.session_state.adaptive_current_question = None
        st.session_state.flow_stage = "clarifying"
        _analyze_and_save()


def _do_answer():
    """Send the stashed answer to the current question. The answer is
    only recorded in "Answered so far" once the AI call succeeds, so a
    retry after a failure never records it twice."""
    question = st.session_state.adaptive_current_question
    answer = st.session_state.get("proc_pending_answer", "")
    with ui_feedback.heartbeat(WAIT_NEXT_QUESTION):
        nxt = ai.continue_adaptive_clarifying(
            st.session_state.adaptive_history,
            question,
            answer,
            st.session_state.adaptive_round,
            api_key,
            documents=st.session_state.get("selected_documents", []),
        )
    st.session_state.adaptive_answered.append((question, answer))
    st.session_state.adaptive_history = nxt["history"]
    st.session_state.pop("proc_pending_answer", None)
    if nxt["question"]:
        st.session_state.adaptive_current_question = nxt["question"]
        st.session_state.adaptive_round = nxt["round"]
        st.rerun()
    # No more questions: from here a retry only re-runs the analysis/save.
    st.session_state.adaptive_current_question = None
    _analyze_and_save()


_PROC_ACTIONS = {"start": _do_start, "answer": _do_answer, "analyze": _analyze_and_save}


def _run_step(action_name: str):
    """Run one step of the flow. Any AI or database failure becomes a
    calm notice with a "Try again" button that re-runs the same step."""
    ui_feedback.clear_failure("process")
    st.session_state.proc_retry_action = action_name
    try:
        _PROC_ACTIONS[action_name]()
    except (ai.AIError, storage.DatabaseUnavailable) as e:
        ui_feedback.remember_failure("process", str(e))
        st.rerun()


def _render_failure_notice():
    message = ui_feedback.pending_failure("process")
    if not message:
        return
    action = st.session_state.get("proc_retry_action") or "start"
    if (
        st.session_state.flow_stage == "clarifying"
        and st.session_state.get("adaptive_current_question") is None
    ):
        # Every question is answered; only the analysis/save is left.
        action = "analyze"
    if ui_feedback.retry_notice(message, key=f"proc_retry_{action}"):
        _run_step(action)


start_clicked = st.button(
    "Import → review metadata" if importing_processed_result else "Start",
    type="primary",
    disabled=(
        not raw_notes.strip()
        or not selected_hypotheses
        # Also disabled mid-flow (clarifying questions or metadata
        # confirmation in progress) so a stray click can't abandon that
        # in-progress interview's state before it's saved/confirmed.
        or st.session_state.flow_stage != "idle"
    ),
)

if start_clicked:
    # Capture the checked document set and hypothesis list once, here, and
    # reuse them for the Step 2 / digest calls below — so the whole
    # conversation sees the same reference material and hypotheses.
    st.session_state.selected_documents = selected_documents
    st.session_state.selected_hypotheses = selected_hypotheses
    # Read each file's bytes now, at Start time, rather than re-reading the
    # file_uploader widget after the clarifying-questions round trip below —
    # same reasoning as freezing selected_documents/selected_hypotheses
    # above: an UploadedFile's read position is also good for one read only.
    st.session_state.pending_media = [
        (f.name, f.getvalue(), f.type or "application/octet-stream")
        for f in (uploaded_media or [])
    ]
    st.session_state.pending_media_caption = media_caption.strip()
    st.session_state.adaptive_answered = []
    for key in _PROC_PENDING_KEYS:
        st.session_state.pop(key, None)
    _run_step("start")

if st.session_state.flow_stage == "idle":
    _render_failure_notice()

if st.session_state.flow_stage == "clarifying":
    st.divider()
    if st.session_state.get("adaptive_current_question") is None:
        # All questions answered; only the analysis/save is left (shown
        # here only if it failed and is waiting for "Try again").
        st.subheader("Clarifying questions done")
    else:
        st.subheader("Clarifying question")
        st.caption(
            f"Question {st.session_state.adaptive_round} of "
            f"{ai.MAX_ADAPTIVE_QUESTIONS} — each one is chosen after seeing your "
            "last answer (Flipped Interaction: the model interrogates you "
            "before analyzing anything, rather than the other way around)."
        )

    if st.session_state.get("adaptive_answered"):
        with st.expander("Answered so far"):
            for q, a in st.session_state.adaptive_answered:
                st.markdown(f"**Q:** {q}")
                st.markdown(f"**A:** {a or '_(no answer given)_'}")
                st.markdown("---")

    if st.session_state.get("adaptive_current_question") is not None:
        with st.form("adaptive_answer_form"):
            # Keyed per round so each new question starts with an empty box.
            answer = st.text_area(
                st.session_state.adaptive_current_question,
                key=f"adaptive_answer_box_{st.session_state.adaptive_round}",
            )
            submitted = st.form_submit_button("Answer")
        if submitted:
            st.session_state.proc_pending_answer = answer
            _run_step("answer")

    _render_failure_notice()
