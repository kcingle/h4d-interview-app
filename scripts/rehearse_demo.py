"""
scripts/rehearse_demo.py — Run the instructor's demo script end to end
against the DEMO database, through the app's real pages (Streamlit
AppTest), the real AI, and real data. Times every step and reports
failures, retry notices, and anything that looks wrong.

Refuses to start unless .streamlit/secrets.toml points at the demo host.

    venv\\Scripts\\python scripts\\rehearse_demo.py --expect-host <demo host> --runs 3
"""
import argparse
import subprocess
import sys
import time
import tomllib
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SECRETS = REPO / ".streamlit" / "secrets.toml"
URL_FILE = r"C:\Users\katei\h4d-secrets\demo_database_url.txt"
HEADINGS = [
    "1. Mom Test audit", "2. Pains-and-gains table", "3. Hypothesis ledger",
    "4. Three sharper questions for the next beneficiary", "5. Slack write-up",
    "Claims to verify before this goes in a brief",
]


def guard(expect_host):
    secrets = tomllib.loads(SECRETS.read_text(encoding="utf-8"))
    host = urllib.parse.urlparse(secrets["DATABASE_URL"]).hostname
    print(f"App will connect to: {host}")
    if host != expect_host:
        sys.exit("STOP: secrets.toml is not pointing at the demo database.")
    return secrets["TEAM_PASSWORD"]


def page(path, authenticated=True, **state):
    from streamlit.testing.v1 import AppTest
    # Always start from the main app file and navigate, like a browser, so
    # page links ("Open in Interviews →") resolve the way they do live.
    at = AppTest.from_file(str(REPO / "Process_Interview.py"), default_timeout=300)
    if path != "Process_Interview.py":
        at.switch_page(path)
    if authenticated:
        at.session_state["authenticated"] = True
    for k, v in state.items():
        at.session_state[k] = v
    return at


def texts(at):
    out = []
    for kind in ("markdown", "subheader", "caption", "info", "warning", "error", "success", "title", "header"):
        out += [getattr(e, "value", "") or "" for e in getattr(at, kind)]
    return out


def problems_on(at, where, issues):
    if at.exception:
        issues.append(f"{where}: EXCEPTION {[e.value for e in at.exception]}")
    for w in at.warning:
        if "⚠️" in (w.value or ""):
            issues.append(f"{where}: retry notice shown: {w.value[:120]}")
    for e in at.error:
        issues.append(f"{where}: error box: {(e.value or '')[:120]}")


def timed(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def one_run(n, team_password, transcript, answers):
    import streamlit as st
    st.switch_page = lambda p: st.stop()  # AppTest can't follow page switches
    import storage
    t, issues = {}, []

    # 1. Log in, Interviews page loads.
    at = page("pages/1_Interviews.py", authenticated=False)
    t["open app (login screen)"] = timed(at.run)
    at.text_input[0].set_value(team_password)
    t["log in + Interviews page"] = timed(lambda: at.button[0].click().run())
    problems_on(at, "Interviews (login)", issues)
    if not at.selectbox:
        issues.append("Interviews: no interview dropdown after login")

    # 2-4. Process Interview: paste, Start, 3 questions, analysis.
    at = page("Process_Interview.py")
    at.run()
    at.text_area(key="raw_notes").set_value(transcript).run()
    start = next(b for b in at.button if b.label == "Start")
    t["Start -> question 1"] = timed(lambda: start.click().run())
    problems_on(at, "Start", issues)
    questions = []
    for i, answer in enumerate(answers, start=1):
        if at.session_state["flow_stage"] != "clarifying":
            issues.append(f"expected clarifying question {i}, stage is {at.session_state['flow_stage']}")
            break
        questions.append(at.session_state["adaptive_current_question"])
        rnd = at.session_state["adaptive_round"]
        at.text_area(key=f"adaptive_answer_box_{rnd}").set_value(answer)
        label = f"answer {i} -> question {i + 1}" if i < len(answers) else "answer 3 -> analysis saved"
        t[label] = timed(lambda: next(b for b in at.button if b.label == "Answer").click().run())
        problems_on(at, f"Answer {i}", issues)
    if at.session_state["flow_stage"] != "metadata":
        issues.append(f"analysis did not reach the metadata step (stage {at.session_state['flow_stage']})")
        return t, issues, questions
    suggested = at.session_state["metadata_suggestion"]
    if suggested.get("name_or_label", "").strip() != "Jordan Vance" or suggested.get("rank") != "1LT":
        issues.append(f"metadata suggestion looks off: {suggested.get('rank')!r} {suggested.get('name_or_label')!r}")
    interview_id = at.session_state["pending_metadata_interview_id"]

    # 5. Confirm metadata -> interviewee linked.
    confirm = next(b for b in at.button if b.label == "Confirm and save metadata")
    t["Confirm metadata"] = timed(lambda: confirm.click().run())
    problems_on(at, "Confirm metadata", issues)
    person = storage.get_person_for_interview(interview_id)
    if not person:
        issues.append("live-processed interview has NO interviewee linked")
    title = storage.get_interview(interview_id)["title"]

    # 6. Interviews page shows the new interview's five outputs.
    ids = [iv["id"] for iv in storage.get_interviews()]
    at = page("pages/1_Interviews.py", interviews_selectbox=ids.index(interview_id))
    t["Interviews page shows result"] = timed(at.run)
    problems_on(at, "Interviews (result)", issues)
    shown = texts(at)
    missing = [h for h in HEADINGS if not any(h in s for s in shown)]
    if missing:
        issues.append(f"result page missing sections: {missing}")

    # 7. Hypothesis Findings for hypothesis 1.
    at = page("pages/3_Hypothesis_Findings.py")
    t["Hypothesis Findings"] = timed(at.run)
    problems_on(at, "Hypothesis Findings", issues)
    unsupported = any("Unsupported / inferred" in s for s in texts(at))

    # 8. Search, Compare, Chat.
    at = page("pages/4_Search_Compare_Chat.py")
    t["Search/Compare/Chat page load"] = timed(at.run)
    problems_on(at, "Search page", issues)
    t["Search 'jamming'"] = timed(lambda: at.text_input(key="search_query").set_value("jamming").run())
    problems_on(at, "Search", issues)
    try:
        ms = at.multiselect(key="compare_interviews")
        ms.set_value([iv["id"] for iv in storage.get_interviews()[:2]])  # options are interview ids
        t["Compare 2 interviews on hypothesis"] = timed(at.run)
        problems_on(at, "Compare", issues)
    except Exception as e:  # report, don't crash the rehearsal
        issues.append(f"Compare could not be driven: {e}")
    t["Chat question"] = timed(lambda: at.chat_input[0].set_value(
        "Which interviews say leaders can't tell where a grid came from?").run())
    problems_on(at, "Chat", issues)
    chat = at.session_state["chat_history"] if "chat_history" in at.session_state else []
    if not any(m.get("role") == "assistant" for m in chat):
        issues.append("Chat produced no reply")

    return t, issues, questions, title, unsupported


def clean(expect_host):
    """Leave the database as the presenter will find it: seed set only."""
    subprocess.run([sys.executable, str(REPO / "scripts" / "seed_demo.py"), "--url-file", URL_FILE,
                    "--expect-host", expect_host, "--clean-extras"], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-host", required=True)
    ap.add_argument("--runs", type=int, default=3)
    args = ap.parse_args()
    team_password = guard(args.expect_host)
    sys.path.insert(0, str(REPO))
    import os
    os.chdir(REPO)
    from demo import seed_content as content
    transcript = (REPO / "demo" / "DEMO_TRANSCRIPT.txt").read_text(encoding="utf-8")

    for n in range(1, args.runs + 1):
        print(f"\n===== Rehearsal {n} =====")
        try:
            result = one_run(n, team_password, transcript, content.LIVE_ANSWERS)
        finally:
            clean(args.expect_host)
        t, issues, questions = result[:3]
        for i, q in enumerate(questions, start=1):
            print(f"  Q{i}: {q}")
        if len(result) > 3:
            print(f"  saved as: {result[3]} | Findings shows 'Unsupported / inferred': {result[4]}")
        for step, secs in t.items():
            print(f"  {step:<40} {secs:6.1f} s")
        print("  issues: " + ("none" if not issues else ""))
        for line in issues:
            print(f"   - {line}")
        print("  cleaned up: demo database back to the 4 seed interviews")


if __name__ == "__main__":
    main()
