"""
render.py — Shared Streamlit rendering for one processed interview's
output. Used by both app.py (a freshly-computed result) and
pages/1_Interviews.py (a past run's saved output), so both places render
tables identically. Not AI logic (ai.py owns the API calls) and not
persistence (storage.py owns the database) — purely presentation plus one
small derived-data helper (build_digest).

pages/1_Interviews.py can't simply `import app` for this, since app.py's
top-level code is the actual Streamlit page — importing it would re-run
that page's UI as a side effect.
"""

import streamlit as st

# The one hardcoded sample hypothesis for Step 2/3. Hypothesis
# management/selection comes in Step 4; both the Process Interview page
# and the Interviews page's rerun control use this as their default.
DEFAULT_HYPOTHESIS = (
    "Junior intelligence analysts spend more than 2 hours per day manually "
    "reformatting data between disconnected tools, and would adopt a "
    "solution that automates cross-tool data transfer."
)


def _md_cell(text: str) -> str:
    """Escape a value for safe placement inside a markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def build_digest(hypothesis: str, analysis: dict) -> dict:
    """A small structured summary of one run, derived entirely from its
    own AI output — no extra AI call. Kept small; intended for the
    cross-interview corpus comparison planned for a much later step."""
    ledger = analysis.get("hypothesis_ledger", [])
    status = ledger[0]["status"] if ledger else "Untested"
    pg_rows = analysis.get("pains_and_gains", [])
    pain_count = sum(1 for r in pg_rows if r.get("attribute_type") == "Pain")
    gain_count = sum(1 for r in pg_rows if r.get("attribute_type") == "Gain")
    key_learning = analysis.get("slack_writeup", {}).get("what_we_learned", "")

    return {
        "hypothesis": hypothesis,
        "status": status,
        "pain_count": pain_count,
        "gain_count": gain_count,
        "claims_to_verify_count": len(analysis.get("claims_to_verify", [])),
        "key_learning": key_learning[:280],
    }


def build_markdown_report(result: dict, hypothesis: str) -> str:
    """Turn a Step 2 structured result into one markdown document for the
    Copy/Download buttons."""
    lines = ["# Interview Analysis", "", f"**Hypothesis tested:** {hypothesis}", ""]

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


def render_analysis(result: dict, hypothesis: str, key_prefix: str = "") -> None:
    """Render a Step 2 structured result as real tables + text.

    `key_prefix` must be unique per call site when this is rendered more
    than once on the same page (e.g. one past run per expander on the
    Interviews page) so the download button's widget key doesn't clash.
    """
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
    markdown_report = build_markdown_report(result, hypothesis)
    with st.expander("📋 Copy as Markdown", expanded=False):
        st.code(markdown_report, language="markdown")
    st.download_button(
        "Download .md",
        data=markdown_report,
        file_name="interview_analysis.md",
        mime="text/markdown",
        key=f"{key_prefix}download_md",
    )
