"""
pages/2_Hypotheses.py — Hypothesis tree: build and manage hypotheses as a
real branching tree. Each node can have children, evolve over time (via
edit), and be set dormant without ever being deleted. Hypothesis
SELECTION for processing an interview comes in a later step — this page
is only about building/maintaining the tree itself.

Two view modes: "List (edit)" (the original tree, with add/edit/toggle
controls) and "Visual tree" (read-only, a real clickable expand/collapse
diagram — see build_visual_tree_html). The visual tree is plain HTML
(nested <details>/<summary>, native browser disclosure — no JS, no new
dependency, works fully offline) rendered via
streamlit.components.v1.html; editing still only happens in List view.
"""

import html as html_lib

import streamlit as st
import streamlit.components.v1 as components

import storage

st.set_page_config(page_title="H4D Interview App — Hypotheses", page_icon="🧩")

st.title("Hypotheses")
st.caption(
    "Build and manage the hypothesis tree. Dormant nodes are set aside, not "
    "tested by default, and can be revived to active at any time — nothing "
    "here is ever deleted."
)


def _ascii_lines(nodes: list[dict], prefix: str) -> list[str]:
    lines = []
    for i, node in enumerate(nodes):
        is_last = i == len(nodes) - 1
        connector = "└─ " if is_last else "├─ "
        suffix = " (dormant)" if node["state"] == "dormant" else ""
        lines.append(f"{prefix}{connector}{node['label']}{suffix}")
        child_prefix = prefix + ("    " if is_last else "│   ")
        lines.extend(_ascii_lines(node["children"], child_prefix))
    return lines


def build_ascii_summary(tree: list[dict]) -> str:
    """A compact plain-text lineage overview, e.g.:
    1
    ├─ 1a
    └─ 1b (dormant)
    2
    └─ 2a
    3 (dormant)
    """
    lines = []
    for root in tree:
        suffix = " (dormant)" if root["state"] == "dormant" else ""
        lines.append(f"{root['label']}{suffix}")
        lines.extend(_ascii_lines(root["children"], ""))
    return "\n".join(lines) if lines else "(no hypotheses yet)"


def render_node(node: dict, depth: int) -> None:
    is_dormant = node["state"] == "dormant"
    indent = "&nbsp;" * 4 * depth

    if is_dormant:
        st.caption(f"{indent}**{node['label']}** _(dormant)_ — {node['text']}", unsafe_allow_html=True)
    else:
        st.markdown(f"{indent}**{node['label']}** — {node['text']}", unsafe_allow_html=True)

    b1, b2, b3, _ = st.columns([1, 1, 1, 3])
    with b1:
        add_child_clicked = st.button("➕ Add child", key=f"add_child_btn_{node['id']}")
    with b2:
        edit_clicked = st.button("✏️ Edit", key=f"edit_btn_{node['id']}")
    with b3:
        toggle_label = "Set dormant" if not is_dormant else "Set active"
        toggle_clicked = st.button(toggle_label, key=f"toggle_btn_{node['id']}")

    if toggle_clicked:
        storage.set_hypothesis_state(node["id"], "dormant" if not is_dormant else "active")
        st.rerun()

    if add_child_clicked:
        st.session_state[f"show_add_child_{node['id']}"] = True
    if edit_clicked:
        st.session_state[f"show_edit_{node['id']}"] = True

    if st.session_state.get(f"show_add_child_{node['id']}"):
        with st.form(f"add_child_form_{node['id']}"):
            child_text = st.text_area("New child hypothesis text", key=f"child_text_{node['id']}")
            submitted = st.form_submit_button("Save child")
        if submitted:
            if child_text.strip():
                storage.add_hypothesis(node["id"], child_text.strip())
                st.session_state[f"show_add_child_{node['id']}"] = False
                st.rerun()
            else:
                st.warning("Enter some text for the new child hypothesis.")

    if st.session_state.get(f"show_edit_{node['id']}"):
        with st.form(f"edit_form_{node['id']}"):
            new_text = st.text_area("Edit text", value=node["text"], key=f"edit_text_{node['id']}")
            submitted_edit = st.form_submit_button("Save edit")
        if submitted_edit:
            if new_text.strip():
                storage.edit_hypothesis_text(node["id"], new_text.strip())
                st.session_state[f"show_edit_{node['id']}"] = False
                st.rerun()
            else:
                st.warning("Hypothesis text can't be empty.")

    for child in node["children"]:
        render_node(child, depth + 1)


def _count_nodes(nodes: list[dict]) -> int:
    return sum(1 + _count_nodes(n["children"]) for n in nodes)


def _visual_tree_node_html(node: dict) -> str:
    """One node's HTML: a <details>/<summary> if it has children (so it's
    a real click-to-expand/collapse toggle), or a plain row if it's a
    leaf (nothing to expand). Text is HTML-escaped since a hypothesis's
    text is free-form user input being embedded directly into markup."""
    is_dormant = node["state"] == "dormant"
    state_class = "dormant" if is_dormant else "active"
    label = html_lib.escape(node["label"])
    text = html_lib.escape(node["text"])
    badge = f'<span class="badge {state_class}">{state_class}</span>'
    row = f'<span class="label">{label}</span> {badge} {text}'

    children = node.get("children") or []
    if children:
        children_html = "".join(_visual_tree_node_html(c) for c in children)
        return (
            f'<details class="node {state_class}" open>'
            f"<summary>{row}</summary>"
            f'<div class="children">{children_html}</div>'
            f"</details>"
        )
    return f'<div class="node leaf {state_class}">{row}</div>'


def build_visual_tree_html(tree: list[dict]) -> str:
    """A self-contained HTML page: a real clickable expand/collapse tree
    diagram, using only native <details>/<summary> disclosure (no JS, no
    new dependency, works fully offline) — rendered via
    streamlit.components.v1.html, which sandboxes it in an iframe."""
    if not tree:
        body = '<p class="empty">No hypotheses yet — add one in List view.</p>'
    else:
        body = "".join(_visual_tree_node_html(root) for root in tree)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
        body {{ font-family: -apple-system, "Segoe UI", sans-serif; font-size: 14px;
                margin: 0; padding: 4px 8px; color: #1a1a1a; background: transparent; }}
        details.node {{ margin: 4px 0; }}
        details.node > summary {{ cursor: pointer; padding: 6px 8px; border-radius: 6px;
                background: #f2f2f5; list-style: none; }}
        details.node > summary::-webkit-details-marker {{ display: none; }}
        details.node > summary::before {{ content: "▸  "; color: #888; }}
        details.node[open] > summary::before {{ content: "▾  "; color: #888; }}
        .children {{ margin-left: 20px; border-left: 2px solid #e2e2e6; padding-left: 12px; }}
        .node.leaf {{ padding: 6px 8px; margin: 4px 0; border-radius: 6px; background: #f2f2f5; }}
        .label {{ font-weight: 700; }}
        .badge {{ font-size: 11px; padding: 1px 7px; border-radius: 10px; margin-right: 2px; }}
        .badge.active {{ background: #d7f3df; color: #1a7f37; }}
        .badge.dormant {{ background: #eaeaea; color: #777; }}
        .node.dormant {{ opacity: 0.7; }}
        .empty {{ color: #888; font-style: italic; }}
        </style></head><body>{body}</body></html>"""


tree = storage.get_hypothesis_tree()

view_mode = st.radio(
    "View as",
    ["List (edit)", "Visual tree (click to expand/collapse)"],
    horizontal=True,
)

if view_mode.startswith("Visual"):
    st.caption("Read-only — switch to List view to add, edit, or toggle active/dormant.")
    node_count = _count_nodes(tree)
    height = min(max(160, 46 * max(node_count, 1) + 80), 700)
    components.html(build_visual_tree_html(tree), height=height, scrolling=True)
else:
    st.subheader("Lineage overview")
    st.code(build_ascii_summary(tree), language=None)

    st.divider()

    with st.expander("➕ Add a new family"):
        with st.form("add_family_form"):
            new_family_text = st.text_area("New hypothesis text", key="new_family_text")
            submitted_family = st.form_submit_button("Add family")
        if submitted_family:
            if new_family_text.strip():
                storage.add_hypothesis(None, new_family_text.strip())
                st.rerun()
            else:
                st.warning("Enter some text for the new family hypothesis.")

    st.divider()
    st.subheader("Tree")

    if not tree:
        st.write("No hypotheses yet — add a family above to get started.")
    else:
        for root in tree:
            render_node(root, depth=0)
            st.markdown("---")
