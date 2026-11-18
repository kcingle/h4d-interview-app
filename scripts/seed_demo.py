"""
scripts/seed_demo.py — Fill (or reset) the DEMO database with the made-up
interviews in demo/seed_content.py, processed through this app's own AI
pipeline exactly like Process Interview does, then check every quote in
every output word for word against its transcript.

SAFETY. This script can only ever touch the demo database:
  * It never reads .streamlit/secrets.toml for its connection. It takes
    the demo URL from a file you name, and changes into an empty folder
    before loading the app, so Streamlit secrets (which would otherwise
    win over DATABASE_URL) can't redirect it to the live database.
  * It prints the host and database it is about to use and stops unless
    the host matches --expect-host exactly.
  * It refuses any host that matches the live database recorded in the
    repo's secrets (or its secrets.live.toml.bak backup).

Usage (Windows, from the repo folder):

    venv\\Scripts\\python scripts\\seed_demo.py --url-file C:\\Users\\katei\\h4d-secrets\\demo_database_url.txt --expect-host <demo host> --reset

--reset wipes every app table in the DEMO database and re-seeds it. Without
--reset, the script refuses to run on a database that already has data.
--export-docx <key> also writes that seed interview's Word report.
"""

import argparse
import os
import sys
import tempfile
import time
import tomllib
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LIVE_SECRET_FILES = [
    REPO / ".streamlit" / "secrets.toml",
    Path.home() / "h4d-secrets" / "secrets.live.toml.bak",
]
APP_TABLES = (
    "visual_resources", "runs", "interview_people", "interviews", "people",
    "hypotheses", "documents", "dictionary_entries",
)


def _endpoint(host: str) -> str:
    """Neon endpoint id, ignoring the -pooler suffix."""
    return (host or "").split(".")[0].replace("-pooler", "")


def guard(url_file: str, expect_host: str) -> str:
    url = Path(url_file).read_text(encoding="utf-8").strip()
    parsed = urllib.parse.urlparse(url)
    host, db = parsed.hostname or "", parsed.path.lstrip("/")
    print(f"About to connect to: host={host}  database={db}")
    if host != expect_host:
        sys.exit(f"STOP: host {host!r} is not the expected demo host {expect_host!r}.")
    live_hosts = set()
    for f in LIVE_SECRET_FILES:
        if f.exists():
            try:
                live = tomllib.loads(f.read_text(encoding="utf-8")).get("DATABASE_URL", "")
            except Exception:
                continue
            live_host = urllib.parse.urlparse(live).hostname or ""
            # The repo secrets file may itself point at the demo database
            # during demo work; only the backup is authoritative then.
            if f.name == "secrets.toml" and (Path.home() / "h4d-secrets" / "secrets.live.toml.bak").exists():
                continue
            live_hosts.add(_endpoint(live_host))
    if _endpoint(host) in live_hosts:
        sys.exit("STOP: that host is the LIVE database. Refusing to continue.")
    if not live_hosts:
        sys.exit("STOP: couldn't find the live database's host to rule it out.")
    print("Confirmed: demo host, and not the live database.")
    return url


def connect_app(url: str):
    """Load the app's modules against `url` only."""
    os.environ["DATABASE_URL"] = url
    os.chdir(tempfile.mkdtemp(prefix="h4d_seed_"))  # no .streamlit/ here
    sys.path.insert(0, str(REPO))
    import streamlit as st
    try:
        if "DATABASE_URL" in st.secrets:
            sys.exit("STOP: a Streamlit secrets file is visible; it could override the demo URL.")
    except Exception:
        pass  # no secrets file found anywhere: exactly what we want
    import storage  # connects now (init_db), to the demo URL only
    if storage._get_database_url() != url:
        sys.exit("STOP: the app resolved a different database URL.")
    return storage


def reset(storage):
    conn = storage.get_connection()
    try:
        conn.cursor().execute(
            "DROP TABLE IF EXISTS " + ", ".join(APP_TABLES) + " CASCADE"
        )
        conn.commit()
    finally:
        storage.release_connection(conn)
    storage.init_db()
    print("Demo database wiped and recreated (empty).")


def is_empty(storage) -> bool:
    return not storage.get_interviews() and not storage.get_people()


def check_quotes(ai, analysis: dict, transcript: str) -> list[str]:
    """Every quote in the output, checked against the transcript. Strict =
    exact substring. Normalized = the app's own check (whitespace and
    curly-quote differences ignored). Returns problems found."""
    import re
    quotes = []
    for row in analysis.get("pains_and_gains", []):
        quotes.append(("pains_and_gains.verbatim_quote", row.get("verbatim_quote", "")))
    for row in analysis.get("hypothesis_ledger", []):
        for q in re.findall(r'"([^"]+)"', row.get("evidence", "") or ""):
            quotes.append(("hypothesis_ledger.evidence", q))
    for row in analysis.get("mom_test_audit", []):
        quotes.append(("mom_test_audit.question_verbatim", row.get("question_verbatim", "")))
    problems = []
    for field, q in quotes:
        if not q.strip():
            continue
        strict = q in transcript
        normalized = ai._quote_appears_in_notes(q, transcript)
        if not strict:
            label = "differs only in whitespace/quote style" if normalized else "NOT FOUND in transcript"
            problems.append(f"{field}: {label}: {q!r}")
    print(f"    quotes checked: {sum(1 for _, q in quotes if q.strip())}, problems: {len(problems)}")
    return problems


def seed(storage, export_key: str | None):
    import ai
    import env_store
    from demo import seed_content as content
    from render import build_export_header
    from docx_export import build_docx_report

    api_key = env_store.load_api_key()
    if not api_key:
        sys.exit("STOP: no Anthropic API key found (.env next to the app).")

    ids = {}
    for key, parent, text in content.HYPOTHESES:
        ids[key] = storage.add_hypothesis(ids[parent] if parent else None, text)
    hypotheses = [text for _, _, text in content.HYPOTHESES]
    print(f"Hypotheses added: {len(hypotheses)}")

    all_problems, timings = {}, {}
    for item in content.SEED_INTERVIEWS:
        transcript, notes, p = item["transcript"], item["notes"], item["person"]
        print(f"\n== {p['rank']} {p['name']}".replace("==  ", "== "))
        t = {}
        start = time.perf_counter()
        step = ai.start_adaptive_clarifying(hypotheses, transcript, api_key, documents=[], additional_notes=notes)
        t["first question"] = time.perf_counter() - start
        history, question, rnd = step["history"], step["question"], step["round"]
        answered = []
        for answer in item["answers"]:
            if not question:
                break
            s = time.perf_counter()
            nxt = ai.continue_adaptive_clarifying(history, question, answer, rnd, api_key, documents=[])
            t[f"after answer {len(answered) + 1}"] = time.perf_counter() - s
            answered.append((question, answer))
            print(f"    Q{rnd}: {question}")
            history, question, rnd = nxt["history"], nxt["question"], nxt["round"]
        s = time.perf_counter()
        analysis = ai.run_step2_after_adaptive_clarifying(history, api_key, documents=[])
        t["analysis"] = time.perf_counter() - s
        all_problems[item["key"]] = check_quotes(ai, analysis, transcript)

        digest = ai.build_digest(hypotheses, analysis, transcript, api_key, person=None, additional_notes=notes)
        title = storage.build_interview_title(p["name"], p["rank"], p["interview_date"])
        interview_id = storage.save_interview(title, transcript, notes=notes)
        run_id = storage.save_run(
            interview_id, hypotheses, [q for q, _ in answered], [a for _, a in answered],
            analysis, digest, document_ids=[],
        )
        person_id = storage.add_person(interview_status="completed", **p)
        storage.set_interview_person(interview_id, person_id)
        person = storage.get_person(person_id)
        storage.update_run_digest(run_id, ai.build_digest(
            hypotheses, analysis, transcript, api_key, person, additional_notes=notes,
        ))
        timings[item["key"]] = t
        print("    timings (s): " + ", ".join(f"{k} {v:.0f}" for k, v in t.items()))

        if export_key == item["key"]:
            interview = storage.get_interview(interview_id)
            run = storage.get_runs_for_interview(interview_id)[0]
            header = build_export_header(interview, person, run, [])
            out = REPO / "demo" / f"fallback_{item['key']}_report.docx"
            out.write_bytes(build_docx_report(run["output"], run["hypothesis_text"], header=header))
            print(f"    Word report written: {out}")

    print("\n== Quote check summary")
    for key, problems in all_problems.items():
        print(f"  {key}: {'all quotes word-for-word' if not problems else f'{len(problems)} problem(s)'}")
        for line in problems:
            print(f"     - {line}")
    unlinked = [iv["title"] for iv in storage.get_interviews() if not iv["person_id"]]
    print(f"\nInterviews: {len(storage.get_interviews())}, without an interviewee: {unlinked or 'none'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url-file", required=True)
    ap.add_argument("--expect-host", required=True)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--export-docx", metavar="KEY")
    args = ap.parse_args()

    url = guard(args.url_file, args.expect_host)
    export_key = args.export_docx
    storage = connect_app(url)
    if args.reset:
        reset(storage)
    elif not is_empty(storage):
        sys.exit("STOP: the demo database already has data. Re-run with --reset to wipe and re-seed it.")
    seed(storage, export_key)


if __name__ == "__main__":
    main()
