# H4D Interview App

A local Streamlit app for processing Hacking for Defense customer-discovery
interviews. Built iteratively in small, verified steps.

**Current status:** the core two-step AI analysis engine, interview
storage with rerun history, a hypothesis tree, reference documents (with
a pinned Mom Test doc), interviewee metadata + a Metadata view (with a
one-click Excel export), exporting a run to Markdown/.txt,
cross-interview corpus features (Hypothesis Findings, Search & Compare),
and a corpus-wide Chat (now combined with Search & Compare on one page)
are all built and working. Every page that lets
you add a hypothesis, interview, or person also lets you delete one —
always behind a confirm/cancel step.

**Live AI processing (Process Interview page, and the Interviews page's
rerun control) requires an Anthropic API key**, entered on the Settings
page. Everything else — browsing/editing hypotheses, documents, people,
and past runs — works with no key.

## Pages

- **Process Interview** (`Process_Interview.py`, the home page — renamed
  from `app.py` so the sidebar reads "Process Interview" instead of the
  filename-derived "app") — check off one or more
  hypotheses from the tree to test this run (active ones pre-checked),
  pick reference documents to include, and paste interview notes plus
  optional Additional Notes (nonverbal communication, tone, the setting,
  or anything else observed but not written as dialogue). Running the
  two-step AI flow (clarifying questions, then the full analysis) saves
  the interview and hands off IMMEDIATELY to the Interviews page for that
  one interview (pre-selected, its run auto-expanded) — the redirect
  never waits on anything else, including interviewee metadata.
- **Interviews** — browse every saved interview, review all of its past
  runs (each kept forever, each exportable to Markdown/.txt with a
  provenance header), inspect or regenerate that run's structured digest
  (see below), rerun the interview against one or more different
  hypotheses without losing earlier runs, or delete the whole interview
  (and every run it has) — behind a confirm/cancel step, the linked
  person is kept. A freshly-processed interview with no linked person
  yet also gets a suggest-and-confirm interviewee metadata form here
  (moved from Process Interview so the handoff there is never gated on
  filling it out) — including up to 5 interviewer names, stored as a
  real list (`people.interviewers_json`), not a delimited string.
- **Hypotheses** — build and manage the hypothesis tree: add
  families/children, edit text, delete a node (only once it has no
  children — delete those first), or toggle active/dormant. Nothing is
  ever auto-added — a brand-new database starts with an empty tree;
  every hypothesis is one you added, or one an AI suggestion you
  explicitly approved. **Suggest hypotheses**
  (`ai.suggest_hypotheses`) proposes new candidates grounded in
  everything logged in the corpus so far (same material Chat uses) —
  each with a rationale citing which interview supports it, and an
  optional parent to attach under. Suggestions are shown as checkboxes;
  nothing reaches the tree until you check the ones you want and click
  "Add approved." Two view modes: **List (edit)** for all of the above,
  and **Visual tree** — a real clickable expand/collapse diagram (plain
  HTML, no new dependency) for browsing the tree read-only.
- **Documents** — upload (.txt, .md, or .pdf) or paste reference
  documents the analysis engine can use as context. Includes a
  permanent, protected pinned slot for the Mom Test book PDF (upload it
  here) — pinned documents are a separate, mandatory category: always
  included on every analysis, never a toggle, and can't be deleted
  (though the PDF itself can be replaced any time). Every other document
  is opt-in, toggled per-interview on the Process Interview page. PDFs
  are sent to Claude natively (it reads the actual pages) — no
  text-extraction step, no extra dependency.
- **Metadata** (renamed from "People" for clarity — this is specifically
  the interviewee metadata confirmed on Process Interview) —
  browsable/filterable/sortable table of everyone interviewed (name,
  role, organization, rank, branch/service, seniority, relationship,
  interview status, date, descriptor), with a one-click **Export to
  Excel** button (respects the filters set on this page,
  `people_export.py`), an editable form per person, a delete button
  (behind confirm/cancel — any linked interview is kept, just unlinked),
  and their linked interview(s)/runs (also exportable).
- **Hypothesis Findings** (renamed from "Hypothesis Status" — it sat too
  close to "Hypotheses" in the sidebar with an easily-confused name) —
  select a hypothesis and see every interview that tested it, rolled up
  from digests (never full transcripts): mechanical
  validated/invalidated/untested counts, each interview's verdict with
  its verbatim quote and interviewee, a clearly separated
  "unsupported/inferred" section for any verdict with no verified quote,
  and the hypothesis's full version lineage with its own per-version
  counts. This page only organizes what interviews already said — it
  never generates a summary interpretation.
- **Search, Compare & Chat** — one page, four tabs. **Search** is
  keyword/tag search over every interview's digest (plain substring
  matching — no semantic search, no vector DB), returning real,
  attributed, verbatim quotes. **Compare** is a side-by-side compare of
  2+ interviews on one hypothesis or topic tag. Like Hypothesis
  Findings, both of those only retrieve and organize what was already
  said — never an AI-written "here's the contrast" summary.
  **Corpus Chat** is a real conversation over the whole corpus, unlike
  Search/Compare's zero-synthesis retrieval: every message sends the
  full hypothesis tree, people roster, document list, and every
  interview's raw transcript + Additional Notes + complete analysis
  (not just its digest) as context (`ai.build_corpus_context`) — cached
  after the first turn each session, so later turns are cheap; only the
  first message and an explicit "Refresh context" pay full price.
  Answers cite which interview a finding came from, and the system
  prompt tells the model to say so plainly rather than guess when
  something isn't in the material — verified live: it correctly
  declined to answer about an interview that doesn't exist in the
  corpus. **Background & Definitions** (`ai.define_terms`) is a
  different kind of assistant: it explains words/acronyms/concepts, and
  — unlike everywhere else in this app — is explicitly allowed to use
  general domain knowledge, not just the corpus (verified live:
  correctly gave the standard DoD meaning of an ambiguous acronym when
  the corpus was empty, rather than guessing). Each definition has an
  "Add to dictionary" button; nothing saves automatically. Corpus Chat
  and Background & Definitions share one cached corpus context per
  session, same as before the two pages were merged.
- **Dictionary** — every term saved from Search, Compare & Chat's
  Background & Definitions tab: search by term or definition text, mark
  an entry high-importance (sorts it to the top), or delete it. Pure
  browsing — no AI calls happen here.
- **Settings** — enter your Anthropic API key. Saved locally to a `.env`
  file next to the app (gitignored — never committed, see `env_store.py`),
  so every page that calls the API sees the same key, and it survives
  restarting the app.

## Architecture

- `Process_Interview.py` — entry point, and the "Process Interview" home
  page. Renamed from `app.py`: Streamlit's classic multipage nav derives
  a page's sidebar label from its filename with no override for the
  entry script, so it showed up as the bare word "app" — confusing
  enough on its own to be worth a rename.
- `pages/` — one file per page; Streamlit's built-in multipage nav lists
  these in the sidebar automatically (numeric prefixes control order and
  are stripped from the displayed name).
- `ai.py` — **all** AI/LLM logic. Pages never call an AI API directly.
  Holds the exact graded system prompt (verbatim, never edited), plus
  separate, unrelated prompts for Chat (`CHAT_SYSTEM_INSTRUCTIONS`),
  hypothesis suggestions (`suggest_hypotheses`), and term/acronym/concept
  definitions (`define_terms` — the one place in this app explicitly
  allowed to use general knowledge, not just the corpus), plus
  `build_corpus_context`, which formats everything the rest of the app
  knows into one text blob the corpus-grounded ones send as context.
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
- `env_store.py` — local persistence for the Anthropic API key, via a
  `.env` file next to the app (gitignored, separate from the SQLite
  database on purpose — a secret shouldn't live in a database that might
  later be shared/hosted). Every page reads the key with
  `env_store.load_api_key()` rather than `st.session_state`, since a
  value tied to a widget's `key=` (like the Settings page's input) is
  only kept in session_state while that widget is being rendered —
  reading the file directly is what makes every page see the same key.
- `people_export.py` — builds the Metadata page's Excel export
  (`build_people_excel`). A plain function with no Streamlit dependency,
  so it's directly unit-testable; the page just calls it and hands the
  bytes to `st.download_button`.
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

**Every quote is checked against that interview's actual raw text (plus
its optional Additional Notes, if any) before being kept** — an
unverifiable or fabricated quote is dropped, not included, matching the
same anti-fabrication rule as the main analysis. Topic tags are the one
part that needs an API key (a small, separate, non-crashing call);
everything else works with no key.

A run processed before this existed has an old, thin digest — the
Interviews page shows this and offers a **Regenerate digest** button,
which rebuilds it from that run's already-saved output (no reprocessing,
no re-reading the transcript through the two-step flow again).

Hypothesis selection is a checklist sourced directly from the hypothesis
tree (on both Process Interview and the Interviews page's rerun control),
and a single run can test one or more hypotheses at once. Each digest
entry records the exact hypothesis text it was tested against, so the
Hypothesis Findings and Search & Compare pages can match a run's verdict
back to the right tree node (case/whitespace-normalized, still exact —
not fuzzy — to avoid attributing evidence to the wrong hypothesis) even
when a run tested several hypotheses in one pass.

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
streamlit run Process_Interview.py
```

This opens the app in your browser (usually `http://localhost:8501`).
Use the sidebar to navigate between pages.

## Using AI features

1. Get an Anthropic API key from console.anthropic.com (separate from a
   claude.ai chat subscription — it's pay-per-use, billed by usage).
2. Go to the **Settings** page and paste it in. It's saved to a local
   `.env` file (gitignored) so you only need to enter it once, ever.
3. Go to **Process Interview** to run a real analysis, or **Interviews**
   to rerun a saved one against a different hypothesis.

Without a key, every other page still works fully for browsing/editing/
deleting (Hypotheses, Documents, Metadata, past Interviews) — you just
can't trigger new AI calls, which includes Chat and the Hypotheses
page's "Suggest hypotheses" button.

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

Every planned feature is built. Ongoing work happens as small, verified
changes on top of what's here (see git history for the shape each one
took).
