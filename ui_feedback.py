"""
ui_feedback.py — The one way this app shows a recoverable failure: a calm
warning that says what happened and that nothing was lost, plus a
"Try again" button. Used for AI-call failures (timeouts, rate limits,
API errors) and database hiccups alike, so a presenter never sees a red
traceback and always has an obvious next click.

Kept tiny and Streamlit-only (no storage/ai imports) so storage.py can use
it without a circular import.
"""

import streamlit as st


def retry_notice(message: str, key: str, button_label: str = "Try again") -> bool:
    """Render the calm failure notice and return True on the rerun where
    "Try again" was clicked."""
    st.warning(f"⚠️ {message}")
    return st.button(button_label, key=key, type="primary")


def remember_failure(slot: str, message: str) -> None:
    """Stash a failure so the notice survives the rerun that follows."""
    st.session_state[f"_failure_{slot}"] = message


def pending_failure(slot: str) -> str | None:
    return st.session_state.get(f"_failure_{slot}")


def clear_failure(slot: str) -> None:
    st.session_state.pop(f"_failure_{slot}", None)
