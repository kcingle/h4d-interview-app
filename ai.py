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
import render  # only for build_markdown_report, reused by build_corpus_context
# below so the Chat page's per-run context matches the exact same
# Mom Test/pains-and-gains/hypothesis-ledger/etc. formatting the rest of
# the app already shows. render.py makes no persistence or AI calls of
# its own, so this doesn't create a cycle back into this module.

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
            # No "maxItems" here — Claude's structured-output schema doesn't
            # support array size constraints (a live call with one returns a
            # 400: "For 'array' type, property 'maxItems' is not
            # supported"). The "up to three" limit is already in
            # SYSTEM_PROMPT's instructions; run_step1 below also truncates
            # to 3 in code as a safety net, never padding if there are fewer.
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
            # No "minItems"/"maxItems" — same unsupported-keyword issue as
            # CLARIFYING_QUESTIONS_SCHEMA above. SYSTEM_PROMPT already asks
            # for exactly three; run_step2 below truncates to 3 in code if
            # the model ever returns more, and leaves it alone (never pads)
            # if it returns fewer.
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


def _call(
    client: anthropic.Anthropic,
    messages: list[dict],
    system,
    schema: dict | None = None,
    max_tokens: int = 8000,
):
    """Shared call wrapper: same model plumbing, one error-handling chain
    for every call site. `schema` (optional) adds output_config for a
    structured-output call (the two-step analysis); omit it for a
    free-form text call (chat)."""
    kwargs = dict(model=config.MODEL_NAME, max_tokens=max_tokens, system=system, messages=messages)
    if schema is not None:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    try:
        return client.messages.create(**kwargs)
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


def _extract_text(response) -> str:
    try:
        return next(block.text for block in response.content if block.type == "text")
    except StopIteration:
        raise AIError("The AI response didn't contain any text.")


# ---------------------------------------------------------------------------
# Public flow — Step 1 then Step 2
# ---------------------------------------------------------------------------


def run_step1(
    hypotheses: list[str],
    raw_notes: str,
    api_key: str,
    documents: list[dict] | None = None,
    additional_notes: str = "",
) -> dict:
    """Step 1: ask up to three clarifying questions about the interview.

    `hypotheses`: one or more hypotheses being tested this run — the
    graded SYSTEM_PROMPT above already says "one or more hypotheses"; the
    app just lists every one of them in the user message below (the
    prompt text itself never changes based on how many there are).

    `additional_notes` (optional): free-form context the interviewer typed
    separately from the transcript — nonverbal communication, tone, the
    setting, or anything else observed but not written as dialogue. Appended
    to the user message as its own clearly-labeled section (never merged
    into `raw_notes` itself, so the interview's stored transcript stays
    exactly what was actually said).

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
    if additional_notes and additional_notes.strip():
        user_text += (
            "\n\nAdditional notes from the interviewer (not part of the "
            "transcript — e.g. nonverbal communication, tone, body language, "
            "the setting, or other context observed during the interview):\n"
            f"{additional_notes.strip()}"
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

    # Enforce "up to three" in code — the schema itself can't (see
    # CLARIFYING_QUESTIONS_SCHEMA above). Truncate only; never pad if the
    # model returns fewer than three.
    questions = list(data.get("questions", []))[:3]

    return {
        "questions": questions,
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
    data = _extract_json(response)

    # Enforce "exactly three" sharper questions in code — the schema
    # itself can't (see ANALYSIS_SCHEMA above). Truncate only; never pad
    # with invented questions if the model returns fewer than three.
    data["sharper_questions"] = list(data.get("sharper_questions", []))[:3]

    return data


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
        # No "maxItems" — same unsupported-keyword issue as the schemas
        # above. The system prompt already asks for 3 to 8 tags;
        # _suggest_topics below truncates to 8 in code as a safety net.
        "topics": {"type": "array", "items": {"type": "string"}},
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
        topics = [t.strip() for t in data.get("topics", []) if isinstance(t, str) and t.strip()]
        # Enforce the cap of 8 in code — the schema itself can't (see
        # _TOPIC_TAGS_SCHEMA above). Truncate only; never pad.
        return topics[:8]
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
    additional_notes: str = "",
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
    matching (Hypothesis Findings, Compare) keys off. If the model produced
    fewer ledger rows than hypotheses tested, the missing ones are marked
    Untested with no quotes rather than guessing which is missing — same
    anti-fabrication rule as everywhere else in this digest.

    `person` (optional): the interviewee's metadata, if already known.
    Often not yet known when a run is first saved (metadata confirmation
    happens right after) — pass None then, and call this again once
    confirmed to refresh the digest's interviewee field.

    `additional_notes` (optional): the same interviewer-supplied context
    passed to run_step1 (see there). Included alongside raw_notes as
    source text for the verbatim-quote check below — a quote the model
    pulls from these notes (not just the transcript) is real, interviewer-
    written text, not a fabrication, so it still counts as verified.
    """
    verification_text = raw_notes
    if additional_notes and additional_notes.strip():
        verification_text = f"{raw_notes}\n\n{additional_notes.strip()}"

    ledger = analysis.get("hypothesis_ledger", [])
    hypotheses_digest = []
    for i, hypothesis_text in enumerate(hypotheses):
        if i < len(ledger):
            row = ledger[i]
            hypotheses_digest.append({
                "hypothesis": hypothesis_text,
                "claim": row.get("claim", ""),
                "status": row.get("status", "Untested"),
                "quotes": _extract_verified_quotes(row.get("evidence", ""), verification_text),
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
        if not _quote_appears_in_notes(quote, verification_text):
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


# ---------------------------------------------------------------------------
# Chat — talks about the WHOLE corpus, not one interview. A different kind
# of feature from everything above: Hypothesis Findings and Search & Compare
# deliberately do zero AI synthesis (pure retrieval), but a chat is
# inherently synthesis. The anti-fabrication rule still applies, just
# enforced through the system prompt's instructions (cite the interview a
# claim comes from; say so when something isn't in the material) rather
# than a verbatim-quote check on free-form conversational text, since
# there's no fixed "evidence" field here to check the way there is for a
# hypothesis ledger row.
# ---------------------------------------------------------------------------

CHAT_SYSTEM_INSTRUCTIONS = (
    "You are a research assistant helping a Hacking for Defense (H4D) "
    "student team review everything they've learned across their DoD "
    "customer-discovery interviews. Below this message is the team's "
    "complete hypothesis tree, their interviewee roster, their reference "
    "document list, and — for every interview logged so far — its raw "
    "transcript, any additional interviewer notes, and the full analysis "
    "produced for every run against it (Mom Test audit, pains and gains, "
    "hypothesis ledger, sharper questions, and Slack write-up).\n\n"
    "Answer ONLY from this material. When you state a finding, name which "
    "interview it comes from (its title and/or date) so the team can "
    "trace it back. If something the team asks about isn't covered by "
    "this material, say so plainly instead of guessing — never invent a "
    "quote, a number, or a finding that isn't actually below. You may "
    "synthesize across multiple interviews (spot a pattern, count how "
    "many validated a hypothesis, compare two interviewees) as long as "
    "every individual claim inside that synthesis still traces back to a "
    "specific interview."
)


def _flatten_hypotheses_for_context(nodes: list[dict], depth: int = 0) -> list[tuple[dict, int]]:
    """Same depth-first flatten as render._flatten_hypothesis_tree, kept
    as its own copy here rather than importing that (leading-underscore,
    render-specific) helper — this one is a plain data transform with no
    Streamlit involved, appropriate to live with the rest of ai.py's
    context-building code."""
    flat = []
    for node in nodes:
        flat.append((node, depth))
        flat.extend(_flatten_hypotheses_for_context(node.get("children", []), depth + 1))
    return flat


def build_corpus_context(
    hypotheses_tree: list[dict],
    interviews: list[dict],
    people: list[dict],
    documents: list[dict],
) -> str:
    """Build one large text blob covering everything else in the app
    knows, for the Chat page to send as a (cached) system block on every
    turn: the hypothesis tree, the people roster, the reference document
    list, and every interview's raw transcript + Additional Notes + full
    analysis for each of its runs — reusing render.build_markdown_report
    so the exact same Mom Test audit / pains-and-gains / hypothesis
    ledger / sharper questions / Slack write-up formatting the rest of
    the app already shows appears here too.

    `interviews`: each dict from storage.get_interviews(), augmented by
    the caller with "person" (storage.get_person_for_interview) and
    "runs" (storage.get_runs_for_interview) — this function only reads
    and formats them, never touches storage itself.

    Never raises; a missing/blank field renders as "(none)" / "Not
    recorded" rather than crashing chat setup.
    """
    lines = ["=== HYPOTHESIS TREE ==="]
    flat_hyps = _flatten_hypotheses_for_context(hypotheses_tree)
    if not flat_hyps:
        lines.append("(no hypotheses logged yet)")
    for node, depth in flat_hyps:
        indent = "  " * depth
        state_tag = "dormant" if node.get("state") == "dormant" else "active"
        lines.append(f"{indent}{node.get('label', '?')} [{state_tag}]: {node.get('text', '')}")
    lines.append("")

    lines.append("=== PEOPLE ROSTER ===")
    if not people:
        lines.append("(no interviewee metadata recorded yet)")
    for p in people:
        bits = [p.get("name") or "(unnamed)"]
        role_org = ", ".join(x for x in [p.get("role"), p.get("organization")] if x)
        if role_org:
            bits.append(f"({role_org})")
        rank_branch = ", ".join(x for x in [p.get("rank"), p.get("branch_service")] if x)
        if rank_branch:
            bits.append(f"[{rank_branch}]")
        if p.get("relationship"):
            bits.append(f"relationship: {p['relationship']}")
        if p.get("interview_status"):
            bits.append(f"status: {p['interview_status']}")
        if p.get("interview_date"):
            bits.append(f"date: {p['interview_date']}")
        if p.get("descriptor"):
            bits.append(f"— {p['descriptor']}")
        lines.append("- " + " ".join(bits))
    lines.append("")

    lines.append("=== REFERENCE DOCUMENTS ON FILE ===")
    if not documents:
        lines.append("(none uploaded yet)")
    for d in documents:
        pin = "📌 " if d.get("is_pinned") else ""
        lines.append(f"- {pin}{d.get('title', '(untitled)')}")
    lines.append("")

    lines.append("=== INTERVIEWS ===")
    if not interviews:
        lines.append("(no interviews logged yet)")
    for interview in interviews:
        lines.append("")
        title = interview.get("title", "(untitled)")
        when = interview.get("created_at", "")
        lines.append(f'--- Interview: "{title}" (saved {when}) ---')

        person = interview.get("person")
        if person:
            label = (person.get("name") or "").strip() or "(unnamed)"
            sub = ", ".join(x for x in [person.get("role"), person.get("organization")] if x)
            lines.append(f"Interviewee: {label}" + (f" ({sub})" if sub else ""))
        else:
            lines.append("Interviewee: Not recorded.")

        additional_notes = (interview.get("notes") or "").strip()
        lines.append(
            "Additional notes (nonverbal/context observed by the interviewer, "
            "NOT part of the transcript):"
        )
        lines.append(additional_notes if additional_notes else "(none)")

        lines.append("Raw transcript:")
        lines.append(interview.get("raw_text") or "(empty)")

        runs = interview.get("runs") or []
        if not runs:
            lines.append("(no runs processed for this interview yet)")
        for i, run in enumerate(runs, start=1):
            hyps_display = "; ".join(run.get("hypotheses") or [run.get("hypothesis_text", "")])
            run_when = run.get("created_at", "")
            lines.append("")
            lines.append(f"[Run {i} — {run_when} — hypotheses tested: {hyps_display}]")
            lines.append(render.build_markdown_report(run.get("output") or {}, hyps_display))

    return "\n".join(lines)


def run_chat(
    history: list[dict], user_message: str, api_key: str, corpus_context: str
) -> dict:
    """One chat turn. `history` is every prior turn this session (a list
    of {"role", "content"} dicts, user/assistant alternating — exactly
    the shape the Anthropic API expects, since the caller stores and
    replays this list as-is). `corpus_context` (see build_corpus_context)
    is sent as a cached system block, so later turns in the same session
    don't re-pay its full cost — only its first use, and any explicit
    refresh, cost full price.

    Returns {"reply": str, "history": [...]} — `history` already
    includes this turn (both the user message and the reply), ready to
    pass back in as-is on the next call.
    """
    client = _client(api_key)
    system = [{
        "type": "text",
        "text": f"{CHAT_SYSTEM_INSTRUCTIONS}\n\n{corpus_context}",
        "cache_control": {"type": "ephemeral"},
    }]
    messages = history + [{"role": "user", "content": user_message}]
    response = _call(client, messages=messages, system=system, max_tokens=4096)
    reply = _extract_text(response)
    return {"reply": reply, "history": messages + [{"role": "assistant", "content": reply}]}


# ---------------------------------------------------------------------------
# Hypothesis suggestions — per feedback, hypotheses are never auto-added.
# This proposes candidates for the team to review; nothing reaches
# storage.add_hypothesis unless a person explicitly approves it on the
# Hypotheses page. Based on the same full-corpus context Chat uses (every
# interview's transcript + full analysis + the existing tree), so a
# suggestion is grounded in what the team has actually found, not guessed.
# ---------------------------------------------------------------------------

_HYPOTHESIS_SUGGESTIONS_SYSTEM_PROMPT = (
    "You help a Hacking for Defense (H4D) student team refine their DoD "
    "customer-discovery hypothesis tree, based on everything they've "
    "learned so far. Below is their full existing hypothesis tree and "
    "every interview logged so far (transcripts, additional notes, and "
    "the complete analysis for every run). Propose new candidate "
    "hypotheses worth testing next — a new root-level hypothesis, a "
    "refinement, or a natural child of an existing one (e.g. probing "
    "WHY a validated hypothesis held, or an alternative explanation for "
    "an invalidated one) — each one surfacing a real gap, pattern, or "
    "open question in what the interviews actually show.\n\n"
    "Ground every suggestion in something specific the interviews "
    "actually said; name which interview(s) support it in the "
    "rationale. Never invent a finding that isn't in the material "
    "below — if there isn't enough material yet to responsibly suggest "
    "anything (e.g. no interviews logged yet), return an empty list "
    "rather than guessing. Suggest at most 8. For each one, if it "
    "naturally belongs as a child of an existing hypothesis, give that "
    "hypothesis's exact label (e.g. \"1\" or \"2a\") in "
    "suggested_parent_label; leave it blank for a new root-level "
    "hypothesis."
)

_HYPOTHESIS_SUGGESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "rationale": {"type": "string"},
                    "suggested_parent_label": {"type": "string"},
                },
                "required": ["text", "rationale", "suggested_parent_label"],
                "additionalProperties": False,
            },
            # No "maxItems" — unsupported by Claude's structured-output
            # schema (see CLARIFYING_QUESTIONS_SCHEMA's comment above for
            # the exact 400 this triggers); capped to 8 in code below
            # instead.
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}


def suggest_hypotheses(corpus_context: str, api_key: str) -> list[dict]:
    """Ask the AI to propose new candidate hypotheses, grounded in
    everything logged in the corpus so far (see build_corpus_context).
    NEVER inserts anything into the tree — returns suggestions only, as
    [{"text", "rationale", "suggested_parent_label"}, ...] (at most 8,
    truncated in code, not via the schema); the Hypotheses page shows
    them for review and adds only the ones a person explicitly checks
    and approves, via the normal storage.add_hypothesis.

    Unlike suggest_metadata/_suggest_topics (silent, best-effort
    conveniences that fall back to empty on any failure), this raises
    AIError on failure — it's a primary action the user explicitly
    triggered by clicking a button, so a failure should be visible, not
    swallowed into a quietly-empty suggestion list.
    """
    client = _client(api_key)
    system = f"{_HYPOTHESIS_SUGGESTIONS_SYSTEM_PROMPT}\n\n{corpus_context}"
    response = _call(
        client,
        messages=[{
            "role": "user",
            "content": "Suggest new hypotheses to test next, based on everything above.",
        }],
        system=system,
        schema=_HYPOTHESIS_SUGGESTIONS_SCHEMA,
    )
    data = _extract_json(response)
    return list(data.get("suggestions", []))[:8]
