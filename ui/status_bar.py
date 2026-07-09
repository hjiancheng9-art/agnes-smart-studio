"""Status bar — model | cwd | branch [diff] | context%."""

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from prompt_toolkit.formatted_text import FormattedText


def _term_width() -> int:
    try:
        return max(shutil.get_terminal_size().columns, 40)
    except Exception:
        return 80


class StatusBar:
    def __init__(
        self, model_fn: Callable[[], str] | str | None = None, cwd: Path | None = None, model: str = ""
    ) -> None:
        if callable(model_fn):
            self._model_fn = model_fn
            self._model_fallback = model or ""
        else:
            self._model_fn = None
            self._model_fallback = model_fn or model or ""
        self.cwd = cwd or Path.cwd()
        self._branch = ""
        self._diff_stats = ""
        self._context_pct: float = 0.0
        self._context_tokens: int = 0
        self._context_max: int = 0
        self._hint = ""
        self._thinking = False
        self._latency: float | None = None
        self._refresh_git()

    def _refresh_git(self) -> None:
        try:
            r = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=3,
                cwd=str(self.cwd),
            )
            self._branch = r.stdout.strip()
        except Exception:
            self._branch = ""
        self._diff_stats = ""
        if self._branch:
            try:
                r = subprocess.run(
                    ["git", "diff", "--shortstat", "--cached"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    cwd=str(self.cwd),
                )
                staged = r.stdout.strip()
                r2 = subprocess.run(
                    ["git", "diff", "--shortstat"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    cwd=str(self.cwd),
                )
                unstaged = r2.stdout.strip()
                added = deleted = 0
                for s in (staged, unstaged):
                    for part in s.split(","):
                        part = part.strip()
                        if "insertion" in part:
                            added += int(part.split()[0])
                        elif "deletion" in part:
                            deleted += int(part.split()[0])
                parts = []
                if added:
                    parts.append(f"+{added}")
                if deleted:
                    parts.append(f"-{deleted}")
                if parts:
                    self._diff_stats = " ".join(parts)
                r3 = subprocess.run(
                    ["git", "rev-list", "--count", "--right-only", "@{u}...HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    cwd=str(self.cwd),
                )
                ahead = r3.stdout.strip()
                if ahead and ahead != "0":
                    self._diff_stats += f" ^ {ahead}"
            except Exception:
                import logging

                logging.getLogger("crux").debug("silent except", exc_info=True)

    def set_context(self, token_count: int, max_tokens: int) -> None:
        self._context_tokens = token_count
        self._context_max = max_tokens
        self._context_pct = (token_count / max_tokens * 100) if max_tokens > 0 else 0.0

    def set_model(self, model: str) -> None:
        self._model_fallback = model

    @property
    def model(self) -> str:
        return (self._model_fn() if self._model_fn else self._model_fallback) or "CRUX"

    def set_hint(self, hint: str) -> None:
        self._hint = hint

    def set_thinking(self, thinking: bool) -> None:
        self._thinking = thinking

    def set_latency(self, seconds: float) -> None:
        self._latency = seconds

    def refresh(self) -> None:
        self._refresh_git()

    def render(self) -> FormattedText:
        model_str = (self._model_fn() if self._model_fn else self._model_fallback) or "CRUX"
        cwd_str = str(self.cwd)
        home = os.path.expanduser("~")
        if cwd_str.startswith(home):
            cwd_str = "~" + cwd_str[len(home) :]

        left = f"{model_str}{' thinking...' if self._thinking else ''}"
        mid = f" {cwd_str}"
        if self._branch:
            mid += f"  {self._branch}"
            if self._diff_stats:
                mid += f" [{self._diff_stats}]"

        right = ""
        if self._latency is not None:
            right = f"ttft: {self._latency:.1f}s"
        # ── 方法论等级 ──
        try:
            from core.methodology import get_methodology_state

            ms = get_methodology_state()
            level_short = {0: "A", 1: "B", 2: "C", 3: "D"}.get(
                {"micro": 0, "normal": 1, "complex": 2, "critical": 3}.get(ms.task_level.value, -1), ""
            )
            if level_short:
                right = f"[{level_short}] " + (right if right else "")
        except (ImportError, OSError):
            pass
        if self._context_max > 0:
            if right:
                right += "  "
            right += f"ctx: {self._context_pct:.0f}%"

        w = _term_width()
        # Truncate mid if content exceeds width
        total = len(left) + len(mid) + len(right) + 2
        if total > w:
            mid = mid[: max(0, w - len(left) - len(right) - 4)] + ".."
        pad = max(1, w - len(left) - len(mid) - len(right))

        pieces = [
            ("class:status-bar-model bold", left),
            ("class:status-bar", mid),
            ("class:status-bar", " " * pad),
            ("class:status-bar-context", right),
        ]
        return FormattedText(pieces)
