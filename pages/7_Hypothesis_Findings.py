"""
pages/7_Hypothesis_Findings.py — Roll a single hypothesis up across every
interview that tested it, using the enriched digests (never full
transcripts). Renamed from "Hypothesis Status" for clarity, since it sat
right next to "Hypotheses" (the tree management page) in the sidebar
with an easily-confused name — this page is specifically the evidence
FOUND for a hypothesis, not where you manage the tree itself. Pure
retrieval and organization of what interviews already said —
quote-anchored, never a synthesized "what this all means" narrative.
Any aggregate shown here (counts, lists) is mechanical.

Matching a run to a tree hypothesis is exact-text (case/whitespace
normalized) against a run's tested hypotheses — see
storage._normalize_hypothesis_text for why this isn't fuzzy.
"""

import streamlit as st

import auth
import storage

st.set_page_config(page_title="H4D Interview App — Hypothesis Findings", page_icon="📊")
auth.require_login()

st.title("Hypothesis Findings")
st.caption(
    "Select a hypothesis to see every interview that tested it — verdicts "
    "and their verbatim evidence, organized from the interviews' own "
    "digests. This page never draws a conclusion for you; it only shows "
    "what was said and by whom."
)

tree = storage.get_hypothesis_tree()

if not tree:
    st.write("No hypotheses yet — add some on the **Hypotheses** page first.")
    st.stop()


def _flatten(nodes: list[dict], depth: int = 0) -> list[tuple[int, dict]]:
    """Flatten the nested tree into a depth-annotated list, preserving
    the same top-to-bottom, label-sorted order as the tree itself."""
    flat = []
    for node in nodes:
        flat.append((depth, node))
        flat.extend(_flatten(node["children"], depth + 1))
    return flat


def _find_root(nodes: list[dict], target_id: int) -> dict | None:
    """Find which root subtree (of the top-level list) contains target_id."""
    def contains(node: dict) -> bool:
        if node["id"] == target_id:
            return True
        return any(contains(child) for child in node["children"])

    for root in nodes:
        if contains(root):
            return root
    return None


flat_all = _flatten(tree)
labels = [f"{'    ' * depth}{node['label']} — {node['text'][:70]}" for depth, node in flat_all]

selected_idx = st.selectbox(
    "Select a hypothesis", options=range(len(flat_all)), format_func=lambda i: labels[i]
)
selected_depth, selected_node = flat_all[selected_idx]

st.subheader(f"Hypothesis {selected_node['label']}")
st.info(selected_node["text"])
if selected_node["state"] == "dormant":
    st.caption("_(dormant)_")

rollup = storage.get_hypothesis_status_rollup(selected_node["text"])
counts = rollup["counts"]
total = sum(counts.values())

st.divider()
st.subheader("Rollup verdict")
c1, c2, c3 = st.columns(3)
c1.metric("Validated", counts.get("Validated", 0))
c2.metric("Invalidated", counts.get("Invalidated", 0))
c3.metric("Untested", counts.get("Untested", 0))

if total == 0:
    st.write(
        "No interview has tested this exact hypothesis text yet. "
        "(Matching is exact-text — see the note at the bottom of this page.)"
    )
else:
    st.divider()
    st.subheader("Per-interview evidence (quote-backed)")
    if not rollup["quote_backed"]:
        st.write("No verdict for this hypothesis has a verified quote yet.")
    else:
        for entry in rollup["quote_backed"]:
            who = entry["interviewee"]
            who_label = (
                f"{who['name']} ({who['role']})" if who and who.get("role")
                else (who["name"] if who else "Interviewee not recorded")
            )
            st.markdown(f"**{entry['status']}** — {entry['interview_title']} — {who_label}")
            for q in entry["quotes"]:
                st.markdown(f"> {q}")
            st.page_link("pages/1_Interviews.py", label="Open in Interviews →")
            st.markdown("---")

    if rollup["unsupported"]:
        st.divider()
        st.subheader("⚠️ Unsupported / inferred verdicts")
        st.caption(
            "These interviews reached a verdict on this hypothesis, but no "
            "quote from the notes verified it — never treat these as "
            "quote-backed evidence."
        )
        for entry in rollup["unsupported"]:
            who = entry["interviewee"]
            who_label = (
                f"{who['name']} ({who['role']})" if who and who.get("role")
                else (who["name"] if who else "Interviewee not recorded")
            )
            st.markdown(
                f"**{entry['status']}** (unsupported) — {entry['interview_title']} — {who_label}"
            )
            st.caption(entry["reason"])
            st.page_link("pages/1_Interviews.py", label="Open in Interviews →")
            st.markdown("---")

st.divider()
st.subheader("Lineage — how this idea evolved")
st.caption("Every version in this hypothesis's family, with its own mechanical rollup.")

root = _find_root(tree, selected_node["id"])
family = _flatten([root]) if root else []

for depth, node in family:
    node_rollup = storage.get_hypothesis_status_rollup(node["text"])
    node_counts = node_rollup["counts"]
    marker = "➤ " if node["id"] == selected_node["id"] else "　"
    state_note = " (dormant)" if node["state"] == "dormant" else ""
    st.markdown(
        f"{'&nbsp;&nbsp;&nbsp;&nbsp;' * depth}{marker}**{node['label']}**{state_note} — "
        f"{node['text'][:80]} — "
        f"✅ {node_counts.get('Validated', 0)} · "
        f"❌ {node_counts.get('Invalidated', 0)} · "
        f"❔ {node_counts.get('Untested', 0)}",
        unsafe_allow_html=True,
    )

st.divider()
st.caption(
    "Matching note: an interview counts toward a hypothesis only if it was "
    "run against that hypothesis's EXACT text — checked on the Process "
    "Interview or Interviews page's hypothesis picker. A run tested against "
    "several hypotheses at once still counts toward each one individually; "
    "a differently-worded (even if topically related) hypothesis won't."
)
