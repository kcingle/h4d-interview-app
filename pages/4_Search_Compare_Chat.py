"""
pages/4_Search_Compare_Chat.py — Four tabs, combining what used to be two
separate pages (Search & Compare, Chat).

"Search" and "Compare" retrieve and organize what interviews' digests
already say — quote-anchored, no AI call anywhere in either tab, and no
synthesized "here's the interesting contrast" narrative. That's a hard
rule: models invent plausible-looking cross-interview patterns that
aren't real, which is exactly the fabrication risk this project exists
to prevent.

"Corpus Chat" is a different kind of feature: a real conversation over
the whole corpus (see ai.run_chat) — every message sends the team's full
hypothesis tree, people roster, document list, and every interview's raw
transcript + Additional Notes + full analysis (not just the digest) as
context (see ai.build_corpus_context) — cached after the first turn each
session, so later turns are cheap; only the first message and an
explicit refresh pay full price. Answers should cite which interview a
finding came from — the system prompt (ai.CHAT_SYSTEM_INSTRUCTIONS)
tells the model to say so plainly when something isn't in the material,
rather than guess.

"Background & Definitions" (see ai.define_terms) is yet another kind of
assistant: it explains words/acronyms/concepts, and — unlike everywhere
else in this app — is explicitly allowed to use general domain knowledge,
not just the corpus. Anything it defines can be saved to the Dictionary
(pages/9_Dictionary.py) with one click; nothing is saved automatically.

Search/Compare and the two Chat tabs share this page only because the
sidebar was getting crowded — they don't share state, except that
Corpus Chat and Background & Definitions still share one cached
`chat_corpus_context` between themselves (see _get_or_build_context),
same as when Chat was its own page.
"""

import streamlit as st

import ai
import auth
import env_store
import storage

st.set_page_config(page_title="H4D Interview App — Search, Compare & Chat", page_icon="🔍")
auth.require_login()

st.title("Search, Compare & Chat")

api_key = env_store.load_api_key()

search_tab, compare_tab, tab_chat, tab_define = st.tabs(
    ["🔍 Search", "⚖️ Compare", "💬 Corpus Chat", "🔤 Background & Definitions"]
)


def _who(person: dict | None) -> str:
    if not person:
        return "Interviewee not recorded"
    return f"{person['name']} ({person['role']})" if person.get("role") else person["name"]


def _build_context() -> str:
    hypotheses_tree = storage.get_hypothesis_tree()
    people = storage.get_people()
    documents = storage.get_documents()
    interviews = []
    for interview in storage.get_interviews():
        person = storage.get_person_for_interview(interview["id"])
        runs = storage.get_runs_for_interview(interview["id"])
        interviews.append({**interview, "person": person, "runs": runs})
    return ai.build_corpus_context(hypotheses_tree, interviews, people, documents)


def _get_or_build_context() -> str:
    """Shared by both Chat tabs, so Background & Definitions doesn't
    force a separate corpus read if Corpus Chat has already built one
    this session."""
    if "chat_corpus_context" not in st.session_state:
        with st.spinner("Reading the corpus..."):
            st.session_state.chat_corpus_context = _build_context()
    return st.session_state.chat_corpus_context


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

with search_tab:
    st.caption(
        "Search work over each interview's digest — never full "
        "transcripts — and only ever show you real, verbatim quotes. "
        "Nothing on this tab is AI-generated; it's retrieval and layout only."
    )
    st.subheader("Search across every interview")

    all_tags = storage.get_all_topic_tags()
    col1, col2 = st.columns([2, 1])
    with col1:
        query = st.text_input("Keyword or phrase", key="search_query")
    with col2:
        tag_pick = st.selectbox(
            "...or pick a topic tag", [""] + all_tags, key="search_tag_pick",
            help="Only tags already stored in a digest — see the topics field.",
        )

    effective_query = tag_pick or query

    if not effective_query.strip():
        st.info("Enter a keyword, or pick a topic tag, to search.")
    else:
        results = storage.search_digests(effective_query)
        if not results:
            st.warning(f"Nothing found for “{effective_query}”.")
        else:
            st.success(f"{len(results)} interview(s) mention “{effective_query}”.")
            for r in results:
                st.markdown(f"### {r['interview_title']}")
                st.caption(_who(r["interviewee"]))
                for p in r["passages"]:
                    extra = f" — {p['status']}" if p.get("status") else ""
                    st.markdown(f"**{p['kind']}{extra}:** {p['label']}")
                    st.markdown(f"> {p['quote']}")
                st.page_link("pages/1_Interviews.py", label="Open in Interviews →")
                st.divider()

# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

with compare_tab:
    st.caption(
        "Compare work over each interview's digest — never full "
        "transcripts — and only ever show you real, verbatim quotes. "
        "Nothing on this tab is AI-generated; it's retrieval and layout only."
    )
    st.subheader("Compare interviews side by side")

    interviews = storage.get_interviews()
    if not interviews:
        st.write("No interviews saved yet.")
    else:
        labels = {iv["id"]: f"{iv['title']} — {iv['created_at'][:10]}" for iv in interviews}
        selected_ids = st.multiselect(
            "Select 2 or more interviews",
            options=[iv["id"] for iv in interviews],
            format_func=lambda i: labels[i],
            key="compare_interviews",
        )

        dimension_kind = st.radio(
            "Compare on", ["Hypothesis", "Topic tag"], horizontal=True, key="compare_dimension_kind"
        )

        dimension_value = None
        if dimension_kind == "Hypothesis":
            tree = storage.get_hypothesis_tree()

            def _flatten(nodes, depth=0):
                flat = []
                for node in nodes:
                    flat.append((depth, node))
                    flat.extend(_flatten(node["children"], depth + 1))
                return flat

            flat_hyps = _flatten(tree)
            if not flat_hyps:
                st.write("No hypotheses yet — add some on the Hypotheses page.")
            else:
                hyp_labels = [f"{'    ' * d}{n['label']} — {n['text'][:60]}" for d, n in flat_hyps]
                hyp_idx = st.selectbox(
                    "Which hypothesis", options=range(len(flat_hyps)),
                    format_func=lambda i: hyp_labels[i], key="compare_hyp_pick",
                )
                dimension_value = flat_hyps[hyp_idx][1]["text"]
        else:
            all_tags_cmp = storage.get_all_topic_tags()
            if not all_tags_cmp:
                st.write("No topic tags recorded yet.")
            else:
                dimension_value = st.selectbox("Which topic tag", all_tags_cmp, key="compare_tag_pick")

        if len(selected_ids) < 2:
            st.info("Select at least 2 interviews to compare.")
        elif dimension_value is None:
            pass  # already showed a message above (no hypotheses/tags yet)
        else:
            if dimension_kind == "Hypothesis":
                comparison = storage.compare_interviews_on_hypothesis(selected_ids, dimension_value)
            else:
                comparison = storage.compare_interviews_on_topic(selected_ids, dimension_value)

            st.divider()
            cols = st.columns(len(comparison))
            for col, entry in zip(cols, comparison):
                with col:
                    st.markdown(f"**{entry['interview_title']}**")
                    st.caption(_who(entry["interviewee"]))
                    st.markdown("---")

                    if dimension_kind == "Hypothesis":
                        if not entry["tested"]:
                            st.write("_Did not test this hypothesis._")
                        elif not entry["quotes"]:
                            st.write(f"**{entry['status']}** _(no verified quote)_")
                        else:
                            st.write(f"**{entry['status']}**")
                            for q in entry["quotes"]:
                                st.markdown(f"> {q}")
                    else:
                        if not entry["passages"]:
                            st.write("_Nothing on this topic._")
                        else:
                            for p in entry["passages"]:
                                st.markdown(f"**{p['kind']}:** {p['label']}")
                                st.markdown(f"> {p['quote']}")

# ---------------------------------------------------------------------------
# Corpus Chat
# ---------------------------------------------------------------------------

with tab_chat:
    if not api_key:
        st.warning("No Anthropic API key set yet. Enter one on the **Settings** page first.")

    st.caption(
        "Ask about anything logged across the app — hypotheses, interviews, "
        "people, findings. Answers should cite which interview they came from."
    )

    interview_count = len(storage.get_interviews())

    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(
            f"Context currently covers {interview_count} interview(s) as of "
            "the last refresh below."
        )
    with col2:
        refresh_clicked = st.button("🔄 Refresh context")

    # Built once per session (or on demand) rather than on every rerun —
    # it reads the whole corpus, so there's no reason to redo that work
    # on every chat_input keystroke/rerun. Refreshing also clears
    # history: an old reply may cite context that's since changed (a
    # rerun, an edited hypothesis), so starting the conversation over
    # avoids mixing stale and fresh context in one exchange.
    if "chat_corpus_context" not in st.session_state or refresh_clicked:
        with st.spinner("Reading the corpus..."):
            st.session_state.chat_corpus_context = _build_context()
        st.session_state.chat_history = []
        if refresh_clicked:
            st.success("Context refreshed — new interviews or edits are now included.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        if msg.get("role") not in ("user", "assistant"):
            continue
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_message = st.chat_input(
        "Ask about the interviews, hypotheses, or people...",
        disabled=not api_key, key="corpus_chat_input",
    )
    if user_message:
        with st.chat_message("user"):
            st.markdown(user_message)
        try:
            with st.spinner("Thinking..."):
                result = ai.run_chat(
                    st.session_state.chat_history,
                    user_message,
                    api_key,
                    st.session_state.chat_corpus_context,
                )
            st.session_state.chat_history = result["history"]
            with st.chat_message("assistant"):
                st.markdown(result["reply"])
        except ai.AIError as e:
            st.error(str(e))

    if st.session_state.chat_history:
        if st.button("🗑️ Clear conversation"):
            st.session_state.chat_history = []
            st.rerun()

# ---------------------------------------------------------------------------
# Background & Definitions
# ---------------------------------------------------------------------------

with tab_define:
    if not api_key:
        st.warning("No Anthropic API key set yet. Enter one on the **Settings** page first.")

    st.caption(
        "Ask what a word, acronym, or concept means. Unlike the corpus "
        "chat, this can draw on general knowledge — not just the "
        "interviews — but will say how a term was used in an interview "
        "if it appears there. Nothing is saved until you click "
        "\"Add to dictionary.\""
    )

    define_query = st.text_input(
        "Term, acronym, or question",
        key="define_query",
        placeholder='e.g. "What does OCA stand for?" or "What is a Mom Test question?"',
    )
    explain_clicked = st.button(
        "Explain", disabled=not api_key or not define_query.strip(), key="explain_btn"
    )

    if explain_clicked:
        try:
            with st.spinner("Looking it up..."):
                context = _get_or_build_context()
                st.session_state.define_results = ai.define_terms(define_query, context, api_key)
        except ai.AIError as e:
            st.error(str(e))

    define_results = st.session_state.get("define_results")
    if define_results is not None:
        if not define_results:
            st.info("No terms identified in that question.")
        else:
            for i, entry in enumerate(define_results):
                with st.container(border=True):
                    header = f"**{entry.get('term', '')}**"
                    if entry.get("is_acronym") and entry.get("expansion"):
                        header += f" — {entry['expansion']}"
                    st.markdown(header)
                    st.write(entry.get("definition", ""))
                    if st.button("➕ Add to dictionary", key=f"add_dict_{i}"):
                        storage.add_dictionary_entry(
                            entry.get("term", ""),
                            entry.get("definition", ""),
                            is_acronym=bool(entry.get("is_acronym")),
                            expansion=entry.get("expansion", "") or "",
                        )
                        st.success(f"Added \"{entry.get('term', '')}\" to the Dictionary.")
