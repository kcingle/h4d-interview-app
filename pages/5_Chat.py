"""
pages/5_Chat.py — Two modes, as tabs. "Corpus Chat" talks about the
interview corpus itself (see ai.run_chat) — every message sends the
team's full hypothesis tree, people roster, document list, and every
interview's raw transcript + Additional Notes + full analysis (not just
the digest) as context (see ai.build_corpus_context) — cached after the
first turn each session, so later turns are cheap; only the first
message and an explicit refresh pay full price. Answers should cite
which interview a finding came from — the system prompt
(ai.CHAT_SYSTEM_INSTRUCTIONS) tells the model to say so plainly when
something isn't in the material, rather than guess.

"Background & Definitions" (see ai.define_terms) is a DIFFERENT kind of
assistant: it explains words/acronyms/concepts, and — unlike everywhere
else in this app — is explicitly allowed to use general domain knowledge,
not just the corpus. Anything it defines can be saved to the Dictionary
(pages/9_Dictionary.py) with one click; nothing is saved automatically.
"""

import streamlit as st

import ai
import auth
import env_store
import storage

st.set_page_config(page_title="H4D Interview App — Chat", page_icon="💬")
auth.require_login()

st.title("Chat")

api_key = env_store.load_api_key()
if not api_key:
    st.warning("No Anthropic API key set yet. Enter one on the **Settings** page first.")


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
    """Shared by both tabs, so Background & Definitions doesn't force a
    separate corpus read if Corpus Chat has already built one this
    session."""
    if "chat_corpus_context" not in st.session_state:
        with st.spinner("Reading the corpus..."):
            st.session_state.chat_corpus_context = _build_context()
    return st.session_state.chat_corpus_context


tab_chat, tab_define = st.tabs(["💬 Corpus Chat", "🔤 Background & Definitions"])

with tab_chat:
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

with tab_define:
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
