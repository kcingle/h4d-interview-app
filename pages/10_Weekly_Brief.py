"""
pages/10_Weekly_Brief.py — Builds the recurring GOVT 391 team-brief
PowerPoint from real app data, in three explicit stages where you stay in
control the whole way (see weekly_brief.py for the template-filling
mechanics):

  STAGE 1 — CHOOSE: pick which hypotheses, which runs to pull test
  questions from, an owner per hypothesis, and which scheduled interviews
  go on the Discovery Plan slide. All selectors — nothing typed here.

  STAGE 2 — EDIT: every template slot as an editable field. Hypothesis
  statements and test questions PRE-FILL from real stored data (the tree,
  and sharper_questions from the runs picked in Stage 1); judgment fields
  (problem statement, what-changed, discovery-plan needs) start BLANK —
  never fabricated. Every field is freely rewritable, nothing is locked.

  STAGE 3 — FINALIZE: only happens on the "Build the deck" click, which
  calls weekly_brief.build_deck() and offers the .pptx for download.
  Nothing is generated before that click.

Going back to Stage 1 and clicking "Continue" again re-derives Stage 2's
defaults from scratch (see _gen below) — deliberately simple over trying
to preserve manual edits across a changed hypothesis selection.
"""

import datetime

import streamlit as st

import auth
import storage
import weekly_brief

st.set_page_config(page_title="H4D Interview App — Weekly Brief", page_icon="📋")
auth.require_login()

st.title("Weekly Brief")
st.caption(
    "Build this week's GOVT 391 team-brief PowerPoint from real hypotheses, "
    "test questions, and interviews — you choose the inputs, edit every "
    "field, and nothing is generated until you click Build."
)

if "brief_stage" not in st.session_state:
    st.session_state.brief_stage = "choose"
if "brief_gen" not in st.session_state:
    st.session_state.brief_gen = 0


def _flatten(nodes: list[dict], depth: int = 0) -> list[tuple[int, dict]]:
    flat = []
    for node in nodes:
        flat.append((depth, node))
        flat.extend(_flatten(node["children"], depth + 1))
    return flat


def _next_tuesday() -> datetime.date:
    """The upcoming Tuesday (today, if today already is one) — just a
    starting point for the date picker below; freely editable there."""
    today = datetime.date.today()
    days_ahead = (1 - today.weekday()) % 7  # Monday=0 ... Tuesday=1
    return today + datetime.timedelta(days=days_ahead)


def _format_brief_date(d: datetime.date) -> str:
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"


# =============================================================================
# STAGE 1 — CHOOSE
# =============================================================================

if st.session_state.brief_stage == "choose":
    tree = storage.get_hypothesis_tree()
    flat = _flatten(tree)

    if not flat:
        st.write("No hypotheses yet — add some on the **Hypotheses** page first.")
        st.stop()

    roster = weekly_brief.get_team_roster()

    st.subheader("1 · Which hypotheses go on this week's brief?")
    st.caption(
        f"The template has exactly {weekly_brief.HYPOTHESIS_SLOTS} hypothesis slots — "
        f"pick exactly {weekly_brief.HYPOTHESIS_SLOTS}. Active ones are checked by default."
    )

    checked_nodes = []
    for depth, node in flat:
        default = node["state"] == "active"
        label = f"{'　' * depth}**{node['label']}** — {node['text'][:90]}"
        if st.checkbox(label, value=default, key=f"brief_hyp_check_{node['id']}"):
            checked_nodes.append(node)

    st.caption(f"{len(checked_nodes)} of {weekly_brief.HYPOTHESIS_SLOTS} selected.")

    hyp_choices = {}  # node id -> {"node", "owner", "runs", "question_candidates", "checked_questions"}

    if checked_nodes:
        st.divider()
        st.subheader("2 · Owner, and which analyses to pull test questions from")

    for node in checked_nodes:
        with st.expander(f"{node['label']} — {node['text'][:70]}", expanded=True):
            owner = st.selectbox(
                "Owner", options=(roster or ["(no team roster found in the template)"]),
                key=f"brief_owner_{node['id']}",
            )

            matching_runs = storage.get_runs_testing_hypothesis(node["text"])
            run_labels = {
                r["id"]: f"{r['interview_title']} — {r['created_at'][:10]}" for r in matching_runs
            }
            if not matching_runs:
                st.caption("No interview has tested this exact hypothesis text yet — test questions will start blank.")
                selected_run_ids = []
            else:
                selected_run_ids = st.multiselect(
                    "Pull test questions from",
                    options=list(run_labels.keys()),
                    default=list(run_labels.keys()),
                    format_func=lambda i: run_labels[i],
                    key=f"brief_runs_{node['id']}",
                )

            candidates = []
            seen = set()
            for r in matching_runs:
                if r["id"] not in selected_run_ids:
                    continue
                for q in (r.get("output") or {}).get("sharper_questions", []):
                    if q not in seen:
                        seen.add(q)
                        candidates.append({"question": q, "source": r["interview_title"]})

            checked_questions = []
            if candidates:
                st.caption(
                    f"Which {weekly_brief.TESTS_PER_HYPOTHESIS} (max) go on the slide "
                    f"— from the sharper questions those analyses actually produced:"
                )
                for i, c in enumerate(candidates):
                    default_checked = i < weekly_brief.TESTS_PER_HYPOTHESIS
                    if st.checkbox(
                        f"{c['question']}  _(from {c['source']})_",
                        value=default_checked,
                        key=f"brief_q_check_{node['id']}_{i}",
                    ):
                        checked_questions.append(c["question"])
                if len(checked_questions) > weekly_brief.TESTS_PER_HYPOTHESIS:
                    st.warning(
                        f"{len(checked_questions)} checked — only the first "
                        f"{weekly_brief.TESTS_PER_HYPOTHESIS} will be used."
                    )

            hyp_choices[node["id"]] = {
                "node": node, "owner": owner,
                "questions": checked_questions[: weekly_brief.TESTS_PER_HYPOTHESIS],
            }

    st.divider()
    st.subheader("3 · Discovery Plan — which scheduled interviews go on this week's brief?")
    scheduled_people = [p for p in storage.get_people() if p["interview_status"] == "scheduled"]
    if not scheduled_people:
        st.caption("Nobody's marked \"scheduled\" on the Metadata page yet — this table will start blank.")
        selected_people_ids = []
    else:
        people_labels = {
            p["id"]: f"{p['name']} — {p['role'] or 'role not set'} — {p['interview_date'] or 'no date'}"
            for p in scheduled_people
        }
        st.caption(f"Up to {weekly_brief.INTERVIEWS_QUEUED_ROWS} — the table has that many rows.")
        selected_people_ids = st.multiselect(
            "Scheduled interviews to list",
            options=list(people_labels.keys()),
            default=list(people_labels.keys())[: weekly_brief.INTERVIEWS_QUEUED_ROWS],
            format_func=lambda i: people_labels[i],
            key="brief_queue_people",
        )
        if len(selected_people_ids) > weekly_brief.INTERVIEWS_QUEUED_ROWS:
            st.warning(
                f"{len(selected_people_ids)} selected — only the first "
                f"{weekly_brief.INTERVIEWS_QUEUED_ROWS} will be used."
            )

    st.divider()
    ready = len(checked_nodes) == weekly_brief.HYPOTHESIS_SLOTS
    if not ready:
        st.warning(f"Select exactly {weekly_brief.HYPOTHESIS_SLOTS} hypotheses to continue.")

    if st.button("Continue to Edit →", type="primary", disabled=not ready):
        # Build Stage 2's starting values from real data now, then bump
        # the generation counter so every Stage-2 widget below is fresh
        # (see the module docstring on why: a widget's own session_state
        # entry otherwise wins over a new `value=` on a later visit here).
        gen = st.session_state.brief_gen + 1
        st.session_state.brief_gen = gen

        st.session_state[f"field_brief_date_{gen}"] = _next_tuesday()

        for i, (node_id, choice) in enumerate(hyp_choices.items()):
            node = choice["node"]
            st.session_state[f"field_h{i}_short_name_{gen}"] = node["text"][:40]
            st.session_state[f"field_h{i}_statement_{gen}"] = node["text"]
            st.session_state[f"field_h{i}_owner_{gen}"] = choice["owner"]
            st.session_state[f"field_h{i}_wrong_if_{gen}"] = ""
            for j in range(weekly_brief.TESTS_PER_HYPOTHESIS):
                q = choice["questions"][j] if j < len(choice["questions"]) else ""
                st.session_state[f"field_h{i}_test{j}_q_{gen}"] = q
                st.session_state[f"field_h{i}_test{j}_who_{gen}"] = ""
                st.session_state[f"field_h{i}_test{j}_disprove_{gen}"] = ""

        queued = [p for p in scheduled_people if p["id"] in selected_people_ids][
            : weekly_brief.INTERVIEWS_QUEUED_ROWS
        ]
        for k in range(weekly_brief.INTERVIEWS_QUEUED_ROWS):
            if k < len(queued):
                p = queued[k]
                role = f", {p['role']}" if p["role"] else ""
                st.session_state[f"field_q{k}_name_role_{gen}"] = f"{p['name']}{role}"
                st.session_state[f"field_q{k}_segment_{gen}"] = p["relationship"] or ""
                st.session_state[f"field_q{k}_when_{gen}"] = p["interview_date"] or ""
            else:
                st.session_state[f"field_q{k}_name_role_{gen}"] = ""
                st.session_state[f"field_q{k}_segment_{gen}"] = ""
                st.session_state[f"field_q{k}_when_{gen}"] = ""

        st.session_state.brief_stage = "edit"
        st.session_state.pop("built_deck_bytes", None)
        st.rerun()


# =============================================================================
# STAGE 2 — EDIT, and STAGE 3 — FINALIZE (the Build button below)
# =============================================================================

else:
    gen = st.session_state.brief_gen

    if st.button("← Back to Choose"):
        st.session_state.brief_stage = "choose"
        st.rerun()
    st.caption("Going back and clicking Continue again re-derives the fields below from scratch.")

    st.divider()
    st.subheader("Cover")
    brief_date = st.date_input("Brief date", key=f"field_brief_date_{gen}")

    st.divider()
    st.subheader("Refined Problem Statement")
    beneficiary = st.text_area(
        "Beneficiary — who feels the pain (a specific role, not an organization)",
        key=f"field_problem_beneficiary_{gen}", height=70,
    )
    problem = st.text_area(
        "Problem — what they cannot do today, stated as pain, not a solution",
        key=f"field_problem_problem_{gen}", height=70,
    )
    mission_impact = st.text_area(
        "Mission impact — what it costs",
        key=f"field_problem_mission_impact_{gen}", height=70,
    )
    workaround = st.text_area(
        "Today's workaround — how they cope now, and where that breaks",
        key=f"field_problem_workaround_{gen}", height=70,
    )
    why_now = st.text_area(
        "Why now — what changed that makes this worth solving this year",
        key=f"field_problem_why_now_{gen}", height=70,
    )

    st.divider()
    st.subheader("What Changed")
    as_given = st.text_area(
        "As given — the sponsor's original framing",
        key=f"field_changed_as_given_{gen}", height=70,
    )
    as_refined = st.text_area(
        "As refined — your restatement after first contact",
        key=f"field_changed_as_refined_{gen}", height=70,
    )
    moved_us_1 = st.text_input("What moved us — fact 1", key=f"field_changed_moved1_{gen}")
    moved_us_2 = st.text_input("What moved us — fact 2 (what it ruled out)", key=f"field_changed_moved2_{gen}")

    st.divider()
    st.subheader("Hypotheses & Tests")
    hyp_fields = []
    for i in range(weekly_brief.HYPOTHESIS_SLOTS):
        st.markdown(f"**H{i + 1}**")
        short_name = st.text_input("Short name", key=f"field_h{i}_short_name_{gen}")
        statement = st.text_area(
            "Statement (from the hypothesis tree — editable)",
            key=f"field_h{i}_statement_{gen}", height=70,
        )
        owner = st.text_input("Owner", key=f"field_h{i}_owner_{gen}")
        wrong_if = st.text_area(
            "We would be wrong if...",
            key=f"field_h{i}_wrong_if_{gen}", height=60,
        )
        tests = []
        for j in range(weekly_brief.TESTS_PER_HYPOTHESIS):
            c1, c2, c3 = st.columns([2, 1, 2])
            with c1:
                q = st.text_input(f"Test {j + 1} question", key=f"field_h{i}_test{j}_q_{gen}")
            with c2:
                who = st.text_input("Who we ask", key=f"field_h{i}_test{j}_who_{gen}")
            with c3:
                disprove = st.text_input("What would prove us wrong", key=f"field_h{i}_test{j}_disprove_{gen}")
            tests.append({"question": q, "who": who, "disprove": disprove})
        hyp_fields.append({
            "short_name": short_name, "statement": statement, "owner": owner,
            "would_be_wrong_if": wrong_if, "tests": tests,
        })
        st.markdown("---")

    st.subheader("Discovery Plan")
    st.caption("Interviews queued")
    queued_fields = []
    for k in range(weekly_brief.INTERVIEWS_QUEUED_ROWS):
        c1, c2, c3 = st.columns(3)
        with c1:
            name_role = st.text_input(
                f"Name & role {k + 1}", key=f"field_q{k}_name_role_{gen}", label_visibility="collapsed",
                placeholder=f"Name & role {k + 1}",
            )
        with c2:
            segment = st.text_input(
                f"Segment {k + 1}", key=f"field_q{k}_segment_{gen}", label_visibility="collapsed",
                placeholder="Segment",
            )
        with c3:
            when = st.text_input(
                f"When {k + 1}", key=f"field_q{k}_when_{gen}", label_visibility="collapsed",
                placeholder="When",
            )
        queued_fields.append({"name_role": name_role, "segment": segment, "when": when})

    need_sponsor = st.text_input("What we need — from the sponsor", key=f"field_need_sponsor_{gen}")
    need_mentors = st.text_input("What we need — from the mentors", key=f"field_need_mentors_{gen}")
    need_instructor = st.text_input("What we need — from the instructor", key=f"field_need_instructor_{gen}")
    battle_meeting = st.text_input("Battle rhythm — team meeting (day/time)", key=f"field_battle_meeting_{gen}")
    battle_sponsor = st.text_input("Battle rhythm — sponsor touchpoint (cadence)", key=f"field_battle_sponsor_{gen}")
    battle_notes_owner = st.text_input(
        "Battle rhythm — who owns notes and the interview log", key=f"field_battle_notes_owner_{gen}"
    )

    st.divider()
    st.subheader("Build")
    st.caption(
        "Nothing is generated until you click below. This fills the template's "
        "slots with exactly what's in the fields above right now, and removes "
        "the how-to slide and both EXAMPLE slides."
    )

    if st.button("📥 Build the deck", type="primary"):
        fields = {
            "brief_date": _format_brief_date(brief_date) if brief_date else "",
            "problem": {
                "beneficiary": beneficiary, "problem": problem, "mission_impact": mission_impact,
                "workaround": workaround, "why_now": why_now,
            },
            "what_changed": {
                "as_given": as_given, "as_refined": as_refined,
                "moved_us_1": moved_us_1, "moved_us_2": moved_us_2,
            },
            "hypotheses": hyp_fields,
            "discovery": {
                "interviews_queued": queued_fields,
                "need_sponsor": need_sponsor, "need_mentors": need_mentors, "need_instructor": need_instructor,
                "battle_meeting": battle_meeting, "battle_sponsor": battle_sponsor,
                "battle_notes_owner": battle_notes_owner,
            },
        }
        with st.spinner("Building the deck..."):
            st.session_state.built_deck_bytes = weekly_brief.build_deck(fields)
        st.success("Deck built — download it below.")

    if st.session_state.get("built_deck_bytes"):
        st.download_button(
            "Download Weekly_Brief.pptx",
            data=st.session_state.built_deck_bytes,
            file_name=f"Weekly_Brief_{datetime.date.today().isoformat()}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
