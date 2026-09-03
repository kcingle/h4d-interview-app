"""
storage.py — All persistence for the app lives here, behind simple named
functions (save_interview, get_interviews, etc.). Pages should never touch
SQLite directly; if we later swap to a hosted database, only this file
should need to change.

Through Step 6: interviews, runs (with rerun history + document/hypothesis
provenance), the hypothesis tree, documents (incl. the pinned Mom Test
doc), and people/metadata are all fully real. Every schema change so far
has been an additive migration — see the `_migrate_*` functions below.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent / "h4d_app.db"


def get_connection() -> sqlite3.Connection:
    """Open a new SQLite connection with foreign keys enabled and rows
    returned as dict-like objects (sqlite3.Row)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all tables if they don't exist yet. Safe to call repeatedly.

      - interviews: raw interview text/notes, optionally linked to a person.
      - people: interviewee metadata (Step 6), linked via interviews.person_id.
      - hypotheses: a branching tree (label like 1, 1a, 1b) with an
        active/dormant state (Step 4).
      - runs: one row per AI processing pass over an interview, so
        reruns against different hypotheses never overwrite history (Step 3);
        also records which reference documents were used (Step 5).
      - documents: reference docs, incl. a pinned Mom Test doc (Step 5).

    This is the CURRENT (post schema-cleanup) shape, used as-is for a
    brand-new database. An existing database created before the cleanup
    is brought to this same shape by _cleanup_dead_schema_v1() below —
    see that function for what was removed and why.
    """
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT,
                organization TEXT,
                seniority_level TEXT,
                relationship TEXT,
                interview_date TEXT,
                descriptor TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS interviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                notes TEXT,
                person_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (person_id) REFERENCES people (id)
            );

            CREATE TABLE IF NOT EXISTS hypotheses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                statement TEXT NOT NULL,
                label TEXT,
                state TEXT NOT NULL DEFAULT 'active',
                parent_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES hypotheses (id)
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interview_id INTEGER NOT NULL,
                hypothesis_text TEXT NOT NULL DEFAULT '',
                questions_json TEXT,
                answers_json TEXT,
                output_json TEXT,
                digest_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (interview_id) REFERENCES interviews (id)
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        _migrate_runs_table(conn)
        _migrate_hypotheses_table(conn)
        _migrate_people_table(conn)
        _cleanup_dead_schema_v1(conn)
        _seed_hypotheses_if_empty(conn)
        _seed_mom_test_document_if_missing(conn)
        _seed_people_if_empty(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate_runs_table(conn: sqlite3.Connection) -> None:
    """Add Step 3's new `runs` columns to a database created before Step 3
    existed. A no-op on a fresh database, where CREATE TABLE already
    included them. Never touches existing rows' other data."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
    migrations = {
        "hypothesis_text": "ALTER TABLE runs ADD COLUMN hypothesis_text TEXT NOT NULL DEFAULT ''",
        "questions_json": "ALTER TABLE runs ADD COLUMN questions_json TEXT",
        "answers_json": "ALTER TABLE runs ADD COLUMN answers_json TEXT",
        "digest_json": "ALTER TABLE runs ADD COLUMN digest_json TEXT",
        "document_ids_json": "ALTER TABLE runs ADD COLUMN document_ids_json TEXT",
    }
    for column, ddl in migrations.items():
        if column not in existing:
            conn.execute(ddl)


def _migrate_hypotheses_table(conn: sqlite3.Connection) -> None:
    """Add Step 4's new `hypotheses` columns (`label`, `state`) to a
    database created before Step 4 existed. A no-op on a fresh database,
    where CREATE TABLE already included them. (The old `family`,
    `version`, and `is_active_for_testing` columns this docstring used to
    mention here were removed entirely by the schema cleanup — see
    _cleanup_dead_schema_v1 below.)"""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(hypotheses)")}
    migrations = {
        "label": "ALTER TABLE hypotheses ADD COLUMN label TEXT",
        "state": "ALTER TABLE hypotheses ADD COLUMN state TEXT NOT NULL DEFAULT 'active'",
    }
    for column, ddl in migrations.items():
        if column not in existing:
            conn.execute(ddl)


# --- SEED DATA (Step 4 demo tree) -------------------------------------------
# Delete this function and its call above to remove the seed tree entirely.
# It only ever fires when the hypotheses table is completely empty, and
# never overwrites or touches existing hypotheses.
def _seed_hypotheses_if_empty(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0]
    if count:
        return

    def insert(parent_id, label, text, state):
        conn.execute(
            "INSERT INTO hypotheses (statement, label, state, parent_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (text, label, state, parent_id, _now()),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    root1 = insert(
        None, "1",
        "Dismounted patrol units in comms-denied environments lose more than "
        "15 minutes per mission re-establishing position after GPS-denial events.",
        "active",
    )
    insert(
        root1, "1a",
        "Dismounted patrol units in comms-denied environments would adopt a "
        "low-cost inertial+visual dead-reckoning aid that requires no network "
        "connectivity.",
        "active",
    )
    insert(
        root1, "1b",
        "Dismounted patrol units in comms-denied environments would adopt a "
        "solution requiring periodic satellite check-ins every 30 minutes.",
        "dormant",
    )

    root2 = insert(
        None, "2",
        "Small unit leaders cannot verify subordinate element positions during "
        "comms-denied operations without physically consolidating the formation.",
        "active",
    )
    insert(
        root2, "2a",
        "Small unit leaders would adopt a peer-to-peer mesh position-sharing "
        "capability that operates without external infrastructure, even during "
        "comms-denied operations.",
        "active",
    )

    insert(
        None, "3",
        "Route planners preparing for comms-denied operations lack a reliable "
        "way to pre-stage waypoints that account for terrain-masking of "
        "degraded PNT signals.",
        "dormant",
    )


# --- SEED DATA (Step 5 pinned Mom Test doc) ---------------------------------
# Only fires when no pinned document exists yet; never overwrites existing
# documents. This is an original plain-language summary, not the book's text.
_MOM_TEST_SEED_CONTENT = """\
- Ground every question in the interviewee's actual life and past behavior — not your idea, and not hypotheticals.
- Ask about specific things that already happened ("What's the last time this came up, and what did you do?"), never "Would you..." or "Do you think you'd..."
- Don't pitch, explain, or describe your solution during a discovery interview — you're gathering evidence, not selling.
- Push for specifics: exact dates, tools used, time lost, money spent, workarounds tried. Vague or generic answers aren't evidence.
- Treat enthusiasm and compliments as noise. Look for real commitments — money, time, an introduction, a follow-up meeting — as the actual signal.
- Every claim in an analysis should trace back to something the interviewee actually said or did, never to what they said they would do.
"""


def _seed_mom_test_document_if_missing(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM documents WHERE is_pinned = 1").fetchone()[0]
    if count:
        return
    conn.execute(
        "INSERT INTO documents (title, content, is_pinned, created_at) VALUES (?, ?, 1, ?)",
        ("The Mom Test (principles)", _MOM_TEST_SEED_CONTENT, _now()),
    )


def _migrate_people_table(conn: sqlite3.Connection) -> None:
    """Add Step 6's new `people` columns to a database created before Step
    6 existed. A no-op on a fresh database. (The old `email`/`notes`
    columns this docstring used to mention here were removed entirely by
    the schema cleanup — see _cleanup_dead_schema_v1 below.)"""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(people)")}
    migrations = {
        "seniority_level": "ALTER TABLE people ADD COLUMN seniority_level TEXT",
        "relationship": "ALTER TABLE people ADD COLUMN relationship TEXT",
        "interview_date": "ALTER TABLE people ADD COLUMN interview_date TEXT",
        "descriptor": "ALTER TABLE people ADD COLUMN descriptor TEXT",
    }
    for column, ddl in migrations.items():
        if column not in existing:
            conn.execute(ddl)


def _cleanup_dead_schema_v1(conn: sqlite3.Connection) -> None:
    """One-time removal of columns/tables that were part of an earlier
    step's provisional schema but were never read or written by any code:
    hypotheses.family/version/is_active_for_testing, people.email/notes,
    documents.doc_type, and the run_hypotheses table (never populated —
    no code ever inserted into, selected from, or joined against it).

    Idempotent: each check looks for the dead column/table's presence
    before acting, so this is a no-op on a database that's already been
    cleaned, or one created fresh after this cleanup existed (its CREATE
    TABLE statements above never included these in the first place).

    SQLite (as used here, via Python's bundled sqlite3 module) has no
    DROP COLUMN, so each affected table is recreated with the trimmed
    column set: every surviving row is copied across by explicit column
    name (never SELECT *, never by position), the old table is dropped,
    and the new one is renamed into place. `id` is always carried
    forward unchanged, so parent_id/person_id references elsewhere stay
    valid, and SQLite's ALTER TABLE RENAME automatically updates other
    tables' FOREIGN KEY clauses that pointed to the old table name.
    """
    hyp_columns = {row["name"] for row in conn.execute("PRAGMA table_info(hypotheses)")}
    if {"family", "version", "is_active_for_testing"} & hyp_columns:
        conn.executescript(
            """
            CREATE TABLE hypotheses_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                statement TEXT NOT NULL,
                label TEXT,
                state TEXT NOT NULL DEFAULT 'active',
                parent_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES hypotheses_new (id)
            );
            INSERT INTO hypotheses_new (id, statement, label, state, parent_id, created_at)
                SELECT id, statement, label, state, parent_id, created_at FROM hypotheses;
            DROP TABLE hypotheses;
            ALTER TABLE hypotheses_new RENAME TO hypotheses;
            """
        )

    people_columns = {row["name"] for row in conn.execute("PRAGMA table_info(people)")}
    if {"email", "notes"} & people_columns:
        conn.executescript(
            """
            CREATE TABLE people_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT,
                organization TEXT,
                seniority_level TEXT,
                relationship TEXT,
                interview_date TEXT,
                descriptor TEXT,
                created_at TEXT NOT NULL
            );
            INSERT INTO people_new (id, name, role, organization, seniority_level,
                relationship, interview_date, descriptor, created_at)
                SELECT id, name, role, organization, seniority_level,
                    relationship, interview_date, descriptor, created_at FROM people;
            DROP TABLE people;
            ALTER TABLE people_new RENAME TO people;
            """
        )

    doc_columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)")}
    if "doc_type" in doc_columns:
        conn.executescript(
            """
            CREATE TABLE documents_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            INSERT INTO documents_new (id, title, content, is_pinned, created_at)
                SELECT id, title, content, is_pinned, created_at FROM documents;
            DROP TABLE documents;
            ALTER TABLE documents_new RENAME TO documents;
            """
        )

    run_hyp_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'run_hypotheses'"
    ).fetchone()
    if run_hyp_exists:
        conn.execute("DROP TABLE run_hypotheses")


# --- SEED DATA (Step 6 demo people) -----------------------------------------
# Only fires when the people table is completely empty; never overwrites
# existing people. These are standalone example rows, NOT linked to any
# real interview (their names are tagged "(example)" so they're obvious),
# thematically matching the Step 4 seed hypothesis tree's scenario.
def _seed_people_if_empty(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
    if count:
        return

    def insert(name, role, organization, seniority_level, relationship, descriptor):
        conn.execute(
            "INSERT INTO people (name, role, organization, seniority_level, "
            "relationship, interview_date, descriptor, created_at) "
            "VALUES (?, ?, ?, ?, ?, '', ?, ?)",
            (name, role, organization, seniority_level, relationship, descriptor, _now()),
        )

    insert(
        "Dismounted Squad Leader (example)",
        "Squad Leader",
        "Notional Infantry Battalion",
        "NCO",
        "beneficiary",
        "Leads dismounted patrols that lose GPS in contested terrain — example seed data.",
    )
    insert(
        "Route Planning Officer (example)",
        "Route Planner",
        "Notional Brigade S3",
        "Company-grade officer",
        "adjacent",
        "Plans routes accounting for comms-denied navigation risk — example seed data.",
    )


def _now() -> str:
    """ISO-8601 UTC timestamp used for every created_at column."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Interviews — real, working (Step 1)
# ---------------------------------------------------------------------------

def save_interview(title: str, raw_text: str, notes: str = "") -> int:
    """Save a new interview and return its new row id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO interviews (title, raw_text, notes, created_at) "
            "VALUES (?, ?, ?, ?)",
            (title, raw_text, notes, _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_interviews() -> list[dict]:
    """Return all interviews, newest first, as a list of plain dicts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, raw_text, notes, person_id, created_at "
            "FROM interviews ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_interview(interview_id: int) -> dict | None:
    """Return one interview by id, or None if it doesn't exist."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, title, raw_text, notes, person_id, created_at "
            "FROM interviews WHERE id = ?",
            (interview_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_person_for_interview(interview_id: int) -> dict | None:
    """Return the person linked to this interview (via
    interviews.person_id), or None if it has no metadata yet. Used by
    Step 7 export to show the interviewee on a run's export header."""
    conn = get_connection()
    try:
        row = conn.execute(
            f"SELECT {_PEOPLE_COLUMNS} FROM people WHERE id = "
            "(SELECT person_id FROM interviews WHERE id = ?)",
            (interview_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Hypotheses — real, working (Step 4)
# ---------------------------------------------------------------------------

ALLOWED_HYPOTHESIS_STATES = ("active", "dormant")


def _next_root_label(conn: sqlite3.Connection) -> str:
    """Next unused integer label among root (family-head) nodes."""
    rows = conn.execute("SELECT label FROM hypotheses WHERE parent_id IS NULL").fetchall()
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


def _next_child_label(conn: sqlite3.Connection, parent_id: int, parent_label: str) -> str:
    """Next unused single-letter suffix among one parent's direct children
    (falls back to two letters in the unlikely event of >26 siblings)."""
    rows = conn.execute("SELECT label FROM hypotheses WHERE parent_id = ?", (parent_id,)).fetchall()
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
        if parent_id is None:
            label = _next_root_label(conn)
        else:
            parent = conn.execute(
                "SELECT label FROM hypotheses WHERE id = ?", (parent_id,)
            ).fetchone()
            if parent is None:
                raise ValueError(f"No hypothesis with id {parent_id}")
            label = _next_child_label(conn, parent_id, parent["label"])

        cur = conn.execute(
            "INSERT INTO hypotheses (statement, label, state, parent_id, created_at) "
            "VALUES (?, ?, 'active', ?, ?)",
            (text, label, parent_id, _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_hypothesis_tree() -> list[dict]:
    """Return every hypothesis as a nested tree: a list of root nodes
    (parent_id IS NULL), each with a "children" list of the same shape,
    sorted by label at every level."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, label, statement AS text, state, parent_id, created_at "
            "FROM hypotheses ORDER BY label"
        ).fetchall()
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
        conn.close()


def set_hypothesis_state(hypothesis_id: int, state: str) -> None:
    """Set a node's state to "active" or "dormant". Reviving a dormant
    node is just calling this with "active" again."""
    if state not in ALLOWED_HYPOTHESIS_STATES:
        raise ValueError(f"state must be one of {ALLOWED_HYPOTHESIS_STATES}, got {state!r}")
    conn = get_connection()
    try:
        conn.execute("UPDATE hypotheses SET state = ? WHERE id = ?", (state, hypothesis_id))
        conn.commit()
    finally:
        conn.close()


def edit_hypothesis_text(hypothesis_id: int, text: str) -> None:
    """Update a node's hypothesis text in place. Label, state, and parent
    are left untouched."""
    conn = get_connection()
    try:
        conn.execute("UPDATE hypotheses SET statement = ? WHERE id = ?", (text, hypothesis_id))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Runs — real, working (Step 3)
# ---------------------------------------------------------------------------

def save_run(
    interview_id: int,
    hypothesis_text: str,
    questions: list[str],
    answers: list[str],
    output: dict,
    digest: dict,
    document_ids: list[int] | None = None,
) -> int:
    """Save one processing run for an interview and return its new row id.

    Every call INSERTs a new row — reruns never overwrite or replace an
    earlier run. The hypothesis text is stored verbatim on the run itself
    (not just referenced), so an old run stays meaningful even if the
    hypothesis wording is edited later. `document_ids` records which
    reference documents (Step 5) were included as context for this run —
    provenance for defending which context produced a given analysis.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO runs "
            "(interview_id, hypothesis_text, questions_json, answers_json, "
            "output_json, digest_json, document_ids_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                interview_id,
                hypothesis_text,
                json.dumps(questions),
                json.dumps(answers),
                json.dumps(output),
                json.dumps(digest),
                json.dumps(document_ids or []),
                _now(),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_runs_for_interview(interview_id: int) -> list[dict]:
    """Return every run for one interview, oldest first (so "Run 1", "Run 2"
    labels line up with processing order), with the JSON columns already
    parsed back into Python objects (questions/answers/output/digest/
    document_ids). Runs saved before Step 5 have no document_ids_json —
    those load fine with document_ids == []."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, interview_id, hypothesis_text, questions_json, "
            "answers_json, output_json, digest_json, document_ids_json, created_at "
            "FROM runs WHERE interview_id = ? ORDER BY created_at ASC",
            (interview_id,),
        ).fetchall()
        runs = []
        for row in rows:
            d = dict(row)
            d["questions"] = json.loads(d.pop("questions_json") or "[]")
            d["answers"] = json.loads(d.pop("answers_json") or "[]")
            d["output"] = json.loads(d.pop("output_json") or "{}")
            d["digest"] = json.loads(d.pop("digest_json") or "{}")
            d["document_ids"] = json.loads(d.pop("document_ids_json") or "[]")
            runs.append(d)
        return runs
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# People — real, working (Step 6)
# ---------------------------------------------------------------------------

_PEOPLE_COLUMNS = (
    "id, name, role, organization, seniority_level, relationship, "
    "interview_date, descriptor, created_at"
)


def add_person(
    name: str,
    role: str = "",
    organization: str = "",
    seniority_level: str = "",
    relationship: str = "",
    interview_date: str = "",
    descriptor: str = "",
) -> int:
    """Add a new person and return their id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO people (name, role, organization, seniority_level, "
            "relationship, interview_date, descriptor, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (name, role, organization, seniority_level, relationship, interview_date,
             descriptor, _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _attach_interviews(conn: sqlite3.Connection, person: dict) -> dict:
    """Attach the list of interviews linked to this person (via
    interviews.person_id), so the People page can show "their interview(s)
    and its runs" without a separate query per caller."""
    rows = conn.execute(
        "SELECT id, title, created_at FROM interviews WHERE person_id = ? "
        "ORDER BY created_at ASC",
        (person["id"],),
    ).fetchall()
    person["interviews"] = [dict(row) for row in rows]
    return person


def get_people() -> list[dict]:
    """Return everyone interviewed, newest first, each with their linked
    interview(s) attached as an "interviews" list."""
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT {_PEOPLE_COLUMNS} FROM people ORDER BY created_at DESC"
        ).fetchall()
        return [_attach_interviews(conn, dict(row)) for row in rows]
    finally:
        conn.close()


def get_person(person_id: int) -> dict | None:
    """Return one person by id (with their linked interviews attached), or
    None if they don't exist."""
    conn = get_connection()
    try:
        row = conn.execute(
            f"SELECT {_PEOPLE_COLUMNS} FROM people WHERE id = ?", (person_id,)
        ).fetchone()
        return _attach_interviews(conn, dict(row)) if row else None
    finally:
        conn.close()


def update_person(
    person_id: int,
    name: str,
    role: str = "",
    organization: str = "",
    seniority_level: str = "",
    relationship: str = "",
    interview_date: str = "",
    descriptor: str = "",
) -> None:
    """Update a person's fields in place. Edits made on the People page
    persist via this function."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE people SET name = ?, role = ?, organization = ?, "
            "seniority_level = ?, relationship = ?, interview_date = ?, "
            "descriptor = ? WHERE id = ?",
            (name, role, organization, seniority_level, relationship, interview_date,
             descriptor, person_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_interview_person(interview_id: int, person_id: int) -> None:
    """Link an interview to a person (sets interviews.person_id)."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE interviews SET person_id = ? WHERE id = ?", (person_id, interview_id)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Documents — real, working (Step 5)
# ---------------------------------------------------------------------------

class DocumentError(Exception):
    """Raised when a document operation is refused — editing or deleting a
    pinned document. Pages should catch this and show st.error(str(e))."""


def add_document(title: str, content: str, is_pinned: bool = False) -> int:
    """Add a new document and return its id."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO documents (title, content, is_pinned, created_at) "
            "VALUES (?, ?, ?, ?)",
            (title, content, 1 if is_pinned else 0, _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_documents() -> list[dict]:
    """Return all documents, pinned first, then newest first."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, content, is_pinned, created_at FROM documents "
            "ORDER BY is_pinned DESC, created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


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
    """Return one document by id, or None if it doesn't exist."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, title, content, is_pinned, created_at FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_document(document_id: int, title: str, content: str) -> None:
    """Update a document's title/content. REFUSES on a pinned document —
    the Mom Test doc is viewable but not editable, since it's the graded
    standard and sent as context on every analysis."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT is_pinned FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            raise DocumentError(f"No document with id {document_id}")
        if row["is_pinned"]:
            raise DocumentError("Pinned documents cannot be edited.")
        conn.execute(
            "UPDATE documents SET title = ?, content = ? WHERE id = ?",
            (title, content, document_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_document(document_id: int) -> None:
    """Delete a document. REFUSES on a pinned document — this is the
    backstop even though the UI also hides the delete control for pinned
    documents."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT is_pinned FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            return  # already gone; nothing to do
        if row["is_pinned"]:
            raise DocumentError("Pinned documents cannot be deleted.")
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        conn.commit()
    finally:
        conn.close()


# Make sure the database and tables exist as soon as this module is
# imported, no matter which page Streamlit happens to load first.
init_db()
