# H4D Interview App

A local Streamlit app for processing Hacking for Defense customer-discovery
interviews. Built iteratively in small, verified steps.

**Current status: Step 1 — skeleton.** No AI yet. Storage layer works for
interviews; everything else is a placeholder page or stub function.

## Architecture

- `app.py` — entry point, and the "Process Interview" home page.
- `pages/` — one file per page; Streamlit's built-in multipage nav lists
  these in the sidebar automatically (numeric prefixes control order and
  are stripped from the displayed name).
- `ai.py` — **all** AI/LLM logic. Pages never call an AI API directly.
- `storage.py` — **all** persistence, backed by SQLite, behind simple
  named functions (`save_interview`, `get_interviews`, ...). If the
  backend is ever swapped to a hosted database, only this file changes.
- `config.py` — model name / API version. API keys are never hardcoded
  here — a later step loads them from a local `.env` file or
  `st.secrets`, entered through the Settings page.
- `h4d_app.db` — the SQLite database file. Created automatically the
  first time the app runs; gitignored.

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

## Testing Step 1

1. Launch the app as above.
2. Confirm you can navigate every page in the sidebar: the home page
   ("app" — labeled "Process Interview"), Interviews, Hypotheses,
   Documents, Chat, Settings.
3. Go to the **Interviews** page. Open the "🧪 Temporary test" box, edit
   or leave the default title/text, and click **Save to database**.
4. Confirm a success message appears, and the new row shows up in the
   table below (it reads live from `h4d_app.db` via `storage.get_interviews()`).
5. Stop and restart the app — the saved interview should still be there,
   proving it's persisted to disk, not just session state.

## What's next

See the project plan for Steps 2–8 (core AI processing loop, saved runs,
hypothesis tree, reference documents, metadata + people, chat, and
cross-interview comparison). Each step is built and verified before the
next begins.
