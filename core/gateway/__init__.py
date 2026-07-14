"""CRUX Gateway — OpenAI-compatible HTTP API.

Exposes CRUX as a drop-in replacement for OpenAI clients:
    crux serve --port 8000

Then:
    openai.api_base = "http://localhost:8000/v1"
    openai.ChatCompletion.create(model="agnes-2.0-pro", messages=[...])
"""

from core.gateway.server import create_app, run_server

__all__ = ["create_app", "run_server"]
