# H4D Interview App

A local Streamlit app for processing Hacking for Defense customer-discovery
interviews. Built iteratively in small, verified steps.

**Current status: through Step 7 (export).** The core two-step AI
analysis engine, interview storage with rerun history, a hypothesis
tree, reference documents (with a pinned Mom Test doc), interviewee
metadata + a People view, and exporting a run to Markdown/.txt are all
built and working. Chat and cross-interview corpus comparison are not
built yet.

**Live AI processing (Process Interview page, and the Interviews page's
rerun control) requires an Anthropic API key**, entered on the Settings
page. Everything else — browsing/editing hypotheses, documents, people,
and past runs — works with no key.

## Pages

- **Process Interview** (`app.py`, the home page) — pick reference
  documents to include, paste interview notes, run the two-step AI flow
  (clarifying questions, then the full analysis), review results as
  tables, and confirm interviewee metadata. Saves automatically.
- **Interviews** — browse every saved interview, review all of its past
  runs (each kept forever, each exportable to Markdown/.txt with a
  provenance header), inspect or regenerate that run's structured digest
  (see below), and rerun the interview against a different hypothesis
  without losing earlier runs.
- **Hypotheses** — build and manage the hypothesis tree: add
  families/children, edit text, toggle active/dormant. Nothing is ever
  deleted.
- **Documents** — upload (.txt, .md, or .pdf) or paste reference
  documents the analysis engine can use as context. Includes a
  permanent, protected pinned slot for the Mom Test book PDF (upload it
  here) — pinned documents are a separate, mandatory category: always
  included on every analysis, never a toggle, and can't be deleted
  (though the PDF itself can be replaced any time). Every other document
  is opt-in, toggled per-interview on the Process Interview page. PDFs
  are sent to Claude natively (it reads the actual pages) — no
  text-extraction step, no extra dependency.
- **People** — browsable/filterable/sortable table of everyone
  interviewed (name, role, organization, rank, branch/service, seniority,
  relationship, interview status, date, descriptor), with an editable
  form per person and their linked interview(s)/runs (also exportable).
- **Hypothesis Status** — select a hypothesis and see every interview
  that tested it, rolled up from digests (never full transcripts):
  mechanical validated/invalidated/untested counts, each interview's
  verdict with its verbatim quote and interviewee, a clearly separated
  "unsupported/inferred" section for any verdict with no verified quote,
  and the hypothesis's full version lineage with its own per-version
  counts. This page only organizes what interviews already said — it
  never generates a summary interpretation.
- **Chat** — placeholder; planned for a later step.
- **Settings** — enter your Anthropic API key (kept only in the browser
  session, not saved to disk).

## Architecture

- `app.py` — entry point, and the "Process Interview" home page.
- `pages/` — one file per page; Streamlit's built-in multipage nav lists
  these in the sidebar automatically (numeric prefixes control order and
  are stripped from the displayed name).
- `ai.py` — **all** AI/LLM logic. Pages never call an AI API directly.
  Holds the exact graded system prompt (verbatim, never edited).
- `storage.py` — **all** persistence, backed by SQLite, behind simple
  named functions (`save_interview`, `get_interviews`, ...). If the
  backend is ever swapped to a hosted database, only this file changes.
  Schema changes are applied automatically the next time the app runs
  (additive migrations, plus a one-time cleanup that removed a handful of
  columns/a table left over from early-step scaffolding that no code ever
  read or wrote — see `_cleanup_dead_schema_v1` for exactly what and why).
- `render.py` — shared table/markdown rendering for a run's output, used
  by every page that displays one, so results look identical everywhere.
- `config.py` — model name / API version.
- `h4d_app.db` — the SQLite database file. Created automatically the
  first time the app runs; gitignored (never committed — see Backups
  below).

## The per-run digest

Every processed run is saved with a structured **digest** (`ai.build_digest`)
in addition to its full output — a compact, quote-anchored summary meant
for future corpus-level features (testing a hypothesis across every
interview, cross-interview search, side-by-side compare) to read instead
of dozens of full transcripts. It includes, per run: the interviewee (once
metadata is confirmed), each hypothesis's verdict with its verbatim
evidence quote(s), key pains/gains with their verbatim quotes, a short
list of topic tags, and the claims-to-verify list.

**Every quote is checked against that interview's actual raw text before
being kept** — an unverifiable or fabricated quote is dropped, not
included, matching the same anti-fabrication rule as the main analysis.
Topic tags are the one part that needs an API key (a small, separate,
non-crashing call); everything else works with no key.

A run processed before this existed has an old, thin digest — the
Interviews page shows this and offers a **Regenerate digest** button,
which rebuilds it from that run's already-saved output (no reprocessing,
no re-reading the transcript through the two-step flow again).

**Known gap:** hypothesis selection isn't wired into the processing flow
yet — every run tests either the hardcoded default hypothesis or free
text typed into the Interviews page's rerun box, neither linked to a
hypothesis-tree node. The Hypothesis Status page matches a run to a tree
node by exact hypothesis text (case/whitespace-normalized), so an
interview only shows up under a tree hypothesis if it was actually
processed against that hypothesis's exact wording.

## Setup (Windows PowerShell)

From the project folder:

```powershell
cd C:\Users\katei\h4d-interview-app

# Create a virtual environment
python -m venv venv

# Activate it (if PowerShell blocks this, see note below)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

> If activation fails with a message about execution policies, run this
> once in an **admin** PowerShell, then retry activation:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

## Run

With the virtual environment activated:

```powershell
streamlit run app.py
```

This opens the app in your browser (usually `http://localhost:8501`).
Use the sidebar to navigate between pages.

## Using AI features

1. Get an Anthropic API key from console.anthropic.com (separate from a
   claude.ai chat subscription — it's pay-per-use, billed by usage).
2. Go to the **Settings** page and paste it in. It's kept only in this
   browser session, not written to disk.
3. Go to **Process Interview** to run a real analysis, or **Interviews**
   to rerun a saved one against a different hypothesis.

Without a key, every other page still works fully (Hypotheses, Documents,
People, browsing past Interviews) — you just can't trigger new AI calls.

## Backups

`h4d_app.db` holds your real interview data and is intentionally
gitignored — it's never committed. Dated backup copies live in
`backups/` (e.g. `backups/h4d_app_2026-09-02.db`), also gitignored, as a
separate restore point independent of git history.

## Version control

This project is a git repository. To see history or roll back:

```powershell
git log --oneline
git diff <commit>              # see what changed since a checkpoint
git checkout <commit> -- .     # restore code to that checkpoint
```

Rolling back git never touches `h4d_app.db` — that's restored (if ever
needed) from a file in `backups/` instead.

## What's next

Chat and cross-interview corpus comparison are not built yet. Each step
is built and verified before the next begins.
