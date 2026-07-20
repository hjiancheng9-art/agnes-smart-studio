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
from enum import IntEnum
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)


# ─── 工具分层（ChatGPT 评审建议） ───
class ToolTier(IntEnum):
    CORE = 1  # 核心高频工具（读文件、搜索、提交等）
    COMMON = 2  # 常用工具（代码审查、Web获取等）
    SPECIALIZED = 3  # 专用工具（ComfyUI、CDP等）
    EXPERIMENTAL = 4  # 实验性工具


TOOL_CATEGORIES: dict[str, list[str]] = {
    "infra": [
        "read_file",
        "write_file",
        "edit_file",
        "patch_file",
        "run_bash",
        "run_python",
        "search_files",
        "glob_files",
        "list_files",
        "tree_dir",
        "env_check",
    ],
    "creative": [
        "generate_image",
        "generate_video",
        "imagegen",
        "text_to_speech",
        "comfyui_submit_workflow",
        "comfyui_build_custom_workflow",
        "comfyui_status",
    ],
    "code": [
        "run_test",
        "code_review",
        "tdd_run_tests",
        "tdd_cycle",
        "git_add_commit",
        "git_branch",
        "git_push",
        "git_pull",
        "run_lint",
        "run_format",
        "debug_inspect",
    ],
    "web": [
        "web_search",
        "web_fetch",
        "github_search",
        "github_repo_view",
        "pw_navigate",
    ],
    "data": ["db_query"],
    "ai": ["multi_agent", "agent_swarm", "trm_route", "skill_search", "trm_growth"],
}

TOOL_TIERS: dict[str, int] = {
    # Tier 1 - 核心
    "read_file": 1,
    "write_file": 1,
    "edit_file": 1,
    "patch_file": 1,
    "run_bash": 1,
    "run_python": 1,
    "search_files": 1,
    "glob_files": 1,
    "web_search": 1,
    "generate_image": 1,
    "git_add_commit": 1,
    "git_status": 1,
    "git_diff": 1,
    "task_launch": 1,
    "todo_add": 1,
    "todo_list": 1,
    # Tier 2 - 常用
    "generate_video": 2,
    "web_fetch": 2,
    "code_review": 2,
    "run_test": 2,
    "run_lint": 2,
    "run_format": 2,
    "github_search": 2,
    "github_repo_view": 2,
    "github_readme": 2,
    "view_image": 2,
    "comfyui_list_models": 2,
    # Tier 3 - 专用
    "comfyui_submit_workflow": 3,
    "comfyui_build_custom_workflow": 3,
    "multi_agent": 3,
    "agent_swarm": 3,
    "tdd_run_tests": 3,
    "tdd_cycle": 3,
    "mcp_call": 3,
    "mcp_connect": 3,
    "http_request": 3,
    # Tier 4 - 实验性
    "comfyui_create_custom_node": 4,
    "comfyui_lora_prepare": 4,
    "create_pdf": 4,
    "deploy_vercel": 4,
    "comfyui_lora_generate_config": 4,
}

DEFAULT_TIER = 2
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).parent.parent
PYTHON = os.path.expanduser(r"python")

# ── Task categories for routing ────────────────────────────

CATEGORY_META = {
    "search": {"order": [], "desc": "代码探索 / 搜索"},
    "review": {"order": [], "desc": "代码审查"},
    "execute": {"order": [], "desc": "编码实现"},
    "think": {"order": [], "desc": "深度分析 / 架构"},
    "generate": {"order": ["generate_image", "generate_video"], "desc": "媒体生成"},
    "status": {"order": ["*_status"], "desc": "状态检查"},
}


# ═══════════════════════════════════════════════════════════════
# Bridge definitions (what to spawn for discovery)
# ═══════════════════════════════════════════════════════════════

BRIDGES = {
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
    source: str  # "crux" | "codex" | "kimi" | ...
    category: str  # "search" | "review" | "execute" | "think" | "generate" | "status" | "unknown"
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
        # ─── 增强：分层路由（ChatGPT评审建议） ───
        self._tier_scores: dict[str, float] = {}  # tool_name → historical success rate
        self._route_stats: dict[str, dict] = {}  # tool_name → {calls, successes, failures}
        self._callbacks: dict[str, Callable] = {}  # tool_name → async callable
        self._function_map: dict[str, str] = {}  # tool_name → "module.func" import path
        self._discovered = False

    # ── Discovery ──────────────────────────────────────────

    # ── Category mapping: tools.json category → TRM intent ──
    _CATEGORY_TO_INTENT: dict[str, str] = {
        "search": "search",
        "fs": "search",
        "review": "review",
        "code_intel": "review",
        "exec": "execute",
        "file": "execute",
        "git": "execute",
        "deploy": "execute",
        "package": "execute",
        "reasoning": "think",
        "skill": "think",
        "media": "generate",
        "creative": "generate",
        "diagnostic": "status",
        "github": "execute",
        "web": "search",
        "net": "search",
        "document": "execute",
        "browser": "execute",
        "utility": "execute",
        "orchestrate": "execute",
    }

    def _load_tools_json(self) -> int:
        """Load tools from tools.json and register in TRM."""
        tools_json = ROOT / "tools.json"
        if not tools_json.exists():
            return 0
        try:
            data = json.loads(tools_json.read_text(encoding="utf-8"))
            tools_list = data.get("tools", [])
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning("TRM: failed to load tools.json: %s", e)
            return 0

        count = 0
        for t in tools_list:
            name = t.get("name", "")
            if not name:
                continue
            # Map tools.json category → TRM intent
            cat = t.get("category", "unknown")
            intent = self._CATEGORY_TO_INTENT.get(cat, "unknown")
            entry = ToolEntry(
                name=name,
                description=t.get("description", ""),
                source="crux",
                category=intent,
                input_schema=t.get("parameters", {}),
            )
            self._register(entry)
            # Store function import path for _call_tool (Python-type tools only)
            func_path = t.get("function", "")
            tool_type = t.get("type", "python")
            if func_path and tool_type == "python":
                self._function_map[name] = func_path
            count += 1

        # Auto-populate CATEGORY_META routing orders from discovered tools
        # Priority ordering: safe fast tools first, dangerous/slow tools last
        _TOOL_PRIORITY = {
            # execute: safe & fast → dangerous/slow
            "run_bash": 1,
            "run_python": 2,
            "read_file": 3,
            "write_file": 4,
            "edit_file": 5,
            "list_files": 8,
            "git_status": 20,
            "git_diff": 21,
            "git_log": 22,
            "run_test": 90,
            "debug_inspect": 91,
            "orchestrate": 92,
            # search: code search first
            "search_files": 1,
            "grep": 1,
            "glob_files": 2,
            "find_symbol": 3,
            "search_symbols": 4,
            "web_search": 10,
            "web_fetch": 11,
            # Default for unlisted tools
        }
        _DEFAULT_PRIORITY = 50

        for intent_key in CATEGORY_META:
            if not CATEGORY_META[intent_key]["order"]:
                tools_in_intent = [
                    e.name for e in self._tools.values() if e.category == intent_key and e.source == "crux"
                ]
                if tools_in_intent:
                    # Sort by priority (lower = preferred), then alphabetically
                    tools_in_intent.sort(key=lambda n: (_TOOL_PRIORITY.get(n, _DEFAULT_PRIORITY), n))
                    CATEGORY_META[intent_key]["order"] = tools_in_intent

        return count

    def discover_all(self, timeout: float = 30.0) -> int:
        """Scan all bridges + CRUX builtins + tools.json. Returns tool count."""
        self._tools.clear()

        # 1. Register CRUX builtins
        for t in CRUX_BUILTIN_TOOLS:
            entry = ToolEntry(
                name=t["name"],
                description=t.get("description", ""),
                source=t.get("source", "crux"),
                category=t.get("category", "unknown"),
                input_schema=t.get("input_schema", {}),  # pyright: ignore[reportArgumentType]
            )
            self._register(entry)

        # 1.5. Load local tools from tools.json
        self._load_tools_json()

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
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            assert proc.stdin is not None
            assert proc.stdout is not None

            # Initialize handshake
            init_msg = (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "trm", "version": "1.0.0"},
                        },
                    }
                )
                + "\n"
            )

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
            tll_msg = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n"
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
            if "proc" in locals():
                proc.kill()
            return []

    @staticmethod
    def _read_line(proc: subprocess.Popen, timeout: float) -> str | None:
        """Read one line from a subprocess with timeout. Returns None on timeout/error."""
        assert proc.stdout is not None  # guaranteed by PIPE
        result: list[str] = []

        def _reader():
            try:
                line = proc.stdout.readline()  # pyright: ignore[reportOptionalMemberAccess]
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
        if any(kw in combined for kw in ["think", "plan", "analyze", "research", "architect", "design", "deliberat"]):
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

    # ─── 增强：分层工具方法（ChatGPT评审建议） ───

    def get_tier(self, tool_name: str) -> int:
        """获取工具层级（1-4），默认 COMMON(2)"""
        return TOOL_TIERS.get(tool_name, DEFAULT_TIER)

    def get_category(self, tool_name: str) -> str:
        """获取工具分类"""
        for cat, tools in TOOL_CATEGORIES.items():
            if tool_name in tools:
                return cat
        return "other"

    def list_by_tier(self, tier: int) -> list[str]:
        """按层级列出工具"""
        return [name for name in self._tools if self.get_tier(name) == tier]

    def list_by_category(self, category: str) -> list[str]:
        """按分类列出工具"""
        return [name for name in self._tools if self.get_category(name) == category]

    def suggest_tools(
        self, intent_or_spec, max_results: int = 5, session_context: dict | None = None
    ) -> list[tuple[str, float]]:
        """基于意图或 TaskSpec 智能推荐工具（含加权路由升级）。"""
        candidates = []

        # 解析输入 - 如果看起来像 TaskSpec (有 intent_type 属性) 就用，否则当字符串
        if hasattr(intent_or_spec, "intent_type"):
            spec = intent_or_spec
            intent_lower = spec.intent.lower()
            spec_type = spec.intent_type
            spec_output = spec.output_type
        else:
            # 向后兼容：字符串输入
            try:
                from core.task_spec_builder import TaskSpecBuilder

                builder = TaskSpecBuilder()
                spec = builder.build(intent_or_spec, session_context or {})
                intent_lower = intent_or_spec.lower()
                spec_type = spec.intent_type
                spec_output = spec.output_type
            except ImportError:
                intent_lower = intent_or_spec.lower()
                intent_or_spec = intent_lower  # 保持原始字符串
                spec_type = None
                spec_output = None

        for name, entry in self._tools.items():
            tier = self.get_tier(name)
            cat = self.get_category(name)

            score = 0.0
            desc = (entry.description or "").lower()

            # 1. 关键词匹配（基础分）
            for word in intent_lower.split()[:10]:
                if word in desc:
                    score += 0.15

            # 2. 分类匹配（如果 TaskSpec 可用）
            if spec_type is not None:
                # Map enum to expected category using value
                try:
                    expected_cat = {
                        "generate": "creative",
                        "analyze": "code",
                        "modify": "code",
                        "search": "web",
                        "execute": "infra",
                        "review": "code",
                        "diagnose": "code",
                        "deploy": "infra",
                    }.get(spec_type.value, "infra")
                except AttributeError:
                    expected_cat = "infra"

                if cat == expected_cat:
                    score += 0.5
                elif cat == "infra" and expected_cat in ("code", "web"):
                    score += 0.2

            # 3. 输出匹配
            if spec_output == "image" and cat == "creative":
                score += 0.4
            elif spec_output == "code" and cat == "code":
                score += 0.3

            # 4. 层级加权
            tier_weight = 1.0 / tier
            score *= tier_weight

            # 5. 历史成功率
            stats = self._route_stats.get(name, {})
            total_calls = stats.get("calls", 0)
            if total_calls > 0:
                success_rate = stats.get("successes", 0) / total_calls
                score *= 0.5 + 0.5 * success_rate

            candidates.append((name, round(score, 3)))

        candidates.sort(key=lambda x: -x[1])

        # 联动技能市场推荐（v6.0: 工具+技能包联合推荐）
        try:
            from core.skill_recommender import SkillRecommender

            sr = SkillRecommender()
            if spec_type is not None:
                skill_recs = sr.recommend(spec_type.value, top_k=3)
                for skill_name, skill_score in skill_recs:
                    candidates.append(
                        (
                            f"[技能] {skill_name}",
                            round(skill_score / 10, 2),  # 归一化到工具评分范围
                        )
                    )
        except ImportError:
            pass

        candidates.sort(key=lambda x: -x[1])
        return candidates[:max_results]

    def record_call(self, tool_name: str, success: bool):
        """记录工具调用结果，用于路由优化"""
        if tool_name not in self._route_stats:
            self._route_stats[tool_name] = {"calls": 0, "successes": 0, "failures": 0}
        self._route_stats[tool_name]["calls"] += 1
        if success:
            self._route_stats[tool_name]["successes"] += 1
        else:
            self._route_stats[tool_name]["failures"] += 1

    def get_route_stats(self) -> dict:
        """获取路由统计"""
        return dict(sorted(self._route_stats.items(), key=lambda x: -x[1]["calls"])[:20])

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
                tool="",
                source="",
                result=None,
                error=f"Unknown intent: {intent}. Use: {', '.join(CATEGORY_META)}",
                fallback_used=False,
                latency_ms=0,
            )

        # Try GrowthEngine optimized ordering first, merge with static fallback
        candidates = self._get_optimized_candidates(intent, meta["order"])
        # Fallback: use all tools assigned to this category by discovery
        if not candidates:
            candidates = [e.name for e in self._by_category.get(intent, [])]
        # Final fallback: search for tools matching intent prefix
        if not candidates:
            candidates = [n for n in self._tools if n.replace("_", "").startswith(intent) or intent in n.split("_")]
        last_error = ""
        first_tool = candidates[0] if candidates else ""
        _MAX_TOTAL_TIME = 8.0  # max total routing time (local tools are fast)
        _route_start = time.monotonic()

        for tool_name in candidates:
            if time.monotonic() - _route_start > _MAX_TOTAL_TIME:
                last_error = "routing time budget exceeded"
                break

            # Support wildcard matching (*_status, search_*, etc.)
            if "*" in tool_name:
                if tool_name.startswith("*"):
                    suffix = tool_name[1:]
                    matching = [n for n in self._tools if n.endswith(suffix)]
                elif tool_name.endswith("*"):
                    prefix = tool_name[:-1]
                    matching = [n for n in self._tools if n.startswith(prefix)]
                else:
                    # Middle wildcard: convert to regex-like matching
                    import re

                    pattern = re.escape(tool_name).replace(r"\*", ".*")
                    regex = re.compile(f"^{pattern}$")
                    matching = [n for n in self._tools if regex.match(n)]
                if not matching:
                    continue
                tool_name = matching[0]

            entry = self._tools.get(tool_name)
            if entry is None:
                continue

            t0 = time.monotonic()
            result = self._call_tool(tool_name, kwargs)
            latency = (time.monotonic() - t0) * 1000
            success = result is not None and not self._is_error_result(str(result))

            # Record to GrowthEngine for adaptive learning
            try:
                from core.growth_engine import hook_trm_route

                hook_trm_route(intent, tool_name, success=success, latency_ms=latency, source=entry.source)
            except Exception:
                pass  # growth engine is non-critical

            if success:
                return RouteResult(
                    tool=tool_name,
                    source=entry.source,
                    result=result,
                    error="",
                    fallback_used=(tool_name != first_tool),
                    latency_ms=latency,
                )
            last_error = str(result) if result else "no result"

        return RouteResult(
            tool=first_tool,
            source="",
            result=None,
            error=f"All tools failed for intent '{intent}'. Last: {last_error}",
            fallback_used=False,
            latency_ms=0,
        )

    @staticmethod
    def _is_error_result(result_str: str) -> bool:
        """检测工具返回是否为错误 — 基于 CRUX 错误前缀而非子串匹配."""
        if not result_str:
            return True
        # CRUX 工具错误前缀
        error_prefixes = ["[错误]", "[自愈失败]", "[已弃用]"]
        for prefix in error_prefixes:
            if result_str.startswith(prefix):
                return True
        # JSON 错误响应
        if result_str.strip().startswith("{"):
            try:
                data = json.loads(result_str)
                if isinstance(data, dict) and data.get("error"):
                    return True
            except (json.JSONDecodeError, TypeError):
                pass
        return False

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
                if routes.get(intent):
                    persisted = routes[intent]
                    seen = set(persisted)
                    return persisted + [t for t in static_order if t not in seen]
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)

        # 2. Try GrowthEngine live stats
        try:
            from core.growth_engine import get_growth_engine

            ge = get_growth_engine()
            learned = ge.get_route(intent)
            if learned:
                seen = set(learned)
                return learned + [t for t in static_order if t not in seen]
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)

        # 3. Static fallback
        return list(static_order)

    def _call_tool(self, name: str, kwargs: dict) -> Any:
        """Call a tool by name. Returns result or None.

        Priority:
          1. Registered callback
          2. CRUX local function (imported from tools.json function path)
          3. Bridge subprocess (for external tools)
          4. Cache lookup
        """
        # 1. Check callback registry first
        cb = self._callbacks.get(name)
        if cb is not None:
            try:
                return cb(**kwargs)
            except Exception:
                return None

        # 2. Check cache
        cache_key = f"{name}:{json.dumps(kwargs, sort_keys=True, default=str)}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            ts, val = cached
            if time.monotonic() - ts < self._cache_ttl:
                return val
            del self._cache[cache_key]

        # 3. CRUX local tool: import and call the function
        func_path = self._function_map.get(name)
        if func_path:
            try:
                mod_path, func_name = func_path.rsplit(".", 1)
                mod = __import__(mod_path, fromlist=[func_name])
                func = getattr(mod, func_name)
                # Map common intent-level kwargs to function parameters
                import inspect as _inspect

                try:
                    sig = _inspect.signature(func)
                    param_names = set(sig.parameters.keys())
                except (ValueError, TypeError):
                    param_names = set()
                # Build effective kwargs: keep matching, map aliases for missing
                effective = {}
                for k, v in kwargs.items():
                    if k in param_names:
                        effective[k] = v
                # If required params are missing, try to fill from common aliases
                if param_names:
                    required = {
                        n
                        for n, p in sig.parameters.items()
                        if p.default is _inspect.Parameter.empty and n not in effective
                    }
                    if required and not effective:
                        # Try mapping the primary intent kwarg to the first required param
                        primary_val = kwargs.get("query") or kwargs.get("prompt") or kwargs.get("target")
                        if primary_val is not None:
                            for req in sorted(required):
                                effective[req] = primary_val
                                break
                return func(**effective)
            except Exception as e:
                logger.debug("TRM: _call_tool failed for %s: %s", name, e)
                return None

        # 4. For bridge tools, build a bridge call (subprocess)
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
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            )
            assert proc.stdin is not None
            assert proc.stdout is not None

            # Initialize first
            init_msg = (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "trm", "version": "1.0.0"},
                        },
                    }
                )
                + "\n"
            )
            proc.stdin.write(init_msg)
            proc.stdin.flush()

            # Send tools/call
            call_msg = (
                json.dumps(
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": kwargs}}
                )
                + "\n"
            )
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
                    import logging

                    logging.getLogger(__name__).debug("silent except", exc_info=True)

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
            if "proc" in locals():
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
