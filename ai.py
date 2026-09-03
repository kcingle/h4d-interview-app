"""
ai.py — All AI/LLM logic lives here and only here. Pages call functions
from this module; they never call an AI API directly. Keeping prompts,
model calls, and response parsing in one place makes them easy to change
together without touching any page.

Step 2: implements the two-step interview processing flow described in
the project plan. Both API calls use `output_config` (structured JSON
outputs) purely as a parsing aid — it lets the app render every result as
a real table without touching a single word of the required system
prompt, which is reproduced verbatim below.
"""

import json

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
    string, unchanged, when no documents are selected (Step 2/3/4
    behavior). When documents ARE selected (Step 5), returns a list of two
    text blocks instead: the untouched system prompt, plus a separate,
    clearly-labeled reference-material block — the prompt string itself is
    never edited.

    NOTE: only documents the user actually checked are sent. If many large
    reference documents are ever selected at once this will grow input
    tokens noticeably — revisit (e.g. summarizing or truncating) if that
    becomes a real cost/context problem.
    """
    if not documents:
        return SYSTEM_PROMPT
    sections = "\n\n".join(f"### {d['title']}\n{d['content']}" for d in documents)
    reference_block = (
        "REFERENCE MATERIAL — background context provided by the team, not "
        "part of the interview. Use it to inform judgment; never quote it or "
        "attribute it to the interviewee.\n\n" + sections
    )
    return [
        {"type": "text", "text": SYSTEM_PROMPT},
        {"type": "text", "text": reference_block},
    ]


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
    hypothesis: str, raw_notes: str, api_key: str, documents: list[dict] | None = None
) -> dict:
    """Step 1: ask up to three clarifying questions about the interview.

    `documents` (Step 5, optional): reference documents to include as
    context — each a dict with at least "title" and "content".

    Returns {"questions": [...], "history": [user_msg, assistant_msg]}.
    `history` is the two-message exchange to replay into run_step2 so the
    conversation stays intact across both steps.
    """
    client = _client(api_key)
    user_content = (
        f"Hypotheses being tested:\n- {hypothesis}\n\n"
        f"Raw interview notes:\n{raw_notes}"
    )
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
    "level; relationship to the problem (must be exactly 'beneficiary', "
    "'adjacent', 'expert', or blank if unclear); and a one-line descriptor "
    "summarizing who they are. Leave any field blank (empty string) rather "
    "than guessing — never invent details the notes don't support."
)

_METADATA_SCHEMA = {
    "type": "object",
    "properties": {
        "name_or_label": {"type": "string"},
        "role": {"type": "string"},
        "organization": {"type": "string"},
        "seniority_level": {"type": "string"},
        "relationship": {"type": "string", "enum": ["", "beneficiary", "adjacent", "expert"]},
        "descriptor": {"type": "string"},
    },
    "required": [
        "name_or_label", "role", "organization", "seniority_level",
        "relationship", "descriptor",
    ],
    "additionalProperties": False,
}

BLANK_METADATA = {
    "name_or_label": "",
    "role": "",
    "organization": "",
    "seniority_level": "",
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
