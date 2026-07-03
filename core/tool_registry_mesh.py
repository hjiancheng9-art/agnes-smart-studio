"""Tool Registry Mesh (TRM) --- unified tool discovery, routing, and caching.

Three layers over the nine-beast MCP mesh:
  1. Registry: auto-discover tools from all bridge servers, build typed index
  2. Router:  map task intent to optimal tool chain with fallback
  3. Cache:   deduplicate identical tool calls, short-lived in-memory

Usage:
    from core.tool_registry_mesh import ToolRegistryMesh

    trm = ToolRegistryMesh()
    trm.discover_all()             # pull tools from all bridges
    trm.print_catalog()            # show full index
    result = trm.route("search", query="payment module")  # auto-select + call
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
PYTHON = os.path.expanduser(
    r"C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe"
)

# ── Task categories for routing ────────────────────────────

CATEGORY_META = {
    "search":    {"order": [],
                  "desc": "代码探索 / 搜索"},
    "review":    {"order": [],
                  "desc": "代码审查"},
    "execute":   {"order": [],
                  "desc": "编码实现"},
    "think":     {"order": [],
                  "desc": "深度分析 / 架构"},
    "generate":  {"order": ["generate_image", "generate_video"],
                  "desc": "媒体生成"},
    "status":    {"order": ["*_status"],
                  "desc": "状态检查"},
}


# ═══════════════════════════════════════════════════════════════
# Bridge definitions (what to spawn for discovery)
# ═══════════════════════════════════════════════════════════════

BRIDGES = {
    "codex": {
        "script": "core/mcp_servers/codex_bridge.py",
    },
    "kimi": {
        "script": "core/mcp_servers/kimi_bridge.py",
    },
    "qoder": {
        "script": "core/mcp_servers/qoder_bridge.py",
    },
    "codebuddy": {
        "script": "core/mcp_servers/codebuddy_bridge.py",
    },
    "zcode": {
        "script": "core/mcp_servers/zcode_bridge.py",
    },
    "claude-code": {
        "script": "core/mcp_servers/claude_code_bridge.py",
    },
}

# CRUX built-in tools (defined in core/chat.py and tools.json)
CRUX_BUILTIN_TOOLS = [
    {
        "name": "generate_image",
        "description": "CRUX AI image generation. Text-to-image, supports size/seed/negative prompt.",
        "category": "generate",
        "source": "crux",
    },
    {
        "name": "generate_video",
        "description": "CRUX AI video generation. Text-to-video with frame/rate/step control.",
        "category": "generate",
        "source": "crux",
    },
    {
        "name": "multi_agent",
        "description": "CRUX multi-agent orchestration. Delegate tasks to sub-agents with role/permission control.",
        "category": "execute",
        "source": "crux",
    },
    {
        "name": "cognitive_deliberate",
        "description": "Multi-model deliberation. Send same question to 2-3 models, synthesize consensus.",
        "category": "think",
        "source": "crux",
    },
]


# ═══════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════

@dataclass
class ToolEntry:
    name: str
    description: str
    source: str           # "crux" | "codex" | "kimi" | ...
    category: str         # "search" | "review" | "execute" | "think" | "generate" | "status" | "unknown"
    input_schema: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str = ""

    @property
    def display(self) -> str:
        cat = self.category
        return f"[{cat}] {self.name} ({self.source})"

    def matches(self, query: str) -> bool:
        q = query.lower()
        return q in self.name.lower() or q in self.description.lower()


@dataclass
class RouteResult:
    tool: str
    source: str
    result: dict | None
    error: str
    fallback_used: bool
    latency_ms: float


# ═══════════════════════════════════════════════════════════════
# Main Registry
# ═══════════════════════════════════════════════════════════════

class ToolRegistryMesh:
    """Central tool registry, router, and cache for the nine-beast mesh."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}  # name → entry
        self._by_category: dict[str, list[ToolEntry]] = {}
        self._by_source: dict[str, list[ToolEntry]] = {}
        self._cache: dict[str, tuple[float, Any]] = {}  # key → (timestamp, result)
        self._cache_maxsize: int = 500
        self._cache_ttl: float = 30.0  # seconds
        self._callbacks: dict[str, Callable] = {}  # tool_name → async callable
        self._discovered = False

    # ── Discovery ──────────────────────────────────────────

    def discover_all(self, timeout: float = 30.0) -> int:
        """Scan all bridges + CRUX builtins. Returns tool count."""
        self._tools.clear()

        # 1. Register CRUX builtins
        for t in CRUX_BUILTIN_TOOLS:
            entry = ToolEntry(
                name=t["name"],
                description=t.get("description", ""),
                source=t.get("source", "crux"),
                category=t.get("category", "unknown"),
                input_schema=t.get("input_schema", {}),
            )
            self._register(entry)

        # 2. Discover from each bridge via MCP initialize + tools/list
        for bridge_id, cfg in BRIDGES.items():
            script = ROOT / cfg["script"]
            if not script.exists():
                continue
            bridge_tools = self._discover_bridge(bridge_id, str(script), timeout=timeout)
            for raw in bridge_tools:
                entry = self._raw_to_entry(raw, bridge_id)
                self._register(entry)

        self._discovered = True
        self._rebuild_indexes()
        return len(self._tools)

    def _discover_bridge(self, bridge_id: str, script: str, timeout: float) -> list[dict]:
        """Spawn a bridge, send initialize + tools/list, return parsed tools."""
        try:
            proc = subprocess.Popen(
                [PYTHON, script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )

            # Initialize handshake
            init_msg = json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "trm", "version": "1.0.0"}}
            }) + "\n"

            try:
                proc.stdin.write(init_msg)
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                proc.kill()
                return []

            # Read initialize response
            init_resp = self._read_line(proc, timeout)
            if not init_resp:
                proc.kill()
                return []

            # tools/list request
            tll_msg = json.dumps({
                "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}
            }) + "\n"
            try:
                proc.stdin.write(tll_msg)
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                proc.kill()
                return []

            # Read tools/list response
            tools_raw = self._read_line(proc, timeout)
            proc.kill()

            if not tools_raw:
                return []

            data = json.loads(tools_raw.strip())
            return data.get("result", {}).get("tools", [])

        except Exception:
            if 'proc' in locals():
                proc.kill()
            return []

    @staticmethod
    def _read_line(proc: subprocess.Popen, timeout: float) -> str | None:
        """Read one line from a subprocess with timeout. Returns None on timeout/error."""
        result: list[str] = []

        def _reader():
            try:
                line = proc.stdout.readline()
                if line:
                    result.append(line)
            except Exception as e:
                logging.debug("MCP response read error: %s", str(e)[:120])

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if t.is_alive() or not result:
            return None
        return result[0]

    def _raw_to_entry(self, raw: dict, source: str) -> ToolEntry:
        name = raw.get("name", "unknown")
        desc = raw.get("description", "")
        schema = raw.get("inputSchema", {})
        category = self._classify(name, desc)
        return ToolEntry(
            name=name,
            description=desc,
            source=source,
            category=category,
            input_schema=schema,
        )

    def _classify(self, name: str, description: str) -> str:
        """Classify a tool into a category based on name + description."""
        combined = (name + " " + description).lower()
        if any(kw in combined for kw in ["search", "explore", "find", "grep", "glob", "read"]):
            return "search"
        if any(kw in combined for kw in ["review", "audit", "inspect"]):
            return "review"
        if any(kw in combined for kw in ["exec", "code", "implement", "write", "edit", "build"]):
            return "execute"
        if any(kw in combined for kw in ["think", "plan", "analyze", "research", "architect",
                                          "design", "deliberat"]):
            return "think"
        if any(kw in combined for kw in ["image", "video", "generate", "create", "render"]):
            return "generate"
        if any(kw in combined for kw in ["status", "login", "check", "health"]):
            return "status"
        return "unknown"

    def _register(self, entry: ToolEntry) -> None:
        if entry.name in self._tools:
            return  # first registered wins
        self._tools[entry.name] = entry

    def _rebuild_indexes(self) -> None:
        self._by_category.clear()
        self._by_source.clear()
        for entry in self._tools.values():
            self._by_category.setdefault(entry.category, []).append(entry)
            self._by_source.setdefault(entry.source, []).append(entry)

    # ── Query ──────────────────────────────────────────────

    def find(self, query: str = "", category: str = "", source: str = "") -> list[ToolEntry]:
        """Find tools matching filters."""
        results = list(self._tools.values())
        if query:
            results = [t for t in results if t.matches(query)]
        if category:
            results = [t for t in results if t.category == category]
        if source:
            results = [t for t in results if t.source == source]
        return results

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    @property
    def categories(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._by_category.items()}

    @property
    def sources(self) -> dict[str, int]:
        return {k: len(v) for k, v in self._by_source.items()}

    # ── Routing ─────────────────────────────────────────────

    def route(self, intent: str, **kwargs) -> RouteResult:
        """Route a task intent to the best available tool.

        Uses GrowthEngine's learned ordering when available,
        falling back to static CATEGORY_META ordering if no data yet.
        Every call is recorded for adaptive optimization.

        intents: "search", "review", "execute", "think", "generate", "status"
        kwargs: passed to the selected tool (query, prompt, target, etc.)

        Returns RouteResult with tool name, source, and result/error.
        Falls back through the category's tool order if primary fails.
        """
        if not self._discovered:
            self.discover_all()

        meta = CATEGORY_META.get(intent)
        if not meta:
            return RouteResult(
                tool="", source="",
                result=None,
                error=f"Unknown intent: {intent}. Use: {', '.join(CATEGORY_META)}",
                fallback_used=False, latency_ms=0,
            )

        # Try GrowthEngine optimized ordering first, merge with static fallback
        candidates = self._get_optimized_candidates(intent, meta["order"])
        last_error = ""
        first_tool = candidates[0] if candidates else ""

        for tool_name in candidates:
            # Support wildcard matching
            if "*" in tool_name:
                prefix = tool_name.replace("*", "")
                matching = [n for n in self._tools if n.startswith(prefix)]
                if not matching:
                    continue
                tool_name = matching[0]

            entry = self._tools.get(tool_name)
            if entry is None:
                continue

            t0 = time.monotonic()
            result = self._call_tool(tool_name, kwargs)
            latency = (time.monotonic() - t0) * 1000
            success = result is not None and "error" not in str(result).lower()

            # Record to GrowthEngine for adaptive learning
            try:
                from core.growth_engine import hook_trm_route
                hook_trm_route(intent, tool_name, success=success,
                               latency_ms=latency, source=entry.source)
            except Exception:
                pass  # growth engine is non-critical

            if success:
                return RouteResult(
                    tool=tool_name, source=entry.source,
                    result=result, error="",
                    fallback_used=(tool_name != first_tool),
                    latency_ms=latency,
                )
            last_error = str(result) if result else "no result"

        return RouteResult(
            tool=first_tool,
            source="",
            result=None,
            error=f"All tools failed for intent '{intent}'. Last: {last_error}",
            fallback_used=False, latency_ms=0,
        )

    @staticmethod
    def _get_optimized_candidates(intent: str, static_order: list[str]) -> list[str]:
        """Merge GrowthEngine learned order + persisted optimized routes.

        Priority:
          1. Persisted optimized_routes.json (auto_tune output)
          2. GrowthEngine live stats ordering
          3. Static CATEGORY_META fallback

        Returns: [optimized tool order]
        """
        # 1. Try persisted optimized config (written by GrowthEngine.auto_tune)
        try:
            config_path = ROOT / ".crux_memory" / "optimized_routes.json"
            if config_path.exists():
                data = json.loads(config_path.read_text(encoding="utf-8"))
                routes = data.get("routes", {})
                if intent in routes and routes[intent]:
                    persisted = routes[intent]
                    seen = set(persisted)
                    return persisted + [t for t in static_order if t not in seen]
        except Exception:
            pass

        # 2. Try GrowthEngine live stats
        try:
            from core.growth_engine import get_growth_engine
            ge = get_growth_engine()
            learned = ge.get_route(intent)
            if learned:
                seen = set(learned)
                return learned + [t for t in static_order if t not in seen]
        except Exception:
            pass

        # 3. Static fallback
        return list(static_order)

    def _call_tool(self, name: str, kwargs: dict) -> Any:
        """Call a tool by name. Returns result or None."""
        # Check callback registry first (for CRUX builtins)
        cb = self._callbacks.get(name)
        if cb is not None:
            try:
                return cb(**kwargs)
            except Exception:
                return None

        # Check cache
        cache_key = f"{name}:{json.dumps(kwargs, sort_keys=True, default=str)}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            ts, val = cached
            if time.monotonic() - ts < self._cache_ttl:
                return val
            del self._cache[cache_key]

        # For bridge tools, build a bridge call (subprocess)
        source = (self._tools.get(name) or ToolEntry(name=name, description="", source="?", category="?")).source
        bridge_cfg = BRIDGES.get(source)
        if bridge_cfg is None:
            return None

        script = ROOT / bridge_cfg["script"]
        if not script.exists():
            return None

        try:
            proc = subprocess.Popen(
                [PYTHON, str(script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace",
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )

            # Initialize first
            init_msg = json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "trm", "version": "1.0.0"}}
            }) + "\n"
            proc.stdin.write(init_msg)
            proc.stdin.flush()

            # Send tools/call
            call_msg = json.dumps({
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": name, "arguments": kwargs}
            }) + "\n"
            proc.stdin.write(call_msg)
            proc.stdin.flush()

            # Read response (skip initialize response, read tools/call response)
            response_lines = []
            for _ in range(2):
                try:
                    line = proc.stdout.readline()
                    if line:
                        response_lines.append(line.strip())
                except Exception:
                    pass

            proc.kill()

            # Parse the last response
            for line in reversed(response_lines):
                try:
                    data = json.loads(line)
                    if "result" in data:
                        result = data["result"]
                        self._cache[cache_key] = (time.monotonic(), result)
                        return result
                    if "error" in data:
                        return {"error": str(data["error"])}
                except json.JSONDecodeError:
                    continue

            return None

        except Exception as e:
            if 'proc' in locals():
                proc.kill()
            return {"error": str(e)}

    def register_callback(self, tool_name: str, callback: Callable) -> None:
        """Register a Python callback for a tool (used by CRUX builtins)."""
        self._callbacks[tool_name] = callback

    # ── Cache ───────────────────────────────────────────────

    def cache_clear(self) -> int:
        n = len(self._cache)
        self._cache.clear()
        return n

    def cache_set(self, key: str, value: Any) -> None:
        if len(self._cache) >= self._cache_maxsize:
            # 淘汰最旧条目（LRU 近似：删除最小的 timestamp）
            oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]
        self._cache[key] = (time.monotonic(), value)

    def cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, val = entry
        if time.monotonic() - ts > self._cache_ttl:
            del self._cache[key]
            return None
        return val

    # ── Display ─────────────────────────────────────────────

    def print_catalog(self) -> None:
        """Print the full tool catalog to stdout."""
        if not self._discovered:
            self.discover_all()

        print(f"\n  TRM Tool Catalog — {self.tool_count} tools across {len(self.sources)} sources\n")
        for cat, tools in sorted(self._by_category.items()):
            print(f"  [{cat}] ({len(tools)} tools)")
            for t in sorted(tools, key=lambda x: x.name):
                desc = t.description[:80].replace("\n", " ")
                print(f"    {t.name:<24s}  ← {t.source:<10s}  {desc}")
            print()
        print(f"  Sources: {self.sources}")
        print(f"  Cache: {len(self._cache)} entries, TTL={self._cache_ttl}s")
        print()

    def as_text(self) -> str:
        """Return catalog as plain text for display."""
        if not self._discovered:
            self.discover_all()

        lines = [f"TRM: {self.tool_count} tools from {len(self.sources)} sources"]
        lines.append(f"Categories: {self.categories}")
        for intent, meta in CATEGORY_META.items():
            available = [t for t in meta["order"] if t in self._tools or "*" in t]
            lines.append(f"  {intent}: {' → '.join(available) if available else '(none)'}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════

_instance: ToolRegistryMesh | None = None


def get_trm() -> ToolRegistryMesh:
    global _instance
    if _instance is None:
        _instance = ToolRegistryMesh()
    return _instance
