"""
config.py — Central place for model / API configuration.

Step 2: model + API version are filled in below (confirmed current at
build time). API keys are still NEVER hardcoded here — the key is entered
in-app on the Settings page and kept only in Streamlit's session state for
now (not yet persisted to disk; that's planned for a later step).
"""

# Model used for all AI calls in ai.py.
MODEL_NAME = "claude-sonnet-5"

# Anthropic API version. The official Python SDK (used in ai.py) sets this
# header automatically on every request, so this constant is kept here as
# documented reference in case raw HTTP is ever used instead.
API_VERSION = "2023-06-01"
