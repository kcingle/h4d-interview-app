"""env_store.py — Resolves the Anthropic API key. Reads Streamlit secrets
(ANTHROPIC_API_KEY) FIRST — that's the deployed/cloud case, set once in
Streamlit Community Cloud's secrets, server-side only, never on anyone's
laptop or in the repo — falling back to a plain local `.env` file next
to the app (gitignored — see .gitignore, never committable) for local
development, matching storage.py's DATABASE_URL resolution (secrets
first, then a local fallback) for the same reason.

This is deliberately its OWN module, not part of storage.py: a secret
like this must never end up in the app's database — especially now that
it can be a shared, hosted Postgres instance (see the cloud-migration
branch) — it's either a per-deployment server secret or a per-machine
local file, never data the rest of the app persists to.

Why every page calls load_api_key() instead of reading st.session_state:
a value tied to a widget's `key=` (like the Settings page's API key
input) is only kept in Streamlit's session_state WHILE that widget is
actually being rendered — navigating to a page that doesn't render that
same widget drops it. That's the actual root cause of "Settings says the
key is set, but every other page says it's missing": the key never made
it anywhere those other pages could see it. Reading it from secrets/file
instead sidesteps that entirely (and is what makes the key survive an
app restart, not just a page switch).

No external dependency (e.g. python-dotenv) — the parsing/writing needed
for one KEY=value line is small enough to not be worth adding one.
"""

from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"
_KEY_NAME = "ANTHROPIC_API_KEY"


def load_api_key() -> str:
    """Resolve the API key: Streamlit secrets first (deployed case),
    then the local .env file (local dev case). Returns "" if neither
    has it, the file doesn't exist, or it can't be read — never raises,
    so a missing key just shows as "not set" rather than crashing."""
    try:
        import streamlit as st
        if _KEY_NAME in st.secrets:
            return st.secrets[_KEY_NAME]
    except Exception:
        pass

    if not ENV_PATH.exists():
        return ""
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() == _KEY_NAME:
            return value.strip().strip('"').strip("'")
    return ""


def save_api_key(key: str) -> None:
    """Save the API key to .env, replacing any previous value for it. A
    blank key removes the saved line entirely (clears it) rather than
    writing an empty value. Every other line already in the file (future
    local settings, comments, etc.) is preserved untouched."""
    key = (key or "").strip()
    try:
        existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    except OSError:
        existing_lines = []

    out_lines = []
    replaced = False
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name = stripped.partition("=")[0].strip()
            if name == _KEY_NAME:
                replaced = True
                if key:
                    out_lines.append(f"{_KEY_NAME}={key}")
                continue  # drop the old line entirely when clearing
        out_lines.append(line)

    if key and not replaced:
        out_lines.append(f"{_KEY_NAME}={key}")

    ENV_PATH.write_text(("\n".join(out_lines) + "\n") if out_lines else "", encoding="utf-8")
