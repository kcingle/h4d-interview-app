"""
weekly_brief.py — Fills the GOVT 391 team-brief PowerPoint template
(assets/weekly_brief_template.pptx) from a `fields` dict built by
pages/11_Weekly_Brief.py's Stage 2 form. Called ONLY when "Build the
deck" is clicked — nothing here runs before that.

The template's own copy (slides 1 and 3) is never touched except the
cover date. Text is filled by overwriting individual text-run objects
addressed by (slide index, shape name) — every bracketed slot in this
template is either a whole run (the entire run IS the bracket) or a
known substring within a run (e.g. the compound "We believe that
[statement] — and we would be wrong if [...]" line) — verified by
reading the template's actual XML runs before writing this, not
guessed. A field left blank by the user just becomes an empty run,
never a leftover "[bracket]" — the one exception the template's own
"Before You Present" checklist calls out.

HYPOTHESIS_SLOTS / TESTS_PER_HYPOTHESIS / INTERVIEWS_QUEUED_ROWS are the
template's fixed slide geometry (3 hypothesis slides, 3 test rows each,
5 discovery-plan rows) — the calling page enforces these caps in Stage 1
so build_deck() never receives more than the template can hold.
"""

import io
from pathlib import Path

from pptx import Presentation

TEMPLATE_PATH = Path(__file__).parent / "assets" / "weekly_brief_template.pptx"

HYPOTHESIS_SLOTS = 3
TESTS_PER_HYPOTHESIS = 3
INTERVIEWS_QUEUED_ROWS = 5

# 0-indexed positions, in the template's ORIGINAL (pre-deletion) slide
# order, of the how-to slide and the two "WORKED EXAMPLE" slides — deleted
# last, in descending order, so removing one never shifts the index of
# another still waiting to be removed.
_SLIDES_TO_DELETE = [10, 5, 1]


def get_team_roster() -> list[str]:
    """Team member names, parsed live from the template's own slide 3
    "Team: A | B | C" line — so the Owner selector always reflects
    whoever the template actually lists, with no second roster to drift
    out of sync with it."""
    prs = Presentation(TEMPLATE_PATH)
    slide = prs.slides[2]
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        text = shape.text_frame.text
        if text.startswith("Team:"):
            names = text.split(":", 1)[1]
            return [n.strip() for n in names.split("|") if n.strip()]
    return []


def _shape_by_name(slide, name: str):
    for shape in slide.shapes:
        if shape.name == name:
            return shape
    raise KeyError(f"No shape named {name!r} on this slide")


def _set_run_text(slide, shape_name: str, text: str, para_idx: int = 0, run_idx: int = 0) -> None:
    """Overwrite one run's text outright — used where the ENTIRE run is
    the bracketed placeholder, so no surrounding text needs preserving."""
    shape = _shape_by_name(slide, shape_name)
    shape.text_frame.paragraphs[para_idx].runs[run_idx].text = text or ""


def _replace_in_run(slide, shape_name: str, replacements: list[tuple[str, str]],
                     para_idx: int = 0, run_idx: int = 0) -> None:
    """Substring-replace one or more bracketed phrases WITHIN a run that
    also contains fixed surrounding text (e.g. "From the sponsor:
    [introduction, document, access]") — preserves everything except the
    bracket itself."""
    shape = _shape_by_name(slide, shape_name)
    run = shape.text_frame.paragraphs[para_idx].runs[run_idx]
    text = run.text
    for old, new in replacements:
        text = text.replace(old, new or "")
    run.text = text


def _delete_slide(prs, index: int) -> None:
    """Remove one slide (by 0-indexed position) and its relationship —
    the standard python-pptx approach; there's no built-in delete_slide."""
    xml_slides = prs.slides._sldIdLst
    slides = list(xml_slides)
    rId = slides[index].rId
    prs.part.drop_rel(rId)
    xml_slides.remove(slides[index])


def build_deck(fields: dict) -> bytes:
    """Fill the template from `fields` and return the finished .pptx as
    bytes. Expected shape of `fields`:

    {
      "brief_date": "Tuesday 15 September" | "",   # optional; blank = leave template's date as-is
      "problem": {"beneficiary", "problem", "mission_impact", "workaround", "why_now"},
      "what_changed": {"as_given", "as_refined", "moved_us_1", "moved_us_2"},
      "hypotheses": [  # EXACTLY 3, in H1/H2/H3 order
        {
          "short_name", "statement", "owner", "would_be_wrong_if",
          "tests": [{"question", "who", "disprove"}, ...]  # 0-3 entries
        },
        ...
      ],
      "discovery": {
        "interviews_queued": [{"name_role", "segment", "when"}, ...],  # 0-5 entries
        "need_sponsor", "need_mentors", "need_instructor",
        "battle_meeting", "battle_sponsor", "battle_notes_owner",
      },
    }
    """
    if len(fields["hypotheses"]) != HYPOTHESIS_SLOTS:
        raise ValueError(f"Expected exactly {HYPOTHESIS_SLOTS} hypotheses, got {len(fields['hypotheses'])}")

    prs = Presentation(TEMPLATE_PATH)

    # ---- Slide 1 (index 0): cover — only the date changes ----
    if fields.get("brief_date"):
        slide = prs.slides[0]
        shape = _shape_by_name(slide, "TextBox 7")
        run = shape.text_frame.paragraphs[0].runs[0]
        prefix = "Team Brief, "
        idx = run.text.find(prefix)
        if idx != -1:
            run.text = run.text[: idx + len(prefix)] + fields["brief_date"]

    # ---- Slide 4 (index 3): Refined Problem Statement ----
    p = fields["problem"]
    slide = prs.slides[3]
    _set_run_text(slide, "TextBox 5", p.get("beneficiary", ""))
    _set_run_text(slide, "TextBox 7", p.get("problem", ""))
    _set_run_text(slide, "TextBox 9", p.get("mission_impact", ""))
    _set_run_text(slide, "TextBox 11", p.get("workaround", ""))
    _set_run_text(slide, "TextBox 13", p.get("why_now", ""))

    # ---- Slide 5 (index 4): What Changed ----
    w = fields["what_changed"]
    slide = prs.slides[4]
    _set_run_text(slide, "TextBox 5", w.get("as_given", ""))
    _set_run_text(slide, "TextBox 8", w.get("as_refined", ""))
    _set_run_text(slide, "TextBox 11", w.get("moved_us_1", ""), para_idx=0, run_idx=1)
    _set_run_text(slide, "TextBox 11", w.get("moved_us_2", ""), para_idx=1, run_idx=1)

    # ---- Slide 7 (index 6): Initial Hypotheses — H1/H2/H3 ----
    hyps = fields["hypotheses"]
    slide = prs.slides[6]
    h_shape_map = [
        ("TextBox 6", "TextBox 7", "TextBox 10"),
        ("TextBox 14", "TextBox 15", "TextBox 18"),
        ("TextBox 22", "TextBox 23", "TextBox 26"),
    ]
    for h, (name_shape, stmt_shape, owner_shape) in zip(hyps, h_shape_map):
        _set_run_text(slide, name_shape, h.get("short_name", ""))
        _set_run_text(slide, stmt_shape, h.get("statement", ""))
        _set_run_text(slide, owner_shape, h.get("owner", ""))

    # ---- Slides 8/9/10 (index 7/8/9): Hypothesis N of 3 · Tests ----
    test_row_shapes = [
        ("TextBox 11", "TextBox 12", "TextBox 13"),
        ("TextBox 17", "TextBox 18", "TextBox 19"),
        ("TextBox 23", "TextBox 24", "TextBox 25"),
    ]
    for i, h in enumerate(hyps):
        slide = prs.slides[7 + i]
        _set_run_text(slide, "TextBox 2", h.get("short_name", ""))
        _replace_in_run(
            slide, "TextBox 4",
            [
                ("[statement]", h.get("statement", "")),
                ("[what we would see instead]", h.get("would_be_wrong_if", "")),
            ],
        )
        tests = (h.get("tests") or [])[:TESTS_PER_HYPOTHESIS]
        for row_idx, (q_shape, who_shape, disprove_shape) in enumerate(test_row_shapes):
            if row_idx < len(tests):
                t = tests[row_idx]
                _set_run_text(slide, q_shape, t.get("question", ""))
                _set_run_text(slide, who_shape, t.get("who", ""))
                _set_run_text(slide, disprove_shape, t.get("disprove", ""))
            else:
                # No test picked for this row — blank it rather than leave
                # the original [bracketed] prompt behind.
                _set_run_text(slide, q_shape, "")
                _set_run_text(slide, who_shape, "")
                _set_run_text(slide, disprove_shape, "")

    # ---- Slide 12 (index 11): Discovery Plan ----
    d = fields["discovery"]
    slide = prs.slides[11]
    queue_row_shapes = [
        ("TextBox 8", "TextBox 9", "TextBox 10"),
        ("TextBox 12", "TextBox 13", "TextBox 14"),
        ("TextBox 16", "TextBox 17", "TextBox 18"),
        ("TextBox 20", "TextBox 21", "TextBox 22"),
        ("TextBox 24", "TextBox 25", "TextBox 26"),
    ]
    queued = (d.get("interviews_queued") or [])[:INTERVIEWS_QUEUED_ROWS]
    for row_idx, (name_shape, seg_shape, when_shape) in enumerate(queue_row_shapes):
        if row_idx < len(queued):
            q = queued[row_idx]
            _set_run_text(slide, name_shape, q.get("name_role", ""))
            _set_run_text(slide, seg_shape, q.get("segment", ""))
            _set_run_text(slide, when_shape, q.get("when", ""))
        else:
            _set_run_text(slide, name_shape, "")
            _set_run_text(slide, seg_shape, "")
            _set_run_text(slide, when_shape, "")

    _replace_in_run(
        slide, "TextBox 29",
        [("[introduction, document, access]", d.get("need_sponsor", ""))],
        para_idx=0, run_idx=1,
    )
    _replace_in_run(
        slide, "TextBox 29",
        [("[specific question]", d.get("need_mentors", ""))],
        para_idx=1, run_idx=1,
    )
    _replace_in_run(
        slide, "TextBox 29",
        [("[decision or unblock]", d.get("need_instructor", ""))],
        para_idx=2, run_idx=1,
    )

    _replace_in_run(
        slide, "TextBox 32",
        [
            ("[Team meeting: day/time]", d.get("battle_meeting", "")),
            ("[Sponsor touchpoint: cadence]", d.get("battle_sponsor", "")),
            ("[Who owns notes and the interview log]", d.get("battle_notes_owner", "")),
        ],
    )

    # ---- Delete the how-to slide and both worked examples ----
    for idx in _SLIDES_TO_DELETE:
        _delete_slide(prs, idx)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
