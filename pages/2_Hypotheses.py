"""
pages/2_Hypotheses.py — Hypothesis tree: build and manage hypotheses as a
real branching tree. Each node can have children, evolve over time (via
edit), and be set dormant without ever being deleted. Hypothesis
SELECTION for processing an interview comes in a later step — this page
is only about building/maintaining the tree itself.

Two view modes: "List (edit)" (the original tree, with add/edit/toggle
controls) and "Visual tree" (read-only, a real branching node/edge
diagram — see build_zoomable_tree_html) — drag to pan, scroll or the
+/−/⤾ buttons to zoom, each node showing how many times it's been
tested and validated (storage.get_hypothesis_test_counts), live off the
same tree/digest data every other page reads (nothing to refresh:
processing a new interview updates it on the next rerun). It's plain
SVG plus a small hand-rolled pointer/wheel-event script for the pan/
zoom — no new dependency (no JS library, no graphviz) — rendered via
streamlit.components.v1.html; editing still only happens in List view.

Hypotheses are never auto-added — the "Suggest hypotheses" section below
is the one place the AI proposes candidates (grounded in everything
logged in the corpus so far, see ai.suggest_hypotheses), and even then
nothing reaches storage.add_hypothesis until a person checks the ones
they want and clicks "Add approved".
"""

import html as html_lib
import textwrap

import streamlit as st
import streamlit.components.v1 as components

import ai
import auth
import env_store
import storage

st.set_page_config(page_title="H4D Interview App — Hypotheses", page_icon="🧩")
auth.require_login()

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

    b1, b2, b3, b4 = st.columns([1, 1, 1, 1])
    with b1:
        add_child_clicked = st.button("➕ Add child", key=f"add_child_btn_{node['id']}")
    with b2:
        edit_clicked = st.button("✏️ Edit", key=f"edit_btn_{node['id']}")
    with b3:
        toggle_label = "Set dormant" if not is_dormant else "Set active"
        toggle_clicked = st.button(toggle_label, key=f"toggle_btn_{node['id']}")
    with b4:
        delete_clicked = st.button("🗑️ Delete", key=f"delete_btn_{node['id']}")

    if toggle_clicked:
        storage.set_hypothesis_state(node["id"], "dormant" if not is_dormant else "active")
        st.rerun()

    if add_child_clicked:
        st.session_state[f"show_add_child_{node['id']}"] = True
    if edit_clicked:
        st.session_state[f"show_edit_{node['id']}"] = True
    if delete_clicked:
        st.session_state[f"show_delete_confirm_{node['id']}"] = True

    if st.session_state.get(f"show_add_child_{node['id']}"):
        with st.form(f"add_child_form_{node['id']}"):
            child_text = st.text_area("New child hypothesis text", key=f"child_text_{node['id']}")
            fc1, fc2 = st.columns(2)
            with fc1:
                submitted = st.form_submit_button("Save child")
            with fc2:
                cancelled_add = st.form_submit_button("Cancel")
        if submitted:
            if child_text.strip():
                storage.add_hypothesis(node["id"], child_text.strip())
                st.session_state[f"show_add_child_{node['id']}"] = False
                # Clear the text box's own stored value too — a widget's
                # session_state entry otherwise persists even while the
                # form is hidden, so reopening "Add child" later would
                # show this leftover text instead of a clean box.
                st.session_state.pop(f"child_text_{node['id']}", None)
                st.rerun()
            else:
                st.warning("Enter some text for the new child hypothesis.")
        if cancelled_add:
            st.session_state[f"show_add_child_{node['id']}"] = False
            st.session_state.pop(f"child_text_{node['id']}", None)
            st.rerun()

    if st.session_state.get(f"show_edit_{node['id']}"):
        with st.form(f"edit_form_{node['id']}"):
            new_text = st.text_area("Edit text", value=node["text"], key=f"edit_text_{node['id']}")
            fe1, fe2 = st.columns(2)
            with fe1:
                submitted_edit = st.form_submit_button("Save edit")
            with fe2:
                cancelled_edit = st.form_submit_button("Cancel")
        if submitted_edit:
            if new_text.strip():
                storage.edit_hypothesis_text(node["id"], new_text.strip())
                st.session_state[f"show_edit_{node['id']}"] = False
                # Clear the text box's own stored value — next time Edit
                # is reopened (for this node or, since the key is
                # per-node, any node), it should fall back to that
                # node's own current text via `value=node["text"]`
                # rather than whatever was last typed here.
                st.session_state.pop(f"edit_text_{node['id']}", None)
                st.rerun()
            else:
                st.warning("Hypothesis text can't be empty.")
        if cancelled_edit:
            st.session_state[f"show_edit_{node['id']}"] = False
            st.session_state.pop(f"edit_text_{node['id']}", None)
            st.rerun()

    if st.session_state.get(f"show_delete_confirm_{node['id']}"):
        if node["children"]:
            st.warning(
                "This hypothesis still has sub-hypotheses under it — delete "
                "those first."
            )
            if st.button("OK", key=f"delete_blocked_ok_{node['id']}"):
                st.session_state[f"show_delete_confirm_{node['id']}"] = False
                st.rerun()
        else:
            st.error(f'This cannot be undone. Delete "{node["label"]}" permanently?')
            dc1, dc2 = st.columns(2)
            with dc1:
                confirm_delete = st.button(
                    "Yes, permanently delete", key=f"confirm_delete_btn_{node['id']}"
                )
            with dc2:
                cancel_delete = st.button("Cancel", key=f"cancel_delete_btn_{node['id']}")
            if confirm_delete:
                try:
                    storage.delete_hypothesis(node["id"])
                    st.session_state.pop(f"show_delete_confirm_{node['id']}", None)
                    st.success("Deleted.")
                    st.rerun()
                except storage.HypothesisError as e:
                    st.error(str(e))
            if cancel_delete:
                st.session_state.pop(f"show_delete_confirm_{node['id']}", None)
                st.rerun()

    for child in node["children"]:
        render_node(child, depth + 1)


def _label_to_id(nodes: list[dict]) -> dict[str, int]:
    """Flatten the tree into {label: id}, for resolving a suggestion's
    suggested_parent_label back to a real parent_id."""
    mapping = {}
    for node in nodes:
        mapping[node["label"]] = node["id"]
        mapping.update(_label_to_id(node["children"]))
    return mapping


def _build_corpus_context_for_suggestions() -> str:
    """Same assembly Chat uses (ai.build_corpus_context) — the full
    hypothesis tree, people roster, document list, and every interview's
    raw transcript + Additional Notes + complete analysis — so a
    suggestion is grounded in the same material a person would see."""
    hypotheses_tree = storage.get_hypothesis_tree()
    people = storage.get_people()
    documents = storage.get_documents()
    interviews = []
    for interview in storage.get_interviews():
        person = storage.get_person_for_interview(interview["id"])
        runs = storage.get_runs_for_interview(interview["id"])
        interviews.append({**interview, "person": person, "runs": runs})
    return ai.build_corpus_context(hypotheses_tree, interviews, people, documents)


_NODE_W = 210
_NODE_H = 108
_H_GAP = 30
_LEVEL_H = 150
_MARGIN = 40
_VIEWPORT_H = 620


def _layout_hypothesis_tree(tree: list[dict]) -> dict:
    """Simple bottom-up tree layout: every leaf gets the next unused
    horizontal slot (left to right, in existing tree order), every
    internal node is centered over the mean of its children's x — a
    standard, good-enough-for-a-modest-tree approach (not a minimal-
    width Reingold-Tilford layout, which isn't worth the complexity at
    this app's scale). Depth sets y directly, so every level lines up
    in a straight horizontal band.

    Returns {"positions": {id: {"x","y","node","depth"}}, "edges":
    [(parent_id, child_id), ...], "width", "height", "max_depth"} — all
    in SVG pixel units, unscaled (offset by _MARGIN so nothing touches
    the edge)."""
    positions: dict[int, dict] = {}
    edges: list[tuple[int, int]] = []
    next_slot = [0]
    max_depth = [0]

    def _place(nodes: list[dict], depth: int) -> None:
        max_depth[0] = max(max_depth[0], depth)
        for node in nodes:
            children = node.get("children") or []
            if children:
                _place(children, depth + 1)
                xs = [positions[c["id"]]["x"] for c in children]
                x = sum(xs) / len(xs)
            else:
                x = next_slot[0] * (_NODE_W + _H_GAP)
                next_slot[0] += 1
            positions[node["id"]] = {
                "x": x, "y": depth * _LEVEL_H, "node": node, "depth": depth,
            }
            for c in children:
                edges.append((node["id"], c["id"]))

    _place(tree, 0)
    width = max((p["x"] for p in positions.values()), default=0) + _NODE_W + 2 * _MARGIN
    height = (max_depth[0] + 1) * _LEVEL_H + 2 * _MARGIN
    return {
        "positions": positions, "edges": edges,
        "width": width, "height": height, "max_depth": max_depth[0],
    }


def _stats_line(counts: dict) -> tuple[str, str]:
    """(text, color) for one node's test-count line. Distinguishes
    "never tested" from "tested but never validated" — both matter and
    look identical if collapsed into one number."""
    tested = counts["tested"]
    if tested == 0:
        return "Not tested yet", "#888"
    bits = [f"🧪 {tested} tested"]
    if counts["validated"]:
        bits.append(f"✅ {counts['validated']}")
    if counts["invalidated"]:
        bits.append(f"❌ {counts['invalidated']}")
    color = "#1a7f37" if counts["validated"] and not counts["invalidated"] else "#4a4a4a"
    return "  ·  ".join(bits), color


def build_zoomable_tree_html(tree: list[dict], counts_by_id: dict[int, dict]) -> str:
    """A real branching node/edge tree diagram — SVG nodes connected by
    curved edges, laid out top-down by depth (see
    _layout_hypothesis_tree) — inside a hand-rolled pan/zoom viewport:
    drag to pan, scroll (or the +/−/reset buttons) to zoom. Deliberately
    no new dependency (no JS library, no graphviz): it's plain SVG plus
    ~30 lines of vanilla pointer/wheel-event JS applying a CSS
    transform, rendered via streamlit.components.v1.html, which
    sandboxes it in its own iframe.

    Always fully expanded (no collapse) — the point of a real tree
    diagram is seeing how it branches at a glance; pan/zoom is how you
    navigate a tree too big to fit on screen, not collapsing replaces
    it. Recomputed from live data on every rerun (get_hypothesis_tree
    and get_hypothesis_test_counts are both fresh queries, no caching
    anywhere in this app), so it reflects the current tree and the
    latest interview the moment either changes — nothing to refresh."""
    if not tree:
        return (
            '<div style="font-family:-apple-system,\'Segoe UI\',sans-serif;'
            'color:#888;font-style:italic;padding:12px;">'
            "No hypotheses yet — add one in List view.</div>"
        )

    layout = _layout_hypothesis_tree(tree)
    positions, edges = layout["positions"], layout["edges"]

    edge_svg = []
    for parent_id, child_id in edges:
        p, c = positions[parent_id], positions[child_id]
        x1, y1 = p["x"] + _NODE_W / 2 + _MARGIN, p["y"] + _NODE_H + _MARGIN
        x2, y2 = c["x"] + _NODE_W / 2 + _MARGIN, c["y"] + _MARGIN
        mid_y = (y1 + y2) / 2
        edge_svg.append(
            f'<path d="M {x1},{y1} C {x1},{mid_y} {x2},{mid_y} {x2},{y2}" '
            f'fill="none" stroke="#c7c7cf" stroke-width="2" />'
        )

    node_svg = []
    for hyp_id, p in positions.items():
        node = p["node"]
        is_dormant = node["state"] == "dormant"
        fill, stroke, text_color = (
            ("#eaeaea", "#bdbdbd", "#777") if is_dormant else ("#d7f3df", "#8fd4a3", "#14532d")
        )
        x, y = p["x"] + _MARGIN, p["y"] + _MARGIN
        label = html_lib.escape(f"{node['label']} · {'dormant' if is_dormant else 'active'}")
        full_text = node["text"]
        wrapped = textwrap.wrap(full_text, width=30)[:3]
        if len(textwrap.wrap(full_text, width=30)) > 3:
            wrapped[-1] = wrapped[-1].rstrip()[:27] + "…"
        stats_text, stats_color = _stats_line(
            counts_by_id.get(hyp_id, {"tested": 0, "validated": 0, "invalidated": 0, "untested": 0})
        )

        lines = [f'<tspan x="16" dy="0">{label}</tspan>']
        for i, line in enumerate(wrapped):
            lines.append(f'<tspan x="16" dy="{18 if i == 0 else 16}">{html_lib.escape(line)}</tspan>')
        text_lines = "".join(lines)
        stats_dy = 18 + 16 * max(len(wrapped) - 1, 0) + 22

        node_svg.append(f"""
            <g transform="translate({x},{y})">
                <title>{html_lib.escape(full_text)}</title>
                <rect width="{_NODE_W}" height="{_NODE_H}" rx="10"
                      fill="{fill}" stroke="{stroke}" stroke-width="1.5" />
                <text y="14" font-family="-apple-system,'Segoe UI',sans-serif"
                      font-size="13" font-weight="700" fill="{text_color}">{text_lines}</text>
                <text x="16" y="{stats_dy}" font-family="-apple-system,'Segoe UI',sans-serif"
                      font-size="11" fill="{stats_color}">{html_lib.escape(stats_text)}</text>
            </g>""")

    svg = (
        f'<svg width="{layout["width"]}" height="{layout["height"]}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'{"".join(edge_svg)}{"".join(node_svg)}</svg>'
    )

    # Auto-fit: start zoomed so the whole tree's width is visible, and
    # never zoomed further IN than 1x for a small tree (no reason to
    # start magnified). Centers it so the tree isn't pinned to a corner.
    viewport_w_estimate = 900  # components.html width isn't knowable in
    # Python at render time — Streamlit sizes the iframe to its column
    # width — so this is a reasonable default main-column estimate; the
    # zoom controls (and scroll-to-zoom) immediately correct for any gap.
    initial_scale = min(1.0, max(0.2, viewport_w_estimate / layout["width"]))
    initial_tx = max(0.0, (viewport_w_estimate - layout["width"] * initial_scale) / 2)
    initial_ty = 20.0

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
        html, body {{ margin: 0; padding: 0; font-family: -apple-system, "Segoe UI", sans-serif; }}
        #viewport {{
            width: 100%; height: {_VIEWPORT_H}px; overflow: hidden; position: relative;
            border: 1px solid #e2e2e6; border-radius: 8px; background: #fafafa; cursor: grab;
            touch-action: none;
        }}
        #canvasWrap {{ position: absolute; top: 0; left: 0; transform-origin: 0 0; }}
        .controls {{ position: absolute; top: 10px; right: 10px; display: flex; gap: 6px; z-index: 2; }}
        .controls button {{
            width: 30px; height: 30px; border-radius: 6px; border: 1px solid #d0d0d6;
            background: white; font-size: 15px; cursor: pointer; color: #333;
        }}
        .controls button:hover {{ background: #f2f2f5; }}
        .hint {{
            position: absolute; bottom: 8px; left: 12px; font-size: 11px; color: #999;
            z-index: 2; pointer-events: none;
        }}
        </style></head><body>
        <div id="viewport">
            <div id="canvasWrap">{svg}</div>
            <div class="controls">
                <button id="zoomOut" title="Zoom out">−</button>
                <button id="zoomReset" title="Reset view">⤾</button>
                <button id="zoomIn" title="Zoom in">+</button>
            </div>
            <div class="hint">Drag to pan · Scroll to zoom</div>
        </div>
        <script>
        (function() {{
            var viewport = document.getElementById('viewport');
            var canvas = document.getElementById('canvasWrap');
            var scale = {initial_scale}, tx = {initial_tx}, ty = {initial_ty};
            var initScale = scale, initTx = tx, initTy = ty;
            var dragging = false, lastX = 0, lastY = 0;

            function apply() {{
                canvas.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
            }}
            apply();

            viewport.addEventListener('pointerdown', function(e) {{
                dragging = true; lastX = e.clientX; lastY = e.clientY;
                viewport.style.cursor = 'grabbing';
                viewport.setPointerCapture(e.pointerId);
            }});
            viewport.addEventListener('pointerup', function() {{
                dragging = false; viewport.style.cursor = 'grab';
            }});
            viewport.addEventListener('pointercancel', function() {{
                dragging = false; viewport.style.cursor = 'grab';
            }});
            viewport.addEventListener('pointermove', function(e) {{
                if (!dragging) return;
                tx += e.clientX - lastX; ty += e.clientY - lastY;
                lastX = e.clientX; lastY = e.clientY;
                apply();
            }});
            viewport.addEventListener('wheel', function(e) {{
                e.preventDefault();
                var rect = viewport.getBoundingClientRect();
                var mx = e.clientX - rect.left, my = e.clientY - rect.top;
                var prevScale = scale;
                scale = Math.min(3, Math.max(0.15, scale * (e.deltaY < 0 ? 1.12 : 0.89)));
                tx = mx - (mx - tx) * (scale / prevScale);
                ty = my - (my - ty) * (scale / prevScale);
                apply();
            }}, {{passive: false}});

            document.getElementById('zoomIn').onclick = function() {{
                scale = Math.min(3, scale * 1.25); apply();
            }};
            document.getElementById('zoomOut').onclick = function() {{
                scale = Math.max(0.15, scale * 0.8); apply();
            }};
            document.getElementById('zoomReset').onclick = function() {{
                scale = initScale; tx = initTx; ty = initTy; apply();
            }};
        }})();
        </script>
        </body></html>"""


tree = storage.get_hypothesis_tree()

view_mode = st.radio(
    "View as",
    ["List (edit)", "Visual tree (branches, drag/zoom)"],
    horizontal=True,
)

if view_mode.startswith("Visual"):
    st.caption(
        "Read-only — switch to List view to add, edit, or toggle active/dormant. "
        "Drag to pan, scroll (or the +/−/⤾ buttons) to zoom. Test/validate counts "
        "come from every interview's digest and update the moment a new one is "
        "processed — nothing here needs a manual refresh."
    )
    counts_by_id = storage.get_hypothesis_test_counts(tree)
    components.html(build_zoomable_tree_html(tree, counts_by_id), height=_VIEWPORT_H + 10, scrolling=False)
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
                # Clear the box's own stored value — otherwise the next
                # time you open this expander to add another hypothesis,
                # the text you just submitted is still sitting there and
                # has to be deleted by hand before typing a new one.
                st.session_state.pop("new_family_text", None)
                st.rerun()
            else:
                st.warning("Enter some text for the new family hypothesis.")

    st.divider()
    with st.expander("🤖 Suggest hypotheses based on what we've learned so far"):
        st.caption(
            "Grounded in every interview logged so far (transcripts, notes, "
            "and full analysis) — nothing is added to the tree until you "
            "check the ones you want and click \"Add approved\" below."
        )
        suggest_api_key = env_store.load_api_key()
        if not suggest_api_key:
            st.warning("No Anthropic API key set yet. Enter one on the **Settings** page first.")

        if st.button("Suggest hypotheses", disabled=not suggest_api_key):
            with st.spinner("Reviewing the corpus..."):
                try:
                    corpus_context = _build_corpus_context_for_suggestions()
                    st.session_state.hypothesis_suggestions = ai.suggest_hypotheses(
                        corpus_context, suggest_api_key
                    )
                except ai.AIError as e:
                    st.error(str(e))

        suggestions = st.session_state.get("hypothesis_suggestions")
        if suggestions is not None:
            if not suggestions:
                st.info(
                    "No suggestions came back — usually means there isn't enough "
                    "logged yet for the AI to responsibly ground one, or nothing "
                    "stood out this time."
                )
            else:
                label_to_id = _label_to_id(tree)
                for i, s in enumerate(suggestions):
                    parent_label = (s.get("suggested_parent_label") or "").strip()
                    if parent_label and parent_label in label_to_id:
                        parent_note = f"child of **{parent_label}**"
                    else:
                        parent_note = "new root hypothesis"
                    st.checkbox(
                        f"{s.get('text', '')}  _({parent_note})_",
                        key=f"suggest_check_{i}",
                    )
                    st.caption(s.get("rationale", ""))

                c1, c2 = st.columns(2)
                with c1:
                    add_approved_clicked = st.button("✅ Add approved")
                with c2:
                    discard_clicked = st.button("🗑️ Discard suggestions")

                if add_approved_clicked:
                    added = 0
                    for i, s in enumerate(suggestions):
                        if not st.session_state.get(f"suggest_check_{i}"):
                            continue
                        text = (s.get("text") or "").strip()
                        if not text:
                            continue
                        parent_label = (s.get("suggested_parent_label") or "").strip()
                        parent_id = label_to_id.get(parent_label)  # None -> root
                        storage.add_hypothesis(parent_id, text)
                        added += 1
                    st.session_state.hypothesis_suggestions = None
                    if added:
                        st.success(f"Added {added} hypothesis(es).")
                    st.rerun()

                if discard_clicked:
                    st.session_state.hypothesis_suggestions = None
                    st.rerun()

    st.divider()
    st.subheader("Tree")

    if not tree:
        st.write("No hypotheses yet — add a family above to get started.")
    else:
        for root in tree:
            render_node(root, depth=0)
            st.markdown("---")
