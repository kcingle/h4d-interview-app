"""
migrate_to_postgres.py — One-time script to copy every row from the local
SQLite database (h4d_app.db) into the new Postgres database, preserving
primary keys exactly (so all the foreign-key relationships — person_id,
interview_id, parent_id — stay valid), then bumping each table's
auto-increment sequence past the highest migrated id.

This is a STANDALONE script, run directly with `python migrate_to_postgres.py`
— it does NOT import storage.py (which, on this branch, is Postgres-only
and would try to connect to Postgres at import time). It talks to SQLite
and Postgres directly, side by side, so nothing here depends on which
backend storage.py currently points at.

Usage (PowerShell):
    $env:DATABASE_URL = "postgresql://user:pass@host/dbname?sslmode=require"
    python migrate_to_postgres.py

Safe to re-run: every INSERT is wrapped so a second run either no-ops
(tables already have rows) or fails loudly rather than silently
duplicating data — see the guard at the top of migrate().
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2

SQLITE_PATH = Path(__file__).parent / "h4d_app.db"


def _sqlite_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _postgres_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: set the DATABASE_URL environment variable first, e.g.")
        print('  $env:DATABASE_URL = "postgresql://user:pass@host/dbname?sslmode=require"')
        sys.exit(1)
    return psycopg2.connect(url)


# Tables in FK-safe insert order: a row's parent (person, interview,
# hypothesis parent) is always inserted before anything that references it.
TABLES_IN_ORDER = ["people", "interviews", "hypotheses", "documents", "runs"]

# Explicit column lists per table (never SELECT/INSERT *), matching the
# CURRENT schema in storage.py exactly.
TABLE_COLUMNS = {
    "people": [
        "id", "name", "role", "organization", "seniority_level", "relationship",
        "interview_date", "descriptor", "rank", "branch_service",
        "interview_status", "created_at",
    ],
    "interviews": ["id", "title", "raw_text", "notes", "person_id", "created_at"],
    "hypotheses": ["id", "statement", "label", "state", "parent_id", "created_at"],
    "documents": ["id", "title", "content", "content_format", "is_pinned", "created_at"],
    "runs": [
        "id", "interview_id", "hypothesis_text", "questions_json", "answers_json",
        "output_json", "digest_json", "document_ids_json", "created_at",
    ],
}


def _row_counts(cur, dialect: str) -> dict:
    counts = {}
    for table in TABLES_IN_ORDER:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        counts[table] = cur.fetchone()[0]
    return counts


def migrate() -> None:
    if not SQLITE_PATH.exists():
        print(f"ERROR: {SQLITE_PATH} not found — nothing to migrate.")
        sys.exit(1)

    sqlite_conn = _sqlite_connection()
    pg_conn = _postgres_connection()

    try:
        sqlite_cur = sqlite_conn.cursor()
        pg_cur = pg_conn.cursor()

        print("=== BEFORE (source: SQLite) ===")
        before_counts = _row_counts(sqlite_cur, "sqlite")
        for table, count in before_counts.items():
            print(f"  {table}: {count}")

        # Safety guard: refuse to run if the Postgres tables already have
        # data, so re-running this script can never silently duplicate rows.
        pg_before = _row_counts(pg_cur, "postgres")
        if any(pg_before.values()):
            print()
            print("ERROR: the Postgres database already has data in it:")
            for table, count in pg_before.items():
                if count:
                    print(f"  {table}: {count} row(s)")
            print("Refusing to migrate into a non-empty database. If this is")
            print("intentional (e.g. re-running after a partial failure), clear")
            print("the target tables first and re-run.")
            sys.exit(1)

        print()
        print("=== Migrating ===")
        for table in TABLES_IN_ORDER:
            columns = TABLE_COLUMNS[table]
            sqlite_cur.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY id ASC")
            rows = sqlite_cur.fetchall()

            placeholders = ", ".join(["%s"] * len(columns))
            insert_sql = (
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
            )
            for row in rows:
                values = [row[col] for col in columns]
                pg_cur.execute(insert_sql, values)

            print(f"  {table}: inserted {len(rows)} row(s)")

            # Bump the SERIAL sequence past the highest migrated id, so the
            # next NEW row this app creates doesn't collide with migrated data.
            pg_cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                f"(SELECT MAX(id) FROM {table}) IS NOT NULL)"
            )

        pg_conn.commit()

        print()
        print("=== AFTER (destination: Postgres) ===")
        after_counts = _row_counts(pg_cur, "postgres")
        all_match = True
        for table in TABLES_IN_ORDER:
            before = before_counts[table]
            after = after_counts[table]
            status = "OK" if before == after else "MISMATCH"
            if before != after:
                all_match = False
            print(f"  {table}: sqlite={before}  postgres={after}  [{status}]")

        print()
        if all_match:
            print("SUCCESS — every table's row count matches exactly.")
        else:
            print("WARNING — row counts do not all match. Investigate before trusting this data.")
            sys.exit(1)

    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    migrate()
