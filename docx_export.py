"""
docx_export.py — Build a formatted Word (.docx) version of one processed
interview's analysis, mirroring how the Interviews page shows it: a title
banner, a boxed interview-details block, a colored bar per numbered
section, shaded-header tables, and boxed cards for the write-up and the
claims to verify. Pure presentation, like render.py: it takes the same
`result` / `hypothesis` / `header` that render.build_markdown_report does
and returns the file's bytes, so a download button can hand them straight
to the browser. Never touches the database or the API.
"""

import io

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

NAVY = "1F3A5F"
BLUE_LIGHT = "EAF0F8"
GRID = "B8C4D6"
ZEBRA = "F6F8FB"
GREEN_BG, GREEN = "DDF3E4", "1E6B3A"
RED_BG, RED = "FADDDD", "9B1C1C"
AMBER_BG, AMBER_BAR = "FFF6E0", "E0A100"

# (fill, text) keyed on the cell's first word, lowercased.
STATUS_COLORS = {
    "validated": (GREEN_BG, GREEN),
    "invalidated": (RED_BG, RED),
    "untested": ("ECEFF3", "4A5568"),
}
TYPE_COLORS = {"pain": (RED_BG, RED), "gain": (GREEN_BG, GREEN)}

FONT = "Calibri"
PAGE_W = 9.6  # usable width in inches (landscape letter, 0.7" margins)


def _shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for old in tc_pr.findall(qn("w:shd")):
        tc_pr.remove(old)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _borders(cell, color: str = GRID, size: int = 6, **edges) -> None:
    """Set all four cell borders; `edges` maps top/left/bottom/right to a
    (color, size) pair overriding that one edge."""
    tc_pr = cell._tc.get_or_add_tcPr()
    for old in tc_pr.findall(qn("w:tcBorders")):
        tc_pr.remove(old)
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        c, sz = edges.get(edge, (color, size))
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), c)
        borders.append(el)
    tc_pr.append(borders)


def _margins(cell, top=70, bottom=70, left=110, right=110) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for edge, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:w"), str(v))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tc_pr.append(mar)


def _repeat_header(row) -> None:
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    row._tr.get_or_add_trPr().append(el)


def _no_split(row) -> None:
    row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))


def _tidy(paragraph, before=0, after=0) -> None:
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)


def _write(paragraph, text, *, bold=False, italic=False, size=10, color=None) -> None:
    run = paragraph.add_run(text)
    run.bold, run.italic = bold, italic
    run.font.size = Pt(size)
    run.font.name = FONT
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), FONT)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _cell_text(cell, text, **fmt) -> None:
    p = cell.paragraphs[0]
    _tidy(p)
    _write(p, str(text or ""), **fmt)


def _table(doc, ncols):
    t = doc.add_table(rows=0, cols=ncols)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    return t


def _add_row(t, widths):
    row = t.add_row()
    for cell, w in zip(row.cells, widths):
        cell.width = Inches(w)
    return row


def _spacer(doc, pts=6, keep_next=False) -> None:
    p = doc.add_paragraph()
    _tidy(p)
    p.paragraph_format.line_spacing = Pt(pts)
    p.paragraph_format.keep_with_next = keep_next


def _section_bar(doc, text) -> None:
    t = _table(doc, 1)
    c = _add_row(t, [PAGE_W]).cells[0]
    _shade(c, NAVY)
    _borders(c, NAVY, 4)
    _margins(c, 80, 80, 160, 160)
    _cell_text(c, text, bold=True, size=12.5, color="FFFFFF")
    c.paragraphs[0].paragraph_format.keep_with_next = True
    _spacer(doc, 5, keep_next=True)


def _data_table(doc, headers, rows, widths, style_col=None) -> None:
    """Shaded-header table with zebra rows. `style_col` = (column index,
    color lookup) color-codes that column's cell by its first word."""
    t = _table(doc, len(headers))
    head = _add_row(t, widths)
    _repeat_header(head)
    for c, h in zip(head.cells, headers):
        _shade(c, BLUE_LIGHT)
        _borders(c, GRID, 6, bottom=(NAVY, 12))
        _margins(c)
        _cell_text(c, h, bold=True, size=9, color=NAVY)
        c.paragraphs[0].paragraph_format.keep_with_next = True
    for i, values in enumerate(rows):
        row = _add_row(t, widths)
        _no_split(row)
        for j, (c, v) in enumerate(zip(row.cells, values)):
            _borders(c)
            _margins(c)
            if i % 2:
                _shade(c, ZEBRA)
            if style_col and j == style_col[0]:
                first = (str(v).strip().split() or [""])[0].lower().strip(".,:;()")
                colors = style_col[1].get(first)
                if colors:
                    _shade(c, colors[0])
                    _cell_text(c, v, bold=True, size=9.5, color=colors[1])
                    continue
            _cell_text(c, v, size=9.5)
    _spacer(doc, 10)


def _card(doc, label, body, bar=NAVY, fill=BLUE_LIGHT) -> None:
    """A boxed card: thick colored left bar, small-caps label, body text."""
    t = _table(doc, 1)
    row = _add_row(t, [PAGE_W])
    _no_split(row)
    c = row.cells[0]
    _shade(c, fill)
    _borders(c, GRID, 4, left=(bar, 36))
    _margins(c, 90, 90, 170, 150)
    p = c.paragraphs[0]
    _tidy(p, after=2)
    _write(p, label.upper(), bold=True, size=8.5, color=bar)
    body_p = c.add_paragraph()
    _tidy(body_p)
    _write(body_p, body or "—", size=10.5)
    _spacer(doc, 6)


def _page_number_footer(section) -> None:
    fp = section.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _write(fp, "H4D Interview Analysis  ·  Page ", size=8.5, color="6B7280")
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        run = fp.add_run()
        run.font.size = Pt(8.5)
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)


def build_docx_report(result: dict, hypothesis: str, header: dict | None = None) -> bytes:
    """Return the analysis as .docx bytes. Same inputs as
    render.build_markdown_report; missing header fields render as
    "Not recorded" rather than being skipped."""
    header = header or {}
    doc = Document()

    sec = doc.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Inches(11), Inches(8.5)
    sec.left_margin = sec.right_margin = Inches(0.7)
    sec.top_margin = sec.bottom_margin = Inches(0.7)
    doc.styles["Normal"].font.name = FONT
    doc.styles["Normal"].font.size = Pt(10)
    _page_number_footer(sec)

    # Title banner
    t = _table(doc, 1)
    c = _add_row(t, [PAGE_W]).cells[0]
    _shade(c, NAVY)
    _borders(c, NAVY, 4)
    _margins(c, 180, 180, 240, 240)
    p = c.paragraphs[0]
    _tidy(p)
    _write(p, "INTERVIEW ANALYSIS", bold=True, size=9, color="A9BEDC")
    p2 = c.add_paragraph()
    _tidy(p2, before=2)
    _write(p2, header.get("interview_title") or "Interview Analysis",
           bold=True, size=22, color="FFFFFF")
    _spacer(doc, 8)

    # Interview details box
    label_w = 2.0
    t = _table(doc, 2)
    for label, value in (
        ("Interviewee", header.get("interviewee") or "Not recorded"),
        ("Date", header.get("date") or "Not recorded"),
        ("Hypothesis tested", hypothesis),
        ("Reference documents", header.get("documents") or "Not recorded"),
    ):
        row = _add_row(t, [label_w, PAGE_W - label_w])
        _no_split(row)
        a, b = row.cells
        _shade(a, BLUE_LIGHT)
        for cell in (a, b):
            _borders(cell)
            _margins(cell, 80, 80, 140, 140)
        _cell_text(a, label, bold=True, size=9.5, color=NAVY)
        _cell_text(b, value, size=10)
    if header.get("clarifying_skipped"):
        row = _add_row(t, [label_w, PAGE_W - label_w])
        _no_split(row)
        a, b = row.cells
        for cell in (a, b):
            _shade(cell, AMBER_BG)
            _borders(cell)
            _margins(cell, 80, 80, 140, 140)
        _cell_text(a, "⚠ Clarifying questions", bold=True, size=9.5, color=AMBER_BAR)
        _cell_text(
            b,
            "Skipped — submitted as an already-complete transcript; nobody "
            "was asked follow-up questions about this interview.",
            bold=True, size=10, color="7A5A00",
        )
    _spacer(doc, 12)

    # 1. Mom Test audit
    _section_bar(doc, "1.  Mom Test audit")
    mom = result.get("mom_test_audit", [])
    if not mom:
        _card(doc, "Result", "No questions failed the Mom Test.", bar=GREEN, fill=GREEN_BG)
    else:
        _data_table(
            doc,
            ["Question that fails the Mom Test (verbatim)",
             "What was wrong with the question",
             "A better question about past behavior"],
            [[r["question_verbatim"], r["what_was_wrong"], r["better_question"]] for r in mom],
            [3.2, 3.2, 3.2],
        )

    # 2. Pains and gains
    _section_bar(doc, "2.  Pains-and-gains table")
    pg = result.get("pains_and_gains", [])
    if not pg:
        _card(doc, "Result", "No pains or gains with a verbatim quote were found.")
    else:
        _data_table(
            doc,
            ["Type", "What it is", "Verbatim quote", "Evidence of strength"],
            [[r["attribute_type"], r["what_it_is"], r["verbatim_quote"], r["evidence_strength"]]
             for r in pg],
            [0.9, 3.0, 4.2, 1.5],
            style_col=(0, TYPE_COLORS),
        )

    # 3. Hypothesis ledger
    _section_bar(doc, "3.  Hypothesis ledger")
    _data_table(
        doc,
        ["Claim", "Status", "Evidence"],
        [[r["claim"], r["status"], r["evidence"]] for r in result.get("hypothesis_ledger", [])],
        [3.4, 1.3, 4.9],
        style_col=(1, STATUS_COLORS),
    )

    # 4. Sharper questions
    _section_bar(doc, "4.  Three sharper questions for the next beneficiary")
    for i, q in enumerate(result.get("sharper_questions", []), start=1):
        _card(doc, f"Question {i}", q)

    # 5. Slack write-up
    _section_bar(doc, "5.  Slack write-up")
    writeup = result.get("slack_writeup", {})
    for label, key, bar in (
        ("Hypothesis tested", "hypothesis_tested", NAVY),
        ("What we learned", "what_we_learned", GREEN),
        ("Where we were wrong", "where_we_were_wrong", RED),
        ("Next steps", "next_steps", "2B6CB0"),
    ):
        _card(doc, label, writeup.get(key, ""), bar=bar)

    # Claims to verify — amber callout
    _section_bar(doc, "Claims to verify before this goes in a brief")
    claims = result.get("claims_to_verify", [])
    if not claims:
        _card(doc, "Result", "None flagged.")
    else:
        t = _table(doc, 1)
        c = _add_row(t, [PAGE_W]).cells[0]
        _shade(c, AMBER_BG)
        _borders(c, GRID, 4, left=(AMBER_BAR, 36))
        _margins(c, 100, 100, 170, 150)
        for n, claim in enumerate(claims):
            p = c.paragraphs[0] if n == 0 else c.add_paragraph()
            _tidy(p, after=3)
            _write(p, "⚠  ", size=10, color=AMBER_BAR, bold=True)
            _write(p, claim, size=10.5)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
