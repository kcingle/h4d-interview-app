"""
pages/4_Chat.py — Chat with the whole interview corpus. Every message
sends the team's full hypothesis tree, people roster, document list, and
every interview's raw transcript + Additional Notes + full analysis (not
just the digest) as context (see ai.build_corpus_context) — cached after
the first turn each session, so later turns in the same conversation are
cheap; only the first message and an explicit refresh pay full price.

Answers should cite which interview a finding came from — the system
prompt (ai.CHAT_SYSTEM_INSTRUCTIONS) tells the model to say so plainly
when something isn't in the material, rather than guess.
"""

import streamlit as st

import ai
import env_store
import storage

st.set_page_config(page_title="H4D Interview App — Chat", page_icon="💬")

st.title("Chat")
st.caption(
    "Ask about anything logged across the app — hypotheses, interviews, "
    "people, findings. Answers should cite which interview they came from."
)

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


interview_count = len(storage.get_interviews())

col1, col2 = st.columns([3, 1])
with col1:
    st.caption(
        f"Context currently covers {interview_count} interview(s) as of the "
        "last refresh below."
    )
with col2:
    refresh_clicked = st.button("🔄 Refresh context")

# Built once per session (or on demand) rather than on every rerun — it
# reads the whole corpus, so there's no reason to redo that work on every
# chat_input keystroke/rerun. Refreshing also clears history: an old
# reply may cite context that's since changed (a rerun, an edited
# hypothesis), so starting the conversation over avoids mixing stale and
# fresh context in one exchange.
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
    "Ask about the interviews, hypotheses, or people...", disabled=not api_key
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
