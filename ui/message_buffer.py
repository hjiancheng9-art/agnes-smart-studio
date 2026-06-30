"""Thread-safe message buffer with Rich→ANSI→prompt_toolkit rendering.

All existing console.print() output is captured, rendered to ANSI via Rich,
then displayed in the prompt_toolkit message area as ANSI(...) formatted text.
"""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass, field

from prompt_toolkit.formatted_text import ANSI, FormattedText, to_formatted_text
from rich.console import Console as RichConsole
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text as RichText

__all__ = ["MessageBuffer", "Message"]


@dataclass
class Message:
    role: str          # "user" | "assistant" | "system" | "tool"
    content: str       # plain text (already stripped of Rich markup)
    timestamp: float = field(default_factory=time.time)

    def age_str(self) -> str:
        delta = time.time() - self.timestamp
        if delta < 60:
            return f"{delta:.0f}s"
        elif delta < 3600:
            return f"{delta / 60:.0f}m"
        return f"{delta / 3600:.1f}h"


class MessageBuffer:
    """Thread-safe message store, renders to prompt_toolkit FormattedText.

    Uses a Rich Console to convert Markdown content to ANSI strings, which
    prompt_toolkit's ``ANSI()`` class can parse into formatted text tuples.
    """

    def __init__(self, max_messages: int = 500):
        self._lock = threading.Lock()
        self._messages: list[Message] = []
        self._max = max_messages
        # Rich console that renders to an ANSI string buffer
        self._ansi_buf = io.StringIO()
        self._rich = RichConsole(
            file=self._ansi_buf,
            force_terminal=True,
            color_system="truecolor",
            width=120,
            height=9999,
        )

    # ── Write ────────────────────────────────────────────────

    def add(self, role: str, content: str) -> None:
        with self._lock:
            self._messages.append(Message(role=role, content=content))
            if len(self._messages) > self._max:
                self._messages = self._messages[-self._max:]

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()

    # ── Read ─────────────────────────────────────────────────

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._messages)

    def latest(self, n: int = 1) -> list[Message]:
        with self._lock:
            return self._messages[-n:]

    def all(self) -> list[Message]:
        with self._lock:
            return list(self._messages)

    # ── Render ───────────────────────────────────────────────

    def _rich_to_ansi(self, renderable) -> str:
        """Render a Rich renderable to an ANSI string."""
        self._ansi_buf.truncate(0)
        self._ansi_buf.seek(0)
        self._rich.print(renderable)
        return self._ansi_buf.getvalue().rstrip("\n")

    def render_message(self, msg: Message, width: int = 100) -> str:  # noqa: ARG002
        """Render a single message as ANSI string with beast-themed decorations."""
        from ui.theme import COLORS

        if msg.role == "user":
            # User messages: blue dragon-themed, left-aligned
            label = RichText("◇ You", style=f"bold {COLORS['qinglong']}")
            prefix = RichText("╭─", style=f"dim {COLORS['qinglong']}")
            panel = Panel(
                Markdown(msg.content) if msg.content else RichText(""),
                title=label,
                border_style=COLORS["qinglong"],
                padding=(0, 1),
            )
            return self._rich_to_ansi(panel)

        elif msg.role == "assistant":
            # AI responses: green kirin-themed with spark border
            label = RichText("● CRUX", style=f"bold {COLORS['qilin']}")
            panel = Panel(
                Markdown(msg.content) if msg.content else RichText(""),
                title=label,
                border_style=COLORS["qilin"],
                padding=(0, 1),
            )
            return self._rich_to_ansi(panel)

        elif msg.role == "system":
            # System messages: subtle, dim with xuanwu shield
            shield = "◎" if len(msg.content) < 60 else ""
            prefix = f"{shield} " if shield else ""
            return self._rich_to_ansi(
                RichText(
                    f"{prefix}{msg.content}",
                    style=f"dim italic {COLORS['text_tertiary']}",
                )
            )

        elif msg.role == "tool":
            return self._rich_to_ansi(
                Panel(
                    RichText(msg.content, style=COLORS["text_secondary"]),
                    border_style=COLORS["border"],
                    padding=(0, 1),
                )
            )

        return msg.content

    def render_all(self, width: int = 100) -> FormattedText:
        """Render all messages as prompt_toolkit FormattedText."""
        with self._lock:
            if not self._messages:
                return FormattedText([("class:dim", "No messages yet.")])

            parts = []
            for msg in self._messages:
                ansi = self.render_message(msg, width)
                if parts:
                    parts.append(("", "\n"))
                # ANSI() returns a non-iterable object in prompt_toolkit 3.0.52+,
                # expand it to flat (style, text) tuples via to_formatted_text().
                parts.extend(to_formatted_text(ANSI(ansi)))

            return FormattedText(parts)

    def render_all_plain(self, width: int = 100) -> str:
        """Render all messages as a single ANSI string (for Window control)."""
        with self._lock:
            if not self._messages:
                return "No messages yet."

            lines = []
            for msg in self._messages:
                lines.append(self.render_message(msg, width))
            return "\n".join(lines)
