"""
storage.py — All persistence for the app lives here, behind simple named
functions (save_interview, get_interviews, etc.). Pages should never touch
the database directly.

CLOUD MIGRATION: this is the Postgres-backed version of storage.py (on the
`cloud-migration` branch), replacing the original SQLite implementation so
a shared, hosted deployment can support concurrent multi-user writes and
survive container restarts (SQLite's local file doesn't). Every public
function below keeps the EXACT same name, arguments, and return shape as
the SQLite version (as of master's current commit — this file was just
brought current with 12 commits of feature work: multi-hypothesis,
Additional Notes, interviewers, delete-everywhere, and the Dictionary
feature) — no page, ai.py, or render.py needed to change at all. What
changed is entirely internal: SQL dialect (?, -> %s, SERIAL instead of
AUTOINCREMENT, RETURNING id instead of cur.lastrowid, a small connection
pool instead of a fresh SQLite file handle per call), and the historical
SQLite `_migrate_*`/`_cleanup_*` functions are gone — Postgres starts
directly from the current, already-cleaned final schema shape, since
we're migrating existing *data* (via migrate_to_postgres.py), not
replaying SQLite's own past ALTER TABLE history.

Connection string resolution: reads DATABASE_URL from Streamlit secrets
when running inside a Streamlit app, falling back to the DATABASE_URL
environment variable otherwise (e.g. for the standalone migration script,
or any local non-Streamlit testing).

Row access: every query goes through a RealDictCursor (_dict_cursor), so
a fetched row is already dict-like — `dict(row)` and `row["col"]` both
work exactly like the old sqlite3.Row-based code did. The one exception
is a bare `SELECT COUNT(*)`, which RealDictCursor can't index positionally
(no row[0]) — those are aliased `AS count` and read via row["count"].
"""

import base64
import json
import os
import re
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import psycopg2.pool


def _get_database_url() -> str:
    """Resolve the Postgres connection string: Streamlit secrets first
    (normal app usage), then the DATABASE_URL environment variable
    (standalone scripts, e.g. migrate_to_postgres.py, or local testing
    outside Streamlit)."""
    try:
        import streamlit as st
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "No database connection configured. Set DATABASE_URL in "
            ".streamlit/secrets.toml (local) or the app's Streamlit Cloud "
            "secrets (deployed), or as an environment variable (scripts)."
        )
    return url


_POOL: "psycopg2.pool.ThreadedConnectionPool | None" = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """A small, lazily-created connection pool — reused across calls so
    we're not paying a fresh TCP+TLS handshake to the remote database on
    every single function call, the way a fresh local SQLite file handle
    was effectively free to reopen."""
    global _POOL
    if _POOL is None:
        _POOL = psycopg2.pool.ThreadedConnectionPool(1, 10, _get_database_url())
    return _POOL


def get_connection():
    """Borrow a pooled connection. Callers MUST release it via
    release_connection() in a `finally` block (mirroring the old
    get_connection()/conn.close() shape, just backed by a pool instead of
    a fresh file handle)."""
    return _get_pool().getconn()


def release_connection(conn) -> None:
    _get_pool().putconn(conn)


def _dict_cursor(conn):
    """A cursor whose rows behave like dicts (row["col"]), matching the
    old sqlite3.Row + dict(row) pattern used everywhere in this file."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db() -> None:
    """Create all tables if they don't exist yet. Safe to call repeatedly.
    This is the CURRENT (post schema-cleanup, post-Dictionary-feature)
    shape — no historical ALTER TABLE migrations to replay on Postgres;
    existing SQLite data arrives here via the separate
    migrate_to_postgres.py script instead.

      - interviews: raw interview text/notes, optionally linked to a person.
      - people: interviewee metadata, linked via interviews.person_id.
      - hypotheses: a branching tree (label like 1, 1a, 1b) with an
        active/dormant state.
      - runs: one row per AI processing pass over an interview, so
        reruns against different hypotheses never overwrite history;
        also records which reference documents were used, and the full
        list of hypotheses tested (hypotheses_json).
      - documents: reference docs, incl. a pinned Mom Test doc.
      - dictionary_entries: terms/acronyms saved from Chat's Background &
        Definitions tab.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS people (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT,
                organization TEXT,
                seniority_level TEXT,
                relationship TEXT,
                interview_date TEXT,
                descriptor TEXT,
                rank TEXT,
                branch_service TEXT,
                interview_status TEXT NOT NULL DEFAULT 'completed',
                interviewers_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS interviews (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                notes TEXT,
                person_id INTEGER REFERENCES people (id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS hypotheses (
                id SERIAL PRIMARY KEY,
                statement TEXT NOT NULL,
                label TEXT,
                state TEXT NOT NULL DEFAULT 'active',
                parent_id INTEGER REFERENCES hypotheses (id),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runs (
                id SERIAL PRIMARY KEY,
                interview_id INTEGER NOT NULL REFERENCES interviews (id),
                hypothesis_text TEXT NOT NULL DEFAULT '',
                hypotheses_json TEXT,
                questions_json TEXT,
                answers_json TEXT,
                output_json TEXT,
                digest_json TEXT,
                document_ids_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT,
                content_format TEXT NOT NULL DEFAULT 'text',
                is_pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dictionary_entries (
                id SERIAL PRIMARY KEY,
                term TEXT NOT NULL,
                definition TEXT NOT NULL,
                is_acronym INTEGER NOT NULL DEFAULT 0,
                expansion TEXT,
                is_important INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
        _seed_mom_test_document_if_missing(conn)
        conn.commit()
    finally:
        release_connection(conn)


# --- SEED DATA (pinned Mom Test doc slot) -----------------------------------
# Only fires when no pinned document exists yet; never overwrites existing
# documents. Deliberately the ONE seed kept here — per feedback earlier
# this session, auto-seeding example hypotheses/people was removed
# entirely from master (it kept silently reappearing after a restart);
# this pinned slot is different in kind — it's an empty placeholder you
# fill in yourself on the Documents page, not fabricated example content.
_MOM_TEST_SEED_CONTENT = """\
- Ground every question in the interviewee's actual life and past behavior — not your idea, and not hypotheticals.
- Ask about specific things that already happened ("What's the last time this came up, and what did you do?"), never "Would you..." or "Do you think you'd..."
- Don't pitch, explain, or describe your solution during a discovery interview — you're gathering evidence, not selling.
- Push for specifics: exact dates, tools used, time lost, money spent, workarounds tried. Vague or generic answers aren't evidence.
- Treat enthusiasm and compliments as noise. Look for real commitments — money, time, an introduction, a follow-up meeting — as the actual signal.
- Every claim in an analysis should trace back to something the interviewee actually said or did, never to what they said they would do.
"""

MOM_TEST_TITLE = "The Mom Test (PDF)"


def _seed_mom_test_document_if_missing(conn) -> None:
    cur = _dict_cursor(conn)
    cur.execute("SELECT COUNT(*) AS count FROM documents WHERE is_pinned = 1")
    if cur.fetchone()["count"]:
        return
    cur.execute(
        "INSERT INTO documents (title, content, content_format, is_pinned, created_at) "
        "VALUES (%s, '', 'pdf', 1, %s)",
        (MOM_TEST_TITLE, _now()),
    )


def _now() -> str:
    """ISO-8601 UTC timestamp used for every created_at column."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Interviews
# ---------------------------------------------------------------------------

def save_interview(title: str, raw_text: str, notes: str = "") -> int:
    """Save a new interview and return its new row id."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "INSERT INTO interviews (title, raw_text, notes, created_at) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (title, raw_text, notes, _now()),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        release_connection(conn)


def get_interviews() -> list[dict]:
    """Return all interviews, newest first, as a list of plain dicts."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT id, title, raw_text, notes, person_id, created_at "
            "FROM interviews ORDER BY created_at DESC"
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        release_connection(conn)


def get_interview(interview_id: int) -> dict | None:
    """Return one interview by id, or None if it doesn't exist."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT id, title, raw_text, notes, person_id, created_at "
            "FROM interviews WHERE id = %s",
            (interview_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        release_connection(conn)


def get_person_for_interview(interview_id: int) -> dict | None:
    """Return the person linked to this interview (via
    interviews.person_id), or None if it has no metadata yet. Used by
    Step 7 export to show the interviewee on a run's export header."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            f"SELECT {_PEOPLE_COLUMNS} FROM people WHERE id = "
            "(SELECT person_id FROM interviews WHERE id = %s)",
            (interview_id,),
        )
        row = cur.fetchone()
        return _parse_person_row(row) if row else None
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# Hypotheses
# ---------------------------------------------------------------------------

ALLOWED_HYPOTHESIS_STATES = ("active", "dormant")


class HypothesisError(Exception):
    """Raised when a hypothesis operation is refused — deleting a node
    that still has children. Pages should catch this and show
    st.error(str(e))."""


def _next_root_label(conn) -> str:
    """Next unused integer label among root (family-head) nodes."""
    cur = _dict_cursor(conn)
    cur.execute("SELECT label FROM hypotheses WHERE parent_id IS NULL")
    rows = cur.fetchall()
    used = set()
    for row in rows:
        try:
            used.add(int(row["label"]))
        except (TypeError, ValueError):
            pass
    n = 1
    while n in used:
        n += 1
    return str(n)


def _next_child_label(conn, parent_id: int, parent_label: str) -> str:
    """Next unused single-letter suffix among one parent's direct children
    (falls back to two letters in the unlikely event of >26 siblings)."""
    cur = _dict_cursor(conn)
    cur.execute("SELECT label FROM hypotheses WHERE parent_id = %s", (parent_id,))
    rows = cur.fetchall()
    used_suffixes = set()
    for row in rows:
        lbl = row["label"] or ""
        if lbl.startswith(parent_label):
            suffix = lbl[len(parent_label):]
            if suffix:
                used_suffixes.add(suffix)

    import string

    for letter in string.ascii_lowercase:
        if letter not in used_suffixes:
            return parent_label + letter
    for l1 in string.ascii_lowercase:
        for l2 in string.ascii_lowercase:
            combo = l1 + l2
            if combo not in used_suffixes:
                return parent_label + combo
    return parent_label + str(len(used_suffixes) + 1)  # extremely unlikely fallback


def add_hypothesis(parent_id: int | None, text: str) -> int:
    """Add a new hypothesis node and return its id. The label is computed
    automatically — a new root gets the next unused integer; a new child
    gets its parent's label plus the next unused letter among that
    parent's direct children. New nodes always start "active". Adding a
    child NEVER changes the parent's own state.
    """
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        if parent_id is None:
            label = _next_root_label(conn)
        else:
            cur.execute("SELECT label FROM hypotheses WHERE id = %s", (parent_id,))
            parent = cur.fetchone()
            if parent is None:
                raise ValueError(f"No hypothesis with id {parent_id}")
            label = _next_child_label(conn, parent_id, parent["label"])

        cur.execute(
            "INSERT INTO hypotheses (statement, label, state, parent_id, created_at) "
            "VALUES (%s, %s, 'active', %s, %s) RETURNING id",
            (text, label, parent_id, _now()),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        release_connection(conn)


def get_hypothesis_tree() -> list[dict]:
    """Return every hypothesis as a nested tree: a list of root nodes
    (parent_id IS NULL), each with a "children" list of the same shape,
    sorted by label at every level."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT id, label, statement AS text, state, parent_id, created_at "
            "FROM hypotheses ORDER BY label"
        )
        rows = cur.fetchall()
        nodes = {row["id"]: {**dict(row), "children": []} for row in rows}
        roots = []
        for node in nodes.values():
            parent_id = node["parent_id"]
            parent = nodes.get(parent_id) if parent_id is not None else None
            if parent is not None:
                parent["children"].append(node)
            else:
                roots.append(node)  # true root, or an orphan as a safety net
        return roots
    finally:
        release_connection(conn)


def set_hypothesis_state(hypothesis_id: int, state: str) -> None:
    """Set a node's state to "active" or "dormant". Reviving a dormant
    node is just calling this with "active" again."""
    if state not in ALLOWED_HYPOTHESIS_STATES:
        raise ValueError(f"state must be one of {ALLOWED_HYPOTHESIS_STATES}, got {state!r}")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE hypotheses SET state = %s WHERE id = %s", (state, hypothesis_id))
        conn.commit()
    finally:
        release_connection(conn)


def edit_hypothesis_text(hypothesis_id: int, text: str) -> None:
    """Update a node's hypothesis text in place. Label, state, and parent
    are left untouched."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE hypotheses SET statement = %s WHERE id = %s", (text, hypothesis_id))
        conn.commit()
    finally:
        release_connection(conn)


def delete_hypothesis(hypothesis_id: int) -> None:
    """Permanently delete one hypothesis node. REFUSES if it still has
    children — delete (or reparent, once that exists) those first,
    rather than silently cascading a whole subtree away from one click.
    Runs that tested this hypothesis are unaffected: the hypothesis text
    is stored verbatim on each run, not as a foreign key, so deleting the
    tree node doesn't touch run history — it just stops matching a tree
    node on the Hypothesis Findings/Search & Compare pages."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT COUNT(*) AS count FROM hypotheses WHERE parent_id = %s", (hypothesis_id,)
        )
        children = cur.fetchone()["count"]
        if children:
            raise HypothesisError(
                "This hypothesis still has sub-hypotheses under it — delete those first."
            )
        cur.execute("DELETE FROM hypotheses WHERE id = %s", (hypothesis_id,))
        conn.commit()
    finally:
        release_connection(conn)


def _normalize_hypothesis_text(text: str) -> str:
    """Whitespace/case-normalized form used to match a run's
    hypothesis_text against a tree node's statement. Deliberately exact
    (not fuzzy/substring) — a loose match risks attributing an
    interview's verdict to the wrong hypothesis, which matters more here
    than catching near-miss wording."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _find_digest_entry_for_hypothesis(hyp_entries: list[dict], target_normalized: str) -> dict | None:
    """Find the digest hypothesis-ledger entry that corresponds to a
    specific tested hypothesis (by exact normalized match against the
    entry's own "hypothesis" field — the authoritative tested string,
    present on any digest built after multi-hypothesis support existed).

    Falls back to the single entry when there's only one and no entry
    carries a "hypothesis" field at all — an older, single-hypothesis
    digest built before this field existed, where there's no ambiguity
    to worry about since only one hypothesis was ever tested that run.

    Returns None (never guesses) if neither case applies — e.g. a
    multi-hypothesis run whose ledger entry count doesn't line up with
    what was tested. A caller then correctly treats this as unsupported
    rather than risk attributing the wrong evidence to the wrong claim.
    """
    for entry in hyp_entries:
        entry_hyp = entry.get("hypothesis") or entry.get("claim", "")
        if _normalize_hypothesis_text(entry_hyp) == target_normalized:
            return entry
    if len(hyp_entries) == 1 and "hypothesis" not in hyp_entries[0]:
        return hyp_entries[0]
    return None


def get_hypothesis_status_rollup(hypothesis_statement: str) -> dict:
    """Roll up every interview whose run tested this exact hypothesis
    (matched against the run's full list of tested hypotheses — see
    _normalize_hypothesis_text) using the ALREADY-VERIFIED quotes in each
    run's digest. Pure retrieval/aggregation, no AI call: this never
    synthesizes an interpretation, only organizes what interviews already
    said.

    Returns:
      {
        "counts": {"Validated": n, "Invalidated": n, "Untested": n},
        "quote_backed": [  # verdict has a verified quote
            {"interview_id", "interview_title", "run_id", "status",
             "quotes": [...], "interviewee": {...} | None}, ...
        ],
        "unsupported": [  # verdict exists but NO verified quote —
            # includes matches against an old, pre-enrichment thin digest
            {"interview_id", "interview_title", "run_id", "status",
             "interviewee": {...} | None, "reason": str}, ...
        ],
      }
    """
    target = _normalize_hypothesis_text(hypothesis_statement)
    counts = {"Validated": 0, "Invalidated": 0, "Untested": 0}
    quote_backed = []
    unsupported = []

    for interview in get_interviews():
        person = get_person_for_interview(interview["id"])
        for run in get_runs_for_interview(interview["id"]):
            if target not in {_normalize_hypothesis_text(h) for h in run["hypotheses"]}:
                continue

            digest = run.get("digest") or {}
            base_entry = {
                "interview_id": interview["id"],
                "interview_title": interview["title"],
                "run_id": run["id"],
                "interviewee": person,
            }

            if digest.get("digest_version", 1) < 2:
                # Old thin digest: matched by hypothesis_text but has no
                # quote-anchored per-hypothesis data at all.
                status = digest.get("status", "Untested")
                counts[status] = counts.get(status, 0) + 1
                unsupported.append({
                    **base_entry, "status": status,
                    "reason": "Old digest format — regenerate on the Interviews page for quotes.",
                })
                continue

            hyp_entries = digest.get("hypotheses") or []
            entry = _find_digest_entry_for_hypothesis(hyp_entries, target)
            if entry is None:
                continue  # matched at the run level, but can't confidently
                          # attribute a specific ledger entry -- skip, don't guess
            status = entry.get("status", "Untested")
            quotes = entry.get("quotes") or []
            counts[status] = counts.get(status, 0) + 1

            if quotes:
                quote_backed.append({**base_entry, "status": status, "quotes": quotes})
            else:
                unsupported.append({
                    **base_entry, "status": status,
                    "reason": "Verdict given, but no quote from the notes verified it.",
                })

    return {"counts": counts, "quote_backed": quote_backed, "unsupported": unsupported}


def get_all_topic_tags() -> list[str]:
    """Every distinct topic tag across all digests (only digest_version 2+
    digests carry topics), sorted, for a search page's quick-pick list."""
    tags = set()
    for interview in get_interviews():
        for run in get_runs_for_interview(interview["id"]):
            digest = run.get("digest") or {}
            if digest.get("digest_version", 1) < 2:
                continue
            tags.update(digest.get("topics") or [])
    return sorted(tags)


def search_digests(query: str) -> list[dict]:
    """Keyword/tag search across every interview's digest(s) — plain
    substring matching over digest text and quotes, no semantic search,
    no vector DB (a possible future upgrade, not built here). An item
    matches if `query` appears in its own label/claim text, its quote, OR
    the interview's topic tags include it. claims_to_verify entries are
    excluded — they carry no verbatim quote, and every result here must.

    Returns one entry per matching interview (merged across any reruns),
    each with its own real, de-duplicated quotes — never an invented or
    synthesized passage. An empty/blank query returns [].
    """
    q = (query or "").strip().lower()
    if not q:
        return []

    results = []
    for interview in get_interviews():
        person = get_person_for_interview(interview["id"])
        passages = []
        seen_quotes = set()

        for run in get_runs_for_interview(interview["id"]):
            digest = run.get("digest") or {}
            if digest.get("digest_version", 1) < 2:
                continue  # no structured quote data to search

            topic_match = any(q in (t or "").lower() for t in digest.get("topics") or [])

            candidates = []
            for h in digest.get("hypotheses") or []:
                for quote in h.get("quotes") or []:
                    candidates.append({
                        "kind": "Hypothesis", "label": h.get("claim", ""),
                        "quote": quote, "status": h.get("status"),
                    })
            for p in digest.get("pains") or []:
                if p.get("quote"):
                    candidates.append({
                        "kind": "Pain", "label": p.get("what", ""),
                        "quote": p["quote"], "strength": p.get("strength"),
                    })
            for g in digest.get("gains") or []:
                if g.get("quote"):
                    candidates.append({
                        "kind": "Gain", "label": g.get("what", ""),
                        "quote": g["quote"], "strength": g.get("strength"),
                    })

            for c in candidates:
                text_match = q in c["label"].lower() or q in c["quote"].lower()
                if not (text_match or topic_match):
                    continue
                if c["quote"] in seen_quotes:
                    continue
                seen_quotes.add(c["quote"])
                passages.append({**c, "run_id": run["id"]})

        if passages:
            results.append({
                "interview_id": interview["id"],
                "interview_title": interview["title"],
                "interviewee": person,
                "passages": passages,
            })

    return results


def compare_interviews_on_hypothesis(interview_ids: list[int], hypothesis_statement: str) -> list[dict]:
    """For each interview id, find a run that tested this EXACT hypothesis
    (same normalized-exact matching as get_hypothesis_status_rollup, for
    the same reason: no fuzzy matching, to avoid mis-attributing
    evidence) and return its verdict + verified quotes. An interview
    that never tested it gets tested=False, not an error."""
    target = _normalize_hypothesis_text(hypothesis_statement)
    results = []
    for interview_id in interview_ids:
        interview = get_interview(interview_id)
        person = get_person_for_interview(interview_id)
        match = None
        for run in get_runs_for_interview(interview_id):
            if target not in {_normalize_hypothesis_text(h) for h in run["hypotheses"]}:
                continue
            digest = run.get("digest") or {}
            if digest.get("digest_version", 1) < 2:
                continue
            hyp_entries = digest.get("hypotheses") or []
            match = _find_digest_entry_for_hypothesis(hyp_entries, target)
            if match is not None:
                break
        results.append({
            "interview_id": interview_id,
            "interview_title": interview["title"] if interview else f"Interview #{interview_id}",
            "interviewee": person,
            "tested": match is not None,
            "status": match.get("status") if match else None,
            "quotes": (match.get("quotes") or []) if match else [],
        })
    return results


def compare_interviews_on_topic(interview_ids: list[int], topic: str) -> list[dict]:
    """Same idea as compare_interviews_on_hypothesis but for a topic tag —
    reuses search_digests, filtered to just the selected interviews."""
    by_id = {r["interview_id"]: r for r in search_digests(topic)}
    results = []
    for interview_id in interview_ids:
        if interview_id in by_id:
            results.append(dict(by_id[interview_id]))
            continue
        interview = get_interview(interview_id)
        results.append({
            "interview_id": interview_id,
            "interview_title": interview["title"] if interview else f"Interview #{interview_id}",
            "interviewee": get_person_for_interview(interview_id),
            "passages": [],
        })
    return results


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def save_run(
    interview_id: int,
    hypotheses: list[str],
    questions: list[str],
    answers: list[str],
    output: dict,
    digest: dict,
    document_ids: list[int] | None = None,
) -> int:
    """Save one processing run for an interview and return its new row id.

    Every call INSERTs a new row — reruns never overwrite or replace an
    earlier run. `hypotheses` is the full list of hypotheses tested this
    run (one or more) — stored verbatim (not just referenced), so an old
    run stays meaningful even if a hypothesis's tree wording is edited
    later. `hypothesis_text` (a "; "-joined display string) is kept
    alongside for backward compatibility with anything that just wants a
    single human-readable label — every page that displays it already
    works unchanged for a multi-hypothesis run. `document_ids` records
    which reference documents were included as context for this run —
    provenance for defending which context produced a given analysis.
    """
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "INSERT INTO runs "
            "(interview_id, hypothesis_text, hypotheses_json, questions_json, "
            "answers_json, output_json, digest_json, document_ids_json, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (
                interview_id,
                "; ".join(hypotheses),
                json.dumps(hypotheses),
                json.dumps(questions),
                json.dumps(answers),
                json.dumps(output),
                json.dumps(digest),
                json.dumps(document_ids or []),
                _now(),
            ),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        release_connection(conn)


def get_runs_for_interview(interview_id: int) -> list[dict]:
    """Return every run for one interview, oldest first (so "Run 1", "Run 2"
    labels line up with processing order), with the JSON columns already
    parsed back into Python objects (questions/answers/output/digest/
    document_ids/hypotheses). Runs saved before Step 5 have no
    document_ids_json — those load fine with document_ids == []. Runs
    saved before multi-hypothesis support has no hypotheses_json — those
    load fine with hypotheses == [hypothesis_text] (a one-element list),
    so every run — old or new — has a consistent, matchable list."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT id, interview_id, hypothesis_text, hypotheses_json, questions_json, "
            "answers_json, output_json, digest_json, document_ids_json, created_at "
            "FROM runs WHERE interview_id = %s ORDER BY created_at ASC",
            (interview_id,),
        )
        rows = cur.fetchall()
        runs = []
        for row in rows:
            d = dict(row)
            hypotheses_json = d.pop("hypotheses_json")
            d["hypotheses"] = json.loads(hypotheses_json) if hypotheses_json else [d["hypothesis_text"]]
            d["questions"] = json.loads(d.pop("questions_json") or "[]")
            d["answers"] = json.loads(d.pop("answers_json") or "[]")
            d["output"] = json.loads(d.pop("output_json") or "{}")
            d["digest"] = json.loads(d.pop("digest_json") or "{}")
            d["document_ids"] = json.loads(d.pop("document_ids_json") or "[]")
            runs.append(d)
        return runs
    finally:
        release_connection(conn)


def update_run_digest(run_id: int, digest: dict) -> None:
    """Replace a run's stored digest in place. No schema change needed —
    digest_json has always been a flexible JSON column. Used to backfill
    a run saved before the rich digest existed, to refresh one once
    interviewee metadata is confirmed shortly after a run is first saved,
    or just to regenerate on demand."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE runs SET digest_json = %s WHERE id = %s", (json.dumps(digest), run_id)
        )
        conn.commit()
    finally:
        release_connection(conn)


def delete_interview(interview_id: int) -> None:
    """Permanently delete one interview AND every run it has (there's no
    meaningful "runs of a deleted interview" state to keep). The linked
    person record, if any, is left alone — a person can be linked to
    other interviews and is managed independently on the Metadata page.
    Deletes runs before the interview row itself, since foreign keys are
    enforced and runs.interview_id references interviews.id."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM runs WHERE interview_id = %s", (interview_id,))
        cur.execute("DELETE FROM interviews WHERE id = %s", (interview_id,))
        conn.commit()
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

ALLOWED_INTERVIEW_STATUSES = ("scheduled", "completed", "follow-up needed")

_PEOPLE_COLUMNS = (
    "id, name, role, organization, seniority_level, relationship, "
    "interview_date, descriptor, rank, branch_service, interview_status, "
    "interviewers_json, created_at"
)


def _parse_person_row(row) -> dict:
    """dict(row), with interviewers_json parsed back into a real list —
    every SELECT using _PEOPLE_COLUMNS should go through this rather than
    a bare dict(row), so "interviewers" is always a list, never raw JSON
    text, and old rows with no interviewers_json (before this field
    existed) come back as [] instead of None."""
    d = dict(row)
    d["interviewers"] = json.loads(d.pop("interviewers_json") or "[]")
    return d


def add_person(
    name: str,
    role: str = "",
    organization: str = "",
    seniority_level: str = "",
    relationship: str = "",
    interview_date: str = "",
    descriptor: str = "",
    rank: str = "",
    branch_service: str = "",
    interview_status: str = "completed",
    interviewers: list[str] | None = None,
) -> int:
    """Add a new person and return their id. `interview_status` defaults
    to "completed" — matching the normal case of confirming metadata
    right after finishing that interview's analysis. `interviewers`: up
    to 5 names of who conducted the interview, stored as a JSON array
    (interviewers_json) — a real list, not a delimited string, so
    reading it back is unambiguous even if a name itself contains a
    comma/semicolon. Blank/empty names are dropped; more than 5 is
    truncated, never silently dropping which ones by re-ordering."""
    interviewers = [n.strip() for n in (interviewers or []) if n and n.strip()][:5]
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "INSERT INTO people (name, role, organization, seniority_level, "
            "relationship, interview_date, descriptor, rank, branch_service, "
            "interview_status, interviewers_json, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (name, role, organization, seniority_level, relationship, interview_date,
             descriptor, rank, branch_service, interview_status,
             json.dumps(interviewers), _now()),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        release_connection(conn)


def _attach_interviews(conn, person: dict) -> dict:
    """Attach the list of interviews linked to this person (via
    interviews.person_id), so the Metadata page can show "their
    interview(s) and its runs" — including each one's Additional Notes,
    so that per-interview context shows up alongside this person's
    metadata too — without a separate query per caller."""
    cur = _dict_cursor(conn)
    cur.execute(
        "SELECT id, title, notes, created_at FROM interviews WHERE person_id = %s "
        "ORDER BY created_at ASC",
        (person["id"],),
    )
    person["interviews"] = [dict(row) for row in cur.fetchall()]
    return person


def get_people() -> list[dict]:
    """Return everyone interviewed, newest first, each with their linked
    interview(s) attached as an "interviews" list."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(f"SELECT {_PEOPLE_COLUMNS} FROM people ORDER BY created_at DESC")
        rows = cur.fetchall()
        return [_attach_interviews(conn, _parse_person_row(row)) for row in rows]
    finally:
        release_connection(conn)


def get_person(person_id: int) -> dict | None:
    """Return one person by id (with their linked interviews attached), or
    None if they don't exist."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(f"SELECT {_PEOPLE_COLUMNS} FROM people WHERE id = %s", (person_id,))
        row = cur.fetchone()
        return _attach_interviews(conn, _parse_person_row(row)) if row else None
    finally:
        release_connection(conn)


def update_person(
    person_id: int,
    name: str,
    role: str = "",
    organization: str = "",
    seniority_level: str = "",
    relationship: str = "",
    interview_date: str = "",
    descriptor: str = "",
    rank: str = "",
    branch_service: str = "",
    interview_status: str = "completed",
    interviewers: list[str] | None = None,
) -> None:
    """Update a person's fields in place. Edits made on the Metadata page
    persist via this function. See add_person for `interviewers`'
    format/limits."""
    interviewers = [n.strip() for n in (interviewers or []) if n and n.strip()][:5]
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE people SET name = %s, role = %s, organization = %s, "
            "seniority_level = %s, relationship = %s, interview_date = %s, "
            "descriptor = %s, rank = %s, branch_service = %s, interview_status = %s, "
            "interviewers_json = %s WHERE id = %s",
            (name, role, organization, seniority_level, relationship, interview_date,
             descriptor, rank, branch_service, interview_status,
             json.dumps(interviewers), person_id),
        )
        conn.commit()
    finally:
        release_connection(conn)


def set_interview_person(interview_id: int, person_id: int) -> None:
    """Link an interview to a person (sets interviews.person_id)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE interviews SET person_id = %s WHERE id = %s", (person_id, interview_id)
        )
        conn.commit()
    finally:
        release_connection(conn)


def delete_person(person_id: int) -> None:
    """Permanently delete one person. Any interview(s) linked to them
    have their person_id cleared back to "not recorded" first (foreign
    keys are enforced) — the interview itself, and its runs, are never
    touched by deleting a person."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE interviews SET person_id = NULL WHERE person_id = %s", (person_id,))
        cur.execute("DELETE FROM people WHERE id = %s", (person_id,))
        conn.commit()
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

class DocumentError(Exception):
    """Raised when a document operation is refused — editing or deleting a
    pinned document. Pages should catch this and show st.error(str(e))."""


def _encode_document_content(content, content_format: str) -> str:
    """PDF content arrives as raw bytes; base64-encode for TEXT-column
    storage. Text content is already a str — stored as-is."""
    if content_format == "pdf":
        return base64.standard_b64encode(content or b"").decode("utf-8")
    return content


def _decode_document_row(row: dict) -> dict:
    """Inverse of _encode_document_content — callers always get natural
    types back: bytes for a PDF document, str for a text one."""
    if row.get("content_format") == "pdf":
        row["content"] = base64.standard_b64decode(row["content"] or "")
    return row


def add_document(
    title: str, content, is_pinned: bool = False, content_format: str = "text"
) -> int:
    """Add a new document and return its id. `content` is a plain str
    for content_format="text", or raw PDF bytes for content_format="pdf"
    (encoded for storage automatically)."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "INSERT INTO documents (title, content, content_format, is_pinned, created_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (title, _encode_document_content(content, content_format), content_format,
             1 if is_pinned else 0, _now()),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        release_connection(conn)


def get_documents() -> list[dict]:
    """Return all documents, pinned first, then newest first. Each dict's
    "content" is bytes for a PDF document, str for a text one."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT id, title, content, content_format, is_pinned, created_at FROM documents "
            "ORDER BY is_pinned DESC, created_at DESC"
        )
        return [_decode_document_row(dict(row)) for row in cur.fetchall()]
    finally:
        release_connection(conn)


def get_document_titles(document_ids: list[int]) -> list[str]:
    """Resolve a run's stored document_ids to titles, for the Step 7
    export header. A document deleted since the run was saved still shows
    (as "Document #N (deleted)") rather than silently vanishing from the
    provenance record."""
    titles = []
    for doc_id in document_ids:
        doc = get_document(doc_id)
        titles.append(doc["title"] if doc else f"Document #{doc_id} (deleted)")
    return titles


def get_document(document_id: int) -> dict | None:
    """Return one document by id, or None if it doesn't exist. "content"
    is bytes for a PDF document, str for a text one."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT id, title, content, content_format, is_pinned, created_at "
            "FROM documents WHERE id = %s",
            (document_id,),
        )
        row = cur.fetchone()
        return _decode_document_row(dict(row)) if row else None
    finally:
        release_connection(conn)


def update_document(document_id: int, title: str, content: str) -> None:
    """Update a TEXT document's title/content. REFUSES on a pinned
    document — the Mom Test slot is viewable but not editable this way,
    since it's the graded standard and sent as context on every analysis.
    Not used for PDF documents — there's no text to type into a box for
    those; see replace_document_pdf() for how a PDF's content changes."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute("SELECT is_pinned FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
        if row is None:
            raise DocumentError(f"No document with id {document_id}")
        if row["is_pinned"]:
            raise DocumentError("Pinned documents cannot be edited.")
        cur.execute(
            "UPDATE documents SET title = %s, content = %s WHERE id = %s",
            (title, content, document_id),
        )
        conn.commit()
    finally:
        release_connection(conn)


def replace_document_pdf(document_id: int, pdf_content: bytes) -> None:
    """Replace a document's PDF content in place (content_format is set
    to "pdf" regardless of what it was before). Deliberately bypasses the
    pinned-edit restriction that update_document enforces — for a PDF,
    re-uploading a new file IS the edit; there's no text box to type
    into. This is how the pinned Mom Test slot is first populated and
    later replaced, and works the same way on a non-pinned document."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute("SELECT id FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
        if row is None:
            raise DocumentError(f"No document with id {document_id}")
        cur.execute(
            "UPDATE documents SET content = %s, content_format = 'pdf' WHERE id = %s",
            (_encode_document_content(pdf_content, "pdf"), document_id),
        )
        conn.commit()
    finally:
        release_connection(conn)


def delete_document(document_id: int) -> None:
    """Delete a document. REFUSES on a pinned document — this is the
    backstop even though the UI also hides the delete control for pinned
    documents."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute("SELECT is_pinned FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
        if row is None:
            return  # already gone; nothing to do
        if row["is_pinned"]:
            raise DocumentError("Pinned documents cannot be deleted.")
        cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))
        conn.commit()
    finally:
        release_connection(conn)


# ---------------------------------------------------------------------------
# Dictionary — terms/acronyms/concepts explained via Chat's "Background &
# Definitions" mode (see ai.define_terms), saved here only when a person
# explicitly clicks "Add to dictionary" — never automatically.
# ---------------------------------------------------------------------------

def add_dictionary_entry(
    term: str, definition: str, is_acronym: bool = False, expansion: str = ""
) -> int:
    """Add one dictionary entry and return its id. `expansion` is the
    spelled-out form of an acronym (e.g. "Offensive Counter Air" for
    "OCA") — meaningless when `is_acronym` is False, so callers should
    leave it blank then."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "INSERT INTO dictionary_entries "
            "(term, definition, is_acronym, expansion, is_important, created_at) "
            "VALUES (%s, %s, %s, %s, 0, %s) RETURNING id",
            (term.strip(), definition.strip(), int(bool(is_acronym)), expansion.strip(), _now()),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return new_id
    finally:
        release_connection(conn)


def get_dictionary_entries() -> list[dict]:
    """Return every dictionary entry, most important first, then newest
    first — so marking a term important actually surfaces it, rather
    than just tagging it in place. Filtering/search happens page-side
    (same convention as the Metadata page's filters) — this always
    returns the full list."""
    conn = get_connection()
    try:
        cur = _dict_cursor(conn)
        cur.execute(
            "SELECT id, term, definition, is_acronym, expansion, is_important, created_at "
            "FROM dictionary_entries ORDER BY is_important DESC, created_at DESC"
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        release_connection(conn)


def set_dictionary_importance(entry_id: int, important: bool) -> None:
    """Mark (or unmark) one entry as high-importance."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dictionary_entries SET is_important = %s WHERE id = %s",
            (int(bool(important)), entry_id),
        )
        conn.commit()
    finally:
        release_connection(conn)


def delete_dictionary_entry(entry_id: int) -> None:
    """Permanently delete one dictionary entry."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dictionary_entries WHERE id = %s", (entry_id,))
        conn.commit()
    finally:
        release_connection(conn)


# Make sure the database and tables exist as soon as this module is
# imported, no matter which page Streamlit happens to load first.
init_db()
