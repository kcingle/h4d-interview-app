"""
ai.py — All AI/LLM logic lives here and only here. Pages call functions
from this module; they never call an AI API directly. Keeping prompts,
model calls, and response parsing in one place makes them easy to change
together without touching any page.

Through Step 6: the two-step interview analysis flow (Step 2), optional
reference-document context (Step 5), and a separate, non-crashing
interviewee-metadata suggestion call (Step 6). All structured-output API
calls use `output_config` purely as a parsing aid — it lets the app render
every result as a real table without touching a single word of the
required system prompt, which is reproduced verbatim below.
"""

import base64
import json
import re

import anthropic

import config

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AIError(Exception):
    """Raised for any AI-call failure. Pages should catch this and show
    st.error(str(e)) instead of letting the app crash."""


# ---------------------------------------------------------------------------
# The system prompt — EXACT, do not edit. Column names and headings in
# here are graded rubric items and must appear verbatim in the app.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an assistant for a Hacking for Defense student team doing DoD customer discovery.
You are given one or more hypotheses the team is testing and raw notes from a single
beneficiary interview.

STEP 1 (first, alone): Ask up to three questions about what the notes do NOT capture,
regarding (a) the interviewee's nonverbal communication relative to the hypotheses,
(b) implied-but-not-stated actions on the team's or interviewee's part, and (c) implied
implications when the interviewee's answers are viewed collectively. Output only these
questions; produce no analysis yet.

STEP 2 (only after receiving answers): Produce, in this exact order:
1. Mom Test audit — a table with exactly these columns: "Questions that fail the Mom
   Test we asked (verbatim in quotes)" | "What was wrong with the question (leading /
   hypothetical / asks for an opinion about the future / fishing for a compliment)" |
   "A better question about past behavior". One row per failing question. If none fail,
   say so explicitly.
2. Pains-and-gains table — exactly these columns: "Type of attribute (Pain or Gain)" |
   "What it is" | "Verbatim quote" | "Evidence of strength (Repeated / Single mention /
   Inferred)". If there is no verbatim quote, do not create the row.
3. Hypothesis ledger — exactly these columns: "Claim" | "Validated / Invalidated /
   Untested" | "Evidence". One row per hypothesis tested.
4. Three sharper questions to ask the next beneficiary. Each must itself pass the Mom
   Test (anchor to specific past events/behavior).
5. A Slack write-up under 200 words with exactly these headings: "Hypothesis tested" /
   "What we learned" / "Where we were wrong" / "Next steps".

FINALLY: list every claim you made above that the team must verify with a human, a
document, or a measurement before it goes in a brief.

RULES: Quote verbatim from the provided notes only; never invent or paraphrase quotes;
omit any row not supported by an exact quote. Judge Mom Test failures by whether a
question anchors to specific past behavior — a question being forward-looking is NOT by
itself a failure, since DoD requirements interviews legitimately probe future needs."""


def _build_system(documents: list[dict] | None):
    """Build the `system` request parameter. Returns the bare SYSTEM_PROMPT
    string, unchanged, when no TEXT-format documents are selected (Step
    2/3/4 behavior). When there ARE text-format documents (Step 5),
    returns a list of two text blocks instead: the untouched system
    prompt, plus a separate, clearly-labeled reference-material block —
    the prompt string itself is never edited.

    PDF-format documents are NOT included here — Claude reads a PDF
    natively as a document content block, which the API only accepts in
    a user message, not the system prompt. See _build_user_message_content.

    NOTE: only documents the user actually included are sent. If many
    large reference documents are ever selected at once this will grow
    input tokens noticeably — revisit (e.g. summarizing or truncating) if
    that becomes a real cost/context problem.
    """
    text_documents = [d for d in (documents or []) if d.get("content_format", "text") == "text"]
    if not text_documents:
        return SYSTEM_PROMPT
    sections = "\n\n".join(f"### {d['title']}\n{d['content']}" for d in text_documents)
    reference_block = (
        "REFERENCE MATERIAL — background context provided by the team, not "
        "part of the interview. Use it to inform judgment; never quote it or "
        "attribute it to the interviewee.\n\n" + sections
    )
    return [
        {"type": "text", "text": SYSTEM_PROMPT},
        {"type": "text", "text": reference_block},
    ]


def _build_user_message_content(user_text: str, documents: list[dict] | None):
    """Build the content of the FIRST user message. Returns the plain
    `user_text` string unchanged when there are no PDF-format documents
    to attach (the common case) or the accumulated reference documents
    aren't yet uploaded (falsy content is skipped, never sent empty).

    When there IS at least one uploaded PDF, returns a list instead: one
    native `document` content block per PDF (Claude reads the actual
    pages directly — no text extraction, no new dependency, just stdlib
    base64), followed by a final text block with `user_text`. This only
    needs to happen on the first message of the conversation — run_step2
    replays this same history rather than re-attaching the PDF(s) again.
    """
    pdf_documents = [
        d for d in (documents or [])
        if d.get("content_format") == "pdf" and d.get("content")
    ]
    if not pdf_documents:
        return user_text

    blocks = []
    for d in pdf_documents:
        blocks.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(d["content"]).decode("utf-8"),
            },
        })
    blocks.append({"type": "text", "text": user_text})
    return blocks


# ---------------------------------------------------------------------------
# JSON schemas — plumbing only. These control how the response is
# structured for rendering; they do not change what the model is asked to
# do (that's entirely the system prompt above). Rendered table headers in
# app.py use the exact strings from the prompt, not these field names.
# ---------------------------------------------------------------------------

CLARIFYING_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 3,
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "mom_test_audit": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_verbatim": {"type": "string"},
                    "what_was_wrong": {"type": "string"},
                    "better_question": {"type": "string"},
                },
                "required": ["question_verbatim", "what_was_wrong", "better_question"],
                "additionalProperties": False,
            },
        },
        "pains_and_gains": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "attribute_type": {"type": "string", "enum": ["Pain", "Gain"]},
                    "what_it_is": {"type": "string"},
                    "verbatim_quote": {"type": "string"},
                    "evidence_strength": {
                        "type": "string",
                        "enum": ["Repeated", "Single mention", "Inferred"],
                    },
                },
                "required": [
                    "attribute_type",
                    "what_it_is",
                    "verbatim_quote",
                    "evidence_strength",
                ],
                "additionalProperties": False,
            },
        },
        "hypothesis_ledger": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["Validated", "Invalidated", "Untested"],
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["claim", "status", "evidence"],
                "additionalProperties": False,
            },
        },
        "sharper_questions": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
        "slack_writeup": {
            "type": "object",
            "properties": {
                "hypothesis_tested": {"type": "string"},
                "what_we_learned": {"type": "string"},
                "where_we_were_wrong": {"type": "string"},
                "next_steps": {"type": "string"},
            },
            "required": [
                "hypothesis_tested",
                "what_we_learned",
                "where_we_were_wrong",
                "next_steps",
            ],
            "additionalProperties": False,
        },
        "claims_to_verify": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "mom_test_audit",
        "pains_and_gains",
        "hypothesis_ledger",
        "sharper_questions",
        "slack_writeup",
        "claims_to_verify",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _client(api_key: str) -> anthropic.Anthropic:
    if not api_key or not api_key.strip():
        raise AIError(
            "No Anthropic API key is set. Enter one on the Settings page, then try again."
        )
    return anthropic.Anthropic(api_key=api_key)


def _call(client: anthropic.Anthropic, messages: list[dict], schema: dict, system):
    """Shared call wrapper: same model/schema plumbing, one error-handling
    chain for both steps of the flow."""
    try:
        return client.messages.create(
            model=config.MODEL_NAME,
            max_tokens=8000,
            system=system,
            messages=messages,
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.AuthenticationError:
        raise AIError(
            "Your Anthropic API key was rejected. Check it on the Settings page."
        )
    except anthropic.RateLimitError:
        raise AIError("Rate limited by the Anthropic API. Wait a moment and try again.")
    except anthropic.APIConnectionError:
        raise AIError("Could not reach the Anthropic API — check your internet connection.")
    except anthropic.APIStatusError as e:
        raise AIError(f"The Anthropic API returned an error ({e.status_code}): {e.message}")
    except Exception as e:  # last resort — never let a raw exception crash the page
        raise AIError(f"Unexpected error while calling the AI: {e}")


def _extract_json(response) -> dict:
    try:
        text = next(block.text for block in response.content if block.type == "text")
    except StopIteration:
        raise AIError("The AI response didn't contain the expected structured output.")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise AIError("The AI response could not be parsed as JSON.")


# ---------------------------------------------------------------------------
# Public flow — Step 1 then Step 2
# ---------------------------------------------------------------------------


def run_step1(
    hypotheses: list[str], raw_notes: str, api_key: str, documents: list[dict] | None = None
) -> dict:
    """Step 1: ask up to three clarifying questions about the interview.

    `hypotheses`: one or more hypotheses being tested this run — the
    graded SYSTEM_PROMPT above already says "one or more hypotheses"; the
    app just lists every one of them in the user message below (the
    prompt text itself never changes based on how many there are).

    `documents` (Step 5, optional): reference documents to include as
    context — each a dict with at least "title", "content", and
    "content_format" ("text" or "pdf"). Text documents join the system
    prompt as reference material; PDF documents attach natively to this
    first user message instead (see _build_user_message_content).

    Returns {"questions": [...], "history": [user_msg, assistant_msg]}.
    `history` is the two-message exchange to replay into run_step2 so the
    conversation stays intact across both steps.
    """
    client = _client(api_key)
    hypotheses_block = "\n".join(f"- {h}" for h in hypotheses)
    user_text = (
        f"Hypotheses being tested:\n{hypotheses_block}\n\n"
        f"Raw interview notes:\n{raw_notes}"
    )
    user_content = _build_user_message_content(user_text, documents)
    response = _call(
        client,
        messages=[{"role": "user", "content": user_content}],
        schema=CLARIFYING_QUESTIONS_SCHEMA,
        system=_build_system(documents),
    )
    data = _extract_json(response)
    assistant_text = next(b.text for b in response.content if b.type == "text")

    return {
        "questions": data.get("questions", []),
        "history": [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_text},
        ],
    }


def run_step2(
    history: list[dict],
    questions: list[str],
    answers: list[str],
    api_key: str,
    documents: list[dict] | None = None,
) -> dict:
    """Step 2: produce the full analysis, given answers to the Step 1
    clarifying questions. `history` must be the two-message exchange
    returned by run_step1 for this same interview. `documents` (Step 5,
    optional) should be the SAME set passed to run_step1, so the model
    sees consistent reference material across both calls."""
    client = _client(api_key)

    if questions:
        answer_lines = "\n".join(
            f"{i + 1}. Q: {q}\n   A: {a.strip() or '(no answer given)'}"
            for i, (q, a) in enumerate(zip(questions, answers))
        )
        followup = f"Here are the answers to your clarifying questions:\n{answer_lines}"
    else:
        followup = "No clarifying questions were needed. Please proceed with the full analysis."

    messages = history + [{"role": "user", "content": followup}]
    response = _call(
        client, messages=messages, schema=ANALYSIS_SCHEMA, system=_build_system(documents)
    )
    return _extract_json(response)


# ---------------------------------------------------------------------------
# Interviewee metadata suggestion — Step 6. A small, SEPARATE call, not
# part of the two-step flow above, and does not touch SYSTEM_PROMPT or any
# of its schemas. Always reviewed and confirmed by hand before saving.
# ---------------------------------------------------------------------------

_METADATA_SYSTEM_PROMPT = (
    "You are extracting interviewee metadata for a DoD customer-discovery "
    "project. Given raw interview notes, suggest values for these fields "
    "based only on what is explicit or strongly implied in the notes: a "
    "name, or a descriptive label if anonymous (e.g. an org+role like "
    "'CENTCOM action officer'); role/title; organization/unit; seniority "
    "level; military rank if stated or clearly implied (e.g. 'Maj / O-4'); "
    "branch of service if stated or clearly implied (e.g. Army, Air Force, "
    "Navy, Marines, Space Force, or civilian/other); relationship to the "
    "problem (must be exactly 'beneficiary', 'adjacent', 'expert', or blank "
    "if unclear); and a one-line descriptor summarizing who they are. Leave "
    "any field blank (empty string) rather than guessing — never invent "
    "details the notes don't support. Do not guess a date or interview "
    "status; those are not part of this task."
)

_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "name_or_label": {"type": "string"},
        "role": {"type": "string"},
        "organization": {"type": "string"},
        "seniority_level": {"type": "string"},
        "rank": {"type": "string"},
        "branch_service": {"type": "string"},
        "relationship": {"type": "string", "enum": ["", "beneficiary", "adjacent", "expert"]},
        "descriptor": {"type": "string"},
    },
    "required": [
        "name_or_label", "role", "organization", "seniority_level", "rank",
        "branch_service", "relationship", "descriptor",
    ],
    "additionalProperties": False,
}

BLANK_METADATA = {
    "name_or_label": "",
    "role": "",
    "organization": "",
    "seniority_level": "",
    "rank": "",
    "branch_service": "",
    "relationship": "",
    "descriptor": "",
}


def suggest_metadata(raw_notes: str, api_key: str) -> dict:
    """Suggest interviewee metadata from raw notes. NEVER raises — any
    failure (no key, API error, malformed output) falls back to an
    all-blank dict, since this is a convenience suggestion the user always
    reviews and confirms by hand before it's saved."""
    if not api_key or not api_key.strip():
        return dict(BLANK_METADATA)
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=config.MODEL_NAME,
            max_tokens=1024,
            system=_METADATA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Interview notes:\n{raw_notes}"}],
            output_config={"format": {"type": "json_schema", "schema": _METADATA_SCHEMA}},
        )
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        return {field: (data.get(field) or "") for field in BLANK_METADATA}
    except Exception:
        return dict(BLANK_METADATA)


# ---------------------------------------------------------------------------
# Per-interview digest — rich, structured, quote-anchored. This is what
# later corpus-level features (testing a hypothesis across every
# interview, cross-interview search, side-by-side compare) read INSTEAD
# of full transcripts, since sending dozens of full transcripts to the
# model at once isn't viable. Every evidence item is verified against the
# interview's actual raw text before being kept — the same anti-
# fabrication rule as the main analysis, enforced again here rather than
# just trusted a second time.
# ---------------------------------------------------------------------------

DIGEST_VERSION = 3  # v3: each hypotheses[] entry carries its own exact
# "hypothesis" string (multi-hypothesis support) alongside the model's
# "claim" restatement; digest_version >= 2 checks elsewhere in the
# codebase still correctly treat v3 as "rich" — no code needed updating.

_TOPIC_TAGS_SYSTEM_PROMPT = (
    "You are extracting short topic/keyword tags for a processed DoD "
    "customer-discovery interview, to make later cross-interview search "
    "possible. Given the hypothesis tested and a summary of what was "
    "found, suggest 3 to 8 short topic tags (a few words each, lowercase, "
    "no punctuation) capturing the interview's main themes. Do not invent "
    "themes the summary doesn't support."
)

_TOPIC_TAGS_SCHEMA = {
    "type": "object",
    "properties": {
        "topics": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    },
    "required": ["topics"],
    "additionalProperties": False,
}


def _suggest_topics(hypotheses: list[str], analysis: dict, api_key: str) -> list[str]:
    """Suggest short topic/keyword tags. This is the one small, separate
    AI call the digest adds — nothing in the Step 2 output already
    produces tags. Fed the CONDENSED analysis (pains/gains + Slack
    write-up), not the full raw notes again, to keep it cheap. NEVER
    raises; falls back to [] with no key or on any failure."""
    if not api_key or not api_key.strip():
        return []
    try:
        summary_bits = [
            f"{pg.get('attribute_type', '')}: {pg.get('what_it_is', '')}"
            for pg in analysis.get("pains_and_gains", [])
        ]
        summary_bits.append(analysis.get("slack_writeup", {}).get("what_we_learned", ""))
        summary_text = "\n".join(b for b in summary_bits if b)
        hypotheses_line = "; ".join(hypotheses)

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=config.MODEL_NAME,
            max_tokens=256,
            system=_TOPIC_TAGS_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Hypotheses: {hypotheses_line}\n\nSummary:\n{summary_text}"}
            ],
            output_config={"format": {"type": "json_schema", "schema": _TOPIC_TAGS_SCHEMA}},
        )
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        return [t.strip() for t in data.get("topics", []) if isinstance(t, str) and t.strip()]
    except Exception:
        return []


def _normalize_for_match(text: str) -> str:
    """Collapse whitespace and common curly-quote/apostrophe variants to
    their straight equivalents, so a trivial Unicode presentation
    difference doesn't wrongly fail the verbatim check below."""
    text = (text or "").replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def _quote_appears_in_notes(quote: str, raw_notes: str) -> bool:
    """The verbatim check: is `quote` an exact substring of the
    interview's actual raw text, once whitespace/quote-style differences
    are normalized away? If not, it isn't evidence."""
    if not quote or not quote.strip():
        return False
    return _normalize_for_match(quote) in _normalize_for_match(raw_notes)


def _extract_verified_quotes(evidence: str, raw_notes: str) -> list[str]:
    """Pull double-quoted spans out of a hypothesis ledger row's
    free-form Evidence text, and keep only the ones that verify verbatim
    against raw_notes. Falls back to treating the whole Evidence string
    as one quote if IT verifies as-is (a row might state its quote
    without wrapping it in quotation marks). Returns [] — no invented
    fallback — if nothing verifies."""
    quoted_spans = re.findall(r'"([^"]+)"', evidence or "")
    verified = [q for q in quoted_spans if _quote_appears_in_notes(q, raw_notes)]
    if verified:
        return verified
    if _quote_appears_in_notes(evidence, raw_notes):
        return [evidence.strip()]
    return []


def build_digest(
    hypotheses: list[str],
    analysis: dict,
    raw_notes: str,
    api_key: str = "",
    person: dict | None = None,
) -> dict:
    """Build the rich, quote-anchored digest for one processed run.
    Derived mostly from the already-computed Step 2 `analysis` — no full
    re-read needed for hypotheses or pains/gains, which already carry (or
    can be checked against) verbatim quotes. The one new, small AI call
    is for topic tags (see _suggest_topics); it never raises, so this
    function always returns a complete, valid digest — with an empty
    topics list when there's no key or that call fails — never crashing
    and never leaving other fields incomplete because of it.

    `hypotheses`: every hypothesis tested this run (one or more), in the
    SAME order they were sent to run_step1/run_step2. Paired POSITIONALLY
    with analysis["hypothesis_ledger"] (the model is asked for "one row
    per hypothesis tested," in the same order) — each digest entry then
    carries the exact tested string in its "hypothesis" field (not just
    the model's own "claim" restatement), which is what later cross-run
    matching (Hypothesis Status, Compare) keys off. If the model produced
    fewer ledger rows than hypotheses tested, the missing ones are marked
    Untested with no quotes rather than guessing which is missing — same
    anti-fabrication rule as everywhere else in this digest.

    `person` (optional): the interviewee's metadata, if already known.
    Often not yet known when a run is first saved (metadata confirmation
    happens right after) — pass None then, and call this again once
    confirmed to refresh the digest's interviewee field.
    """
    ledger = analysis.get("hypothesis_ledger", [])
    hypotheses_digest = []
    for i, hypothesis_text in enumerate(hypotheses):
        if i < len(ledger):
            row = ledger[i]
            hypotheses_digest.append({
                "hypothesis": hypothesis_text,
                "claim": row.get("claim", ""),
                "status": row.get("status", "Untested"),
                "quotes": _extract_verified_quotes(row.get("evidence", ""), raw_notes),
            })
        else:
            # The model produced fewer ledger rows than hypotheses tested —
            # don't guess which one is missing.
            hypotheses_digest.append({
                "hypothesis": hypothesis_text, "claim": "", "status": "Untested", "quotes": [],
            })

    pains, gains = [], []
    for row in analysis.get("pains_and_gains", []):
        quote = row.get("verbatim_quote", "")
        if not _quote_appears_in_notes(quote, raw_notes):
            continue  # unverified — dropped, not propagated
        entry = {
            "what": row.get("what_it_is", ""),
            "quote": quote,
            "strength": row.get("evidence_strength", ""),
        }
        (pains if row.get("attribute_type") == "Pain" else gains).append(entry)

    interviewee = None
    if person:
        interviewee = {
            "name": person.get("name") or "",
            "role": person.get("role") or "",
            "organization": person.get("organization") or "",
        }

    return {
        "digest_version": DIGEST_VERSION,
        "hypotheses_tested": list(hypotheses),
        "interviewee": interviewee,
        "hypotheses": hypotheses_digest,
        "pains": pains,
        "gains": gains,
        "topics": _suggest_topics(hypotheses, analysis, api_key),
        "claims_to_verify": list(analysis.get("claims_to_verify", [])),
    }
