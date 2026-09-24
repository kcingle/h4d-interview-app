"""
render.py — Shared Streamlit rendering for one processed interview's
output. Used by both pages/1_Interviews.py and pages/7_Metadata.py (each
showing a past run's saved output), so both places render tables
identically. Not AI logic (ai.py owns the API calls, including building
the per-run digest — see ai.build_digest) and not persistence
(storage.py owns the database) — purely presentation.

(Process_Interview.py, the entry point, hands off to the Interviews page
immediately after saving a run rather than rendering results itself —
see that file's docstring — so it no longer uses this module for that.)
"""

import re

import streamlit as st

from docx_export import build_docx_report


def _flatten_hypothesis_tree(nodes: list[dict], depth: int = 0) -> list[tuple[dict, int]]:
    """Flatten a hypothesis tree (as returned by storage.get_hypothesis_tree)
    into a depth-first list of (node, depth) pairs, preserving the tree's
    own sort order. Depth is used purely for display indentation."""
    flat = []
    for node in nodes:
        flat.append((node, depth))
        flat.extend(_flatten_hypothesis_tree(node["children"], depth + 1))
    return flat


def render_hypothesis_picker(tree: list[dict], key_prefix: str) -> list[str]:
    """Render one checkbox per hypothesis in the tree, indented by depth,
    active nodes pre-checked and dormant nodes available but unchecked —
    and return the statement text of every checked node, in tree order.

    Shared by the Process Interview page and the Interviews page's rerun
    control so selecting one or more hypotheses to test looks and behaves
    identically everywhere. `key_prefix` must be unique per call site
    (e.g. per-interview on the rerun control) so widget keys don't clash.
    """
    flat = _flatten_hypothesis_tree(tree)
    if not flat:
        st.caption("No hypotheses yet — add some on the Hypotheses page.")
        return []
    selected = []
    for node, depth in flat:
        indent = " " * 4 * depth
        suffix = "  _(dormant)_" if node["state"] == "dormant" else ""
        label = f"{indent}{node['text']}{suffix}"
        checked = st.checkbox(
            label,
            value=(node["state"] == "active"),
            key=f"{key_prefix}_{node['id']}",
        )
        if checked:
            selected.append(node["text"])
    return selected


def _docx_filename(header: dict | None) -> str:
    """A safe .docx filename from the interview title, e.g.
    "(MAJ Qazi, 2026-09-17)" -> "MAJ Qazi 2026-09-17 - Interview Analysis.docx"."""
    title = ((header or {}).get("interview_title") or "").strip("() ")
    title = re.sub(r'[\/:*?"<>|,]+', "", title).strip()
    return f"{title} - Interview Analysis.docx" if title else "Interview Analysis.docx"


def _md_cell(text: str) -> str:
    """Escape a value for safe placement inside a markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def build_export_header(
    interview: dict | None, person: dict | None, run: dict, document_titles: list[str]
) -> dict:
    """Build the header dict for render_analysis's `export_header` param.
    Callers resolve `person` (via storage.get_person_for_interview) and
    `document_titles` (via storage.get_document for each of the run's
    document_ids — using a placeholder string for any that were since
    deleted) — this function only formats them for display. Never raises:
    a missing interview/person/documents just renders as "Not recorded"."""
    interviewee = None
    if person:
        label = (person.get("name") or "").strip()
        sub = ", ".join(x for x in [person.get("role"), person.get("organization")] if x)
        interviewee = f"{label} ({sub})" if label and sub else (label or None)

    return {
        "interview_title": interview["title"] if interview else None,
        "interviewee": interviewee,
        "date": (run.get("created_at") or "")[:19].replace("T", " ") or None,
        "documents": ", ".join(document_titles) if document_titles else None,
        "clarifying_skipped": bool(run.get("clarifying_skipped")),
    }


def _format_header_lines(hypothesis: str, header: dict | None) -> list[str]:
    """Markdown lines for an export's header block: interview title,
    interviewee, date, hypothesis tested, and reference documents used.
    `header` is optional (None renders just the hypothesis line, as
    before Step 7) so this stays backward compatible with any future
    caller that doesn't build one."""
    lines = []
    if header:
        if header.get("interview_title"):
            lines.append(f"**Interview:** {header['interview_title']}")
        lines.append(f"**Interviewee:** {header.get('interviewee') or 'Not recorded'}")
        if header.get("date"):
            lines.append(f"**Date:** {header['date']}")
    lines.append(f"**Hypothesis tested:** {hypothesis}")
    if header:
        lines.append(f"**Reference documents used:** {header.get('documents') or 'Not recorded'}")
        if header.get("clarifying_skipped"):
            lines.append(
                "**⚠ Clarifying questions skipped:** submitted as an already-"
                "complete transcript — nobody was asked follow-up questions "
                "about this interview."
            )
    return lines


def build_markdown_report(result: dict, hypothesis: str, header: dict | None = None) -> str:
    """Turn a Step 2 structured result into one markdown document for the
    Copy/Download buttons. `header` (Step 7, optional) adds interview
    title/interviewee/date/documents-used lines above the hypothesis line."""
    lines = ["# Interview Analysis", ""]
    lines.extend(_format_header_lines(hypothesis, header))
    lines.append("")

    lines.append("## 1. Mom Test audit")
    mom_rows = result.get("mom_test_audit", [])
    if not mom_rows:
        lines.append("No questions failed the Mom Test.")
    else:
        lines.append(
            "| Questions that fail the Mom Test we asked (verbatim in quotes) "
            "| What was wrong with the question (leading / hypothetical / asks "
            "for an opinion about the future / fishing for a compliment) "
            "| A better question about past behavior |"
        )
        lines.append("|---|---|---|")
        for r in mom_rows:
            lines.append(
                f"| {_md_cell(r['question_verbatim'])} | {_md_cell(r['what_was_wrong'])} "
                f"| {_md_cell(r['better_question'])} |"
            )
    lines.append("")

    lines.append("## 2. Pains-and-gains table")
    pg_rows = result.get("pains_and_gains", [])
    if not pg_rows:
        lines.append("No pains or gains with a verbatim quote were found.")
    else:
        lines.append(
            "| Type of attribute (Pain or Gain) | What it is | Verbatim quote "
            "| Evidence of strength (Repeated / Single mention / Inferred) |"
        )
        lines.append("|---|---|---|---|")
        for r in pg_rows:
            lines.append(
                f"| {_md_cell(r['attribute_type'])} | {_md_cell(r['what_it_is'])} "
                f"| {_md_cell(r['verbatim_quote'])} | {_md_cell(r['evidence_strength'])} |"
            )
    lines.append("")

    lines.append("## 3. Hypothesis ledger")
    ledger_rows = result.get("hypothesis_ledger", [])
    lines.append("| Claim | Validated / Invalidated / Untested | Evidence |")
    lines.append("|---|---|---|")
    for r in ledger_rows:
        lines.append(f"| {_md_cell(r['claim'])} | {_md_cell(r['status'])} | {_md_cell(r['evidence'])} |")
    lines.append("")

    lines.append("## 4. Three sharper questions for the next beneficiary")
    for i, q in enumerate(result.get("sharper_questions", []), start=1):
        lines.append(f"{i}. {q}")
    lines.append("")

    writeup = result.get("slack_writeup", {})
    lines.append("## 5. Slack write-up")
    lines.append(f"**Hypothesis tested**  \n{writeup.get('hypothesis_tested', '')}")
    lines.append("")
    lines.append(f"**What we learned**  \n{writeup.get('what_we_learned', '')}")
    lines.append("")
    lines.append(f"**Where we were wrong**  \n{writeup.get('where_we_were_wrong', '')}")
    lines.append("")
    lines.append(f"**Next steps**  \n{writeup.get('next_steps', '')}")
    lines.append("")

    lines.append("## Claims to verify before this goes in a brief")
    claims = result.get("claims_to_verify", [])
    if not claims:
        lines.append("None flagged.")
    else:
        for c in claims:
            lines.append(f"- {c}")

    return "\n".join(lines)


def render_analysis(
    result: dict,
    hypothesis: str,
    key_prefix: str = "",
    export_header: dict | None = None,
) -> None:
    """Render a Step 2 structured result as real tables + text.

    `key_prefix` must be unique per call site when this is rendered more
    than once on the same page (e.g. one past run per expander on the
    Interviews page) so the download button's widget key doesn't clash.

    `export_header` (Step 7, optional): a dict from build_export_header()
    — adds interview title/interviewee/date/documents-used to the top of
    the exported Markdown/.txt. Omitted lines render as "Not recorded"
    rather than being skipped, so a run missing metadata or documents
    still exports cleanly.
    """
    if export_header and export_header.get("clarifying_skipped"):
        st.warning(
            "⚠ Clarifying questions skipped — submitted as an already-"
            "complete transcript. Nobody was asked follow-up questions "
            "about this interview."
        )
    st.subheader("1. Mom Test audit")
    mom_rows = result.get("mom_test_audit", [])
    if not mom_rows:
        st.success("No questions failed the Mom Test.")
    else:
        st.dataframe(
            [
                {
                    "Questions that fail the Mom Test we asked (verbatim in quotes)": r[
                        "question_verbatim"
                    ],
                    "What was wrong with the question (leading / hypothetical / asks "
                    "for an opinion about the future / fishing for a compliment)": r[
                        "what_was_wrong"
                    ],
                    "A better question about past behavior": r["better_question"],
                }
                for r in mom_rows
            ],
            use_container_width=True,
        )

    st.subheader("2. Pains-and-gains table")
    pg_rows = result.get("pains_and_gains", [])
    if not pg_rows:
        st.write("No pains or gains with a verbatim quote were found.")
    else:
        st.dataframe(
            [
                {
                    "Type of attribute (Pain or Gain)": r["attribute_type"],
                    "What it is": r["what_it_is"],
                    "Verbatim quote": r["verbatim_quote"],
                    "Evidence of strength (Repeated / Single mention / Inferred)": r[
                        "evidence_strength"
                    ],
                }
                for r in pg_rows
            ],
            use_container_width=True,
        )

    st.subheader("3. Hypothesis ledger")
    ledger_rows = result.get("hypothesis_ledger", [])
    st.dataframe(
        [
            {
                "Claim": r["claim"],
                "Validated / Invalidated / Untested": r["status"],
                "Evidence": r["evidence"],
            }
            for r in ledger_rows
        ],
        use_container_width=True,
    )

    st.subheader("4. Three sharper questions for the next beneficiary")
    for i, q in enumerate(result.get("sharper_questions", []), start=1):
        st.write(f"{i}. {q}")

    st.subheader("5. Slack write-up")
    writeup = result.get("slack_writeup", {})
    st.markdown(
        f"**Hypothesis tested**  \n{writeup.get('hypothesis_tested', '')}\n\n"
        f"**What we learned**  \n{writeup.get('what_we_learned', '')}\n\n"
        f"**Where we were wrong**  \n{writeup.get('where_we_were_wrong', '')}\n\n"
        f"**Next steps**  \n{writeup.get('next_steps', '')}"
    )

    st.subheader("Claims to verify before this goes in a brief")
    claims = result.get("claims_to_verify", [])
    if not claims:
        st.write("None flagged.")
    else:
        for c in claims:
            st.write(f"- {c}")

    st.divider()
    st.subheader("Export")
    markdown_report = build_markdown_report(result, hypothesis, header=export_header)
    # No st.expander here (unlike a plain page): render_analysis is often
    # called from inside an outer expander (one per past run, on the
    # Interviews and Metadata pages), and Streamlit does not allow nested
    # expanders — this bit both of those pages from Step 3 onward,
    # whenever a run was actually expanded, until this fix.
    st.caption("📋 Copy report — hover the block below and click the copy icon in its corner.")
    st.code(markdown_report, language="markdown")
    # Word is the one download: a formatted document that mirrors the
    # tables and boxes shown above (see docx_export.py). The copy block
    # above stays for pasting the plain-text version into Slack/email.
    st.download_button(
        "Download as Word document",
        data=build_docx_report(result, hypothesis, header=export_header),
        file_name=_docx_filename(export_header),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{key_prefix}download_docx",
        type="primary",
    )
