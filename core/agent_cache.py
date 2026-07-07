"""Agent cache layer — avoid redundant LLM calls for repeated operations.

Two caches:
1. Decomposition cache: SmartDecomposer results keyed by goal hash.
   When Plan spawns multiple Explore agents for similar tasks, only the first
   one triggers an LLM decomposition call.
2. Exploration cache: file search / glob / grep results with TTL.
   Frequently searched patterns (e.g., "find all test files") are served
   from cache for a short window.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Any

# ── Cache limits ──
MAX_DECOMPOSITIONS = 50  # max cached decomposition results
MAX_EXPLORATIONS = 100  # max cached exploration results
DECOMP_TTL = 300  # 5 min — tasks change slowly
EXPLORE_TTL = 60  # 1 min — files change faster


class AgentCache:
    """In-memory LRU cache with TTL for agent operations."""

    def __init__(self):
        self._decomp: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._explore: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    # ── Decomposition cache ──

    def get_decomposition(self, goal: str, agent_type: str = "") -> Any | None:
        """Get cached decomposition for a goal. Returns None if miss/expired."""
        key = self._decomp_key(goal, agent_type)
        entry = self._decomp.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > DECOMP_TTL:
            del self._decomp[key]
            return None
        # Move to end (LRU)
        self._decomp.move_to_end(key)
        return value

    def set_decomposition(self, goal: str, agent_type: str, value: Any) -> None:
        """Cache a decomposition result."""
        key = self._decomp_key(goal, agent_type)
        self._decomp[key] = (time.time(), value)
        # Evict oldest if over limit
        while len(self._decomp) > MAX_DECOMPOSITIONS:
            self._decomp.popitem(last=False)

    @staticmethod
    def _decomp_key(goal: str, agent_type: str) -> str:
        h = hashlib.sha256(goal.encode()).hexdigest()[:16]
        return f"{agent_type}:{h}"

    # ── Exploration cache ──

    def get_exploration(self, query: str, directory: str = "") -> Any | None:
        """Get cached exploration result. Returns None if miss/expired."""
        key = self._explore_key(query, directory)
        entry = self._explore.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > EXPLORE_TTL:
            del self._explore[key]
            return None
        self._explore.move_to_end(key)
        return value

    def set_exploration(self, query: str, directory: str, value: Any) -> None:
        """Cache an exploration result."""
        key = self._explore_key(query, directory)
        self._explore[key] = (time.time(), value)
        while len(self._explore) > MAX_EXPLORATIONS:
            self._explore.popitem(last=False)

    @staticmethod
    def _explore_key(query: str, directory: str) -> str:
        raw = f"{directory}:{query}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ── Cache stats ──

    def stats(self) -> dict:
        return {
            "decomp_entries": len(self._decomp),
            "explore_entries": len(self._explore),
            "decomp_hits": getattr(self, "_decomp_hits", 0),
            "explore_hits": getattr(self, "_explore_hits", 0),
        }

    def clear(self) -> None:
        self._decomp.clear()
        self._explore.clear()


# ── Global singleton ──
_cache: AgentCache | None = None


def get_cache() -> AgentCache:
    global _cache
    if _cache is None:
        _cache = AgentCache()
    return _cache


def cached_decompose(goal: str, agent_type: str, decompose_fn) -> Any:
    """Decorator: cache decomposition results.

    Usage:
        tasks = cached_decompose(goal, "explore", lambda: self._llm_decompose(goal))
    """
    cache = get_cache()
    cached = cache.get_decomposition(goal, agent_type)
    if cached is not None:
        return cached
    result = decompose_fn()
    cache.set_decomposition(goal, agent_type, result)
    return result


def cached_explore(query: str, directory: str, explore_fn) -> Any:
    """Decorator: cache exploration results.

    Usage:
        files = cached_explore("**/*.py", "src", lambda: glob_files("**/*.py"))
    """
    cache = get_cache()
    cached = cache.get_exploration(query, directory)
    if cached is not None:
        return cached
    result = explore_fn()
    cache.set_exploration(query, directory, result)
    return result
