"""Memory bridge — cross-session persistent memory for CRUX.

Stores key decisions, project context, and user preferences in a local JSON
file. On each new conversation, injects relevant memories as system context.

Structure mirrors Pensyve's entity-based model for future sync compatibility.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("crux.memory")

MEMORY_DIR = Path(__file__).resolve().parent.parent / ".crux_memory"
MEMORY_FILE = MEMORY_DIR / "memory.json"

MAX_MEMORIES = 200


def _ensure_dir() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    _ensure_dir()
    if not MEMORY_FILE.exists():
        return {"memories": [], "stats": {"total_stored": 0, "total_recalled": 0}}
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"memories": [], "stats": {"total_stored": 0, "total_recalled": 0}}


def _save(data: dict) -> None:
    _ensure_dir()
    MEMORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class MemoryBridge:
    """Lightweight persistent memory for CRUX sessions.

    Stores and retrieves facts with entity-scoped namespacing.
    """

    def __init__(self) -> None:
        self._data = _load()
        self._dirty = False

    def remember(self, fact: str, entity: str = "crux-session", metadata: dict | None = None) -> str:
        """Store a fact. Returns memory ID."""
        mem_id = f"mem_{int(time.time())}_{len(self._data['memories'])}"
        entry = {
            "id": mem_id,
            "entity": entity,
            "fact": fact,
            "ts": time.time(),
            "metadata": metadata or {},
        }
        self._data["memories"].append(entry)
        self._data["stats"]["total_stored"] += 1
        # Prune old memories if over limit
        if len(self._data["memories"]) > MAX_MEMORIES:
            self._data["memories"] = self._data["memories"][-MAX_MEMORIES:]
        self._dirty = True
        return mem_id

    def recall(self, query: str, entity: str | None = None, limit: int = 5) -> list[dict]:
        """Search memories by keyword match (simple, no embedding needed)."""
        results = []
        query_lower = query.lower()
        for m in reversed(self._data["memories"]):
            if entity and m.get("entity") != entity:
                continue
            fact = m.get("fact", "")
            if any(word in fact.lower() for word in query_lower.split() if len(word) > 2):
                results.append(m)
            if len(results) >= limit:
                break
        self._data["stats"]["total_recalled"] += 1
        return results

    # Marker prefix for memory system messages — used for in-place dedup.
    _MEMORY_MARKER = "[Memory]"

    def inject_context(self, messages: list[dict], user_input: str) -> None:
        """Insert relevant memories as system context, replacing any prior memory message.

        Previously this inserted a new system message every turn, causing N memory
        messages to accumulate after N turns. Now we find and replace the existing
        memory message in-place, keeping at most one in the history.
        """
        memories = self.recall(user_input)
        # Locate any existing memory message so we can replace or remove it.
        memory_idx: int | None = None
        for i, m in enumerate(messages):
            if m.get("role") == "system" and str(m.get("content", "")).startswith(self._MEMORY_MARKER):
                memory_idx = i
                break
        if not memories:
            # No relevant memories this turn — drop the stale one if present.
            if memory_idx is not None:
                messages.pop(memory_idx)
            return
        ctx_parts = [f"{self._MEMORY_MARKER} Relevant past context:"]
        for m in memories[:3]:
            ctx_parts.append(f"- {m['fact']}")
        ctx = "\n".join(ctx_parts)
        if memory_idx is not None:
            # Replace stale memory message in-place — no growth.
            messages[memory_idx]["content"] = ctx
        else:
            # First time: insert right after the system prompt.
            insert_at = 1 if len(messages) > 1 and messages[0].get("role") == "system" else 0
            messages.insert(insert_at, {"role": "system", "content": ctx})

    def extract_key_facts(self, messages: list[dict]) -> list[str]:
        """Extract potential facts from the last assistant response."""
        for m in reversed(messages):
            if m.get("role") == "assistant":
                content = str(m.get("content", ""))
                # Simple heuristic: lines with decision keywords
                facts = []
                for line in content.split("\n"):
                    low = line.lower()
                    if any(kw in low for kw in ("decision:", "chose ", "selected ", "prefer ", "using ")):
                        facts.append(line.strip()[:200])
                return facts[:3]
        return []

    def flush(self) -> None:
        if self._dirty:
            _save(self._data)
            self._dirty = False
