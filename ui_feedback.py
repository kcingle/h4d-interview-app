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


import contextlib  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402


@contextlib.contextmanager
def heartbeat(message: str, every: float = 2.0):
    """Use instead of st.spinner around any call that can take more than
    ~20 seconds (AI calls). Shows the message with a running timer and
    refreshes it every `every` seconds from a helper thread.

    Why: Streamlit Community Cloud drops a browser connection that has
    sent nothing new for about 30 seconds (measured 2026-11-18; the same
    wait never drops locally). A dropped connection stops the running
    script and the browser comes back as a NEW session, which is logged
    out and has lost the interview in progress. The timer refresh is
    real data on the connection, so it stays open however long the call
    takes. The call itself still runs in the script thread, unchanged."""
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

    box = st.empty()
    box.info(f"⏳ {message}")
    start = time.monotonic()
    stop = threading.Event()

    def beat():
        while not stop.wait(every):
            try:
                box.info(f"⏳ {message} ({int(time.monotonic() - start)} s so far)")
            except Exception:
                return  # the script run ended or the session went away

    thread = threading.Thread(target=beat, daemon=True)
    if get_script_run_ctx() is not None:
        add_script_run_ctx(thread)
        thread.start()
    try:
        yield
    finally:
        stop.set()
        if thread.is_alive():
            thread.join(timeout=every + 1)
        box.empty()
