"""
config.py — Central place for model / API configuration.

Step 2: model + API version are filled in below (confirmed current at
build time). API keys are still NEVER hardcoded here — the key is entered
in-app on the Settings page and kept only in Streamlit's session state for
now (not yet persisted to disk; that's planned for a later step).
"""

# Model used for the graded interview analysis and the adaptive
# clarifying-question loop that feeds it.
MODEL_NAME = "claude-sonnet-5"

# Cheaper/faster model for small, non-graded, checkable-output calls that
# don't need Sonnet-level judgment: interviewee-metadata suggestion and
# digest topic-tagging. Neither is part of the graded analysis rubric, and
# both are simple extraction tasks the user reviews before anything is
# saved (metadata) or that only feed internal search (topic tags) — a
# cheaper model here cuts cost with low quality risk. Haiku 4.5 has no
# `effort` parameter (it errors), so calls using this model never pass one.
MODEL_NAME_SMALL = "claude-haiku-4-5"

# Anthropic API version. The official Python SDK (used in ai.py) sets this
# header automatically on every request, so this constant is kept here as
# documented reference in case raw HTTP is ever used instead.
API_VERSION = "2023-06-01"
