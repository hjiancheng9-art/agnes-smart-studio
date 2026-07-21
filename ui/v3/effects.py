"""CRUX TUI v3 — effects (side-effects dispatched by the reducer).

Effects are PURE DATA. The reducer returns a list of Effect objects;
the app loop executes them. This keeps the reducer testable and the
side-effect surface explicit and auditable.

Naming convention: verb_noun (e.g. "run_model_stream", "copy_to_clipboard").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Effect:
    """A side-effect to execute after state reduction."""

    kind: str
    payload: dict[str, Any] | None = None

    # ── Factory helpers ──

    @staticmethod
    def run_stream(text: str) -> Effect:
        return Effect("run_model_stream", {"text": text})

    @staticmethod
    def cancel_stream() -> Effect:
        return Effect("cancel_model_stream")

    @staticmethod
    def render_chat() -> Effect:
        return Effect("render_chat")

    @staticmethod
    def render_thinking() -> Effect:
        return Effect("render_thinking")

    @staticmethod
    def render_activity() -> Effect:
        return Effect("render_activity")

    @staticmethod
    def render_status() -> Effect:
        return Effect("render_status")

    @staticmethod
    def recalculate_layout() -> Effect:
        return Effect("recalculate_layout")

    @staticmethod
    def finalize_stream() -> Effect:
        return Effect("finalize_stream")

    @staticmethod
    def copy_to_clipboard(text: str, as_markdown: bool = False) -> Effect:
        return Effect("copy_to_clipboard", {"text": text, "as_markdown": as_markdown})

    @staticmethod
    def execute_command(command: str) -> Effect:
        return Effect("execute_command", {"command": command})

    @staticmethod
    def scroll_to_bottom() -> Effect:
        return Effect("scroll_to_bottom")

    @staticmethod
    def exit_app() -> Effect:
        return Effect("exit_app")

    @staticmethod
    def analyze_image(path: str) -> Effect:
        return Effect("run_model_stream", {"text": "Describe this image.", "image_url": path})

    @staticmethod
    def none() -> Effect:
        return Effect("noop")
