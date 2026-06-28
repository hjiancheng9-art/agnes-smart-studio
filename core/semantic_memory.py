"""Cross-session semantic memory with automatic context injection.

Upgrades utils/memory.py with compression, preference learning, and
project-context awareness. Designed to be called at session start/end.
"""

import json
import os
import threading
import time
from collections import deque
from pathlib import Path

__all__ = ["MEMORY_FILE", "ROOT", "SemanticMemory", "get_memory", "reset_memory"]

ROOT = Path(__file__).resolve().parent.parent
MEMORY_FILE = ROOT / "output" / "memory.json"


class SemanticMemory:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or MEMORY_FILE
        self._lock = threading.Lock()
        self.data = self._load()
        self._recent_decisions: deque = deque(maxlen=20)

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {"preferences": {}, "decisions": [], "project_context": {}, "corrections": [], "learned_patterns": {}}

    def _save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    def record_decision(self, context: str, choice: str, outcome: str):
        entry = {"ts": time.time(), "context": context[:200], "choice": choice[:200], "outcome": outcome[:200]}
        self.data["decisions"].append(entry)
        if len(self.data["decisions"]) > 100:
            self.data["decisions"] = self.data["decisions"][-100:]
        self._save()

    def record_correction(self, problem: str, fix: str):
        self.data["corrections"].append({"ts": time.time(), "problem": problem[:300], "fix": fix[:300]})
        if len(self.data["corrections"]) > 50:
            self.data["corrections"] = self.data["corrections"][-50:]
        self._save()

    def learn_pattern(self, name: str, pattern: str, replacement: str):
        self.data["learned_patterns"][name] = {"pattern": pattern, "replacement": replacement, "ts": time.time()}
        self._save()

    def set_project_context(self, key: str, value: str):
        self.data["project_context"][key] = value
        self._save()

    def set_preference(self, key: str, value):
        self.data["preferences"][key] = value
        self._save()

    def get_preference(self, key: str, default=None):
        return self.data["preferences"].get(key, default)

    def build_context_injection(self) -> str:
        """Generate text to inject into the system prompt."""
        parts = []

        pref = self.data.get("preferences", {})
        if pref:
            parts.append("## User Preferences\n" + json.dumps(pref, ensure_ascii=False))

        corrections = self.data.get("corrections", [])[-5:]
        if corrections:
            parts.append("## Critical Corrections (do NOT repeat these mistakes)")
            for c in corrections:
                parts.append(f"- Problem: {c['problem']}\n  Fix: {c['fix']}")

        patterns = self.data.get("learned_patterns", {})
        if patterns:
            parts.append("## Learned Code Patterns (apply when relevant)")
            for name, p in list(patterns.items())[-5:]:
                parts.append(f"- {name}: find '{p['pattern'][:60]}' -> replace with '{p['replacement'][:60]}'")

        ctx = self.data.get("project_context", {})
        if ctx:
            parts.append("## Project Context")
            for k, v in ctx.items():
                parts.append(f"- {k}: {v[:200]}")

        return "\n\n".join(parts) if parts else ""


# Global singleton
_memory = SemanticMemory()


def get_memory() -> SemanticMemory:
    return _memory


def reset_memory() -> None:
    """Reset the semantic-memory singleton (test isolation / hot reload).

    SemanticMemory is eagerly instantiated at import. Reassigning a fresh
    instance drops the in-memory state (preferences/decisions/recent queue)
    and re-reads the on-disk store. Callers that imported ``_memory`` by
    value keep their old reference; always go through get_memory() after reset.
    """
    global _memory
    _memory = SemanticMemory()
