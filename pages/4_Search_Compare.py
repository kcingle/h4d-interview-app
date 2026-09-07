"""
pages/4_Search_Compare.py — Cross-interview keyword/tag search, and
side-by-side compare of 2+ interviews on one dimension (a hypothesis or
a topic tag). Both retrieve and organize what interviews' digests already
say — quote-anchored, no AI call anywhere on this page, and no synthesized
"here's the interesting contrast" narrative. That's a hard rule: models
invent plausible-looking cross-interview patterns that aren't real, which
is exactly the fabrication risk this project exists to prevent.
"""

import streamlit as st

import auth
import storage

st.set_page_config(page_title="H4D Interview App — Search & Compare", page_icon="🔍")
auth.require_login()

st.title("Search & Compare")
st.caption(
    "Search and compare work over each interview's digest — never full "
    "transcripts — and only ever show you real, verbatim quotes. Nothing "
    "on this page is AI-generated; it's retrieval and layout only."
)

search_tab, compare_tab = st.tabs(["🔍 Search", "⚖️ Compare"])


def _who(person: dict | None) -> str:
    if not person:
        return "Interviewee not recorded"
    return f"{person['name']} ({person['role']})" if person.get("role") else person["name"]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

with search_tab:
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
