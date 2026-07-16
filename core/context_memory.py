# core/context_memory.py
"""Phase 3: Context Compiler + Token Budget Tracker + Three-Tier Memory.

Builds on top of existing ContextManager (core/agent.py) with:

1. TokenBudgetTracker — proactive budget management with warnings/actions
2. WorkingMemory — short-term task context (current file, goal, decisions)
3. EpisodicMemory — compressed summaries of past conversation segments
4. SemanticMemory — long-term persistent facts (wiki-backed)
5. ContextCompiler — orchestrates all four into the LLM context

Design:
- Not a replacement for ContextManager, an enhancement layer
- Each tier has a budget, a summarizer, and a decay strategy
- ContextCompiler assembles the final context from all tiers
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 1. Token Budget Tracker
# ═══════════════════════════════════════════════════════════════════


@dataclass
class BudgetStatus:
    """Current budget status snapshot."""

    used: int = 0
    total: int = 0
    pct: float = 0.0
    warnings: list[str] = field(default_factory=list)
    should_compress: bool = False
    should_alert_user: bool = False
    remaining: int = 0


class TokenBudgetTracker:
    """Track and manage token budget across conversation turns.

    Wraps the existing ContextManager with proactive budget management,
    warnings, and compression triggers.

    Thresholds (configurable):
    - WARN: 70% — log warning
    - ALERT: 85% — yield user-facing warning
    - CRITICAL: 95% — force compression
    """

    def __init__(
        self,
        hard_limit: int = 64000,
        warn_at: float = 0.7,
        alert_at: float = 0.85,
        critical_at: float = 0.95,
    ):
        self.hard_limit = hard_limit
        self.warn_at = warn_at
        self.alert_at = alert_at
        self.critical_at = critical_at
        self._peak_usage: int = 0
        self._compression_count: int = 0

    def check(self, current_tokens: int) -> BudgetStatus:
        """Check current token usage against budget thresholds."""
        pct = current_tokens / self.hard_limit if self.hard_limit > 0 else 0
        status = BudgetStatus(
            used=current_tokens,
            total=self.hard_limit,
            pct=round(pct * 100, 1),
            remaining=max(0, self.hard_limit - current_tokens),
        )

        if current_tokens > self._peak_usage:
            self._peak_usage = current_tokens

        if pct >= self.critical_at:
            status.warnings.append(f"CRITICAL: {pct * 100:.0f}% budget used — forcing compression")
            status.should_compress = True
        elif pct >= self.alert_at:
            status.warnings.append(f"ALERT: {pct * 100:.0f}% budget used — consider reducing context")
            status.should_compress = True
            status.should_alert_user = True
        elif pct >= self.warn_at:
            status.warnings.append(f"WARN: {pct * 100:.0f}% budget used")
            status.should_compress = True

        return status

    def record_compression(self):
        self._compression_count += 1

    @property
    def stats(self) -> dict:
        return {
            "peak_usage": self._peak_usage,
            "compression_count": self._compression_count,
            "hard_limit": self.hard_limit,
        }

    def suggest_next_action(self, status: BudgetStatus) -> str | None:
        """Suggest what to do based on budget status."""
        if status.should_compress and status.pct > 90:
            return "compress_history"
        elif status.should_compress:
            return "summarize_older_turns"
        elif status.remaining < 2000:
            return "reduce_output_detail"
        return None


# ═══════════════════════════════════════════════════════════════════
# 2. Working Memory
# ═══════════════════════════════════════════════════════════════════


@dataclass
class MemoryItem:
    """A single working memory item."""

    key: str
    value: str
    priority: int = 0  # higher = more important
    created_at: float = 0.0
    ttl_seconds: float = 300.0  # 5 min default TTL

    @property
    def expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds


class WorkingMemory:
    """Short-term volatile memory for current task context.

    Stores items like:
    - Current task description
    - File being edited
    - Last tool result summary
    - Active decisions/milestones
    - User preferences for this session

    Items auto-expire by TTL. Priority determines retention under pressure.
    Max items kept; lowest-priority expired items dropped first.
    """

    def __init__(self, max_items: int = 20):
        self._items: dict[str, MemoryItem] = {}
        self.max_items = max_items

    def set(self, key: str, value: str, priority: int = 0, ttl: float = 300.0):
        """Store a working memory item."""
        self._items[key] = MemoryItem(
            key=key,
            value=value,
            priority=priority,
            created_at=time.time(),
            ttl_seconds=ttl,
        )

    def get(self, key: str, default: str = "") -> str:
        """Retrieve a working memory item."""
        item = self._items.get(key)
        if item and not item.expired:
            return item.value
        return default

    def delete(self, key: str):
        self._items.pop(key, None)

    def clear(self):
        self._items.clear()

    def prune(self):
        """Remove expired and lowest-priority items if over limit."""
        time.time()
        # Remove expired
        expired = [k for k, v in self._items.items() if v.expired]
        for k in expired:
            del self._items[k]

        # If still over limit, remove lowest priority non-expired
        if len(self._items) > self.max_items:
            sorted_items = sorted(
                self._items.items(),
                key=lambda x: (x[1].priority, x[1].created_at),
            )
            to_remove = len(sorted_items) - self.max_items
            for k, _ in sorted_items[:to_remove]:
                del self._items[k]

    def snapshot(self) -> str:
        """Return a compact string for LLM context injection."""
        self.prune()
        if not self._items:
            return ""

        lines = ["[Working Memory]"]
        # Sort by priority desc, then by time desc
        sorted_items = sorted(
            self._items.values(),
            key=lambda x: (-x.priority, -x.created_at),
        )
        for item in sorted_items:
            lines.append(f"  {item.key}={item.value[:200]}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {k: {"value": v.value, "priority": v.priority} for k, v in self._items.items()}


# ═══════════════════════════════════════════════════════════════════
# 3. Episodic Memory
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Episode:
    """A compressed summary of a conversation segment."""

    index: int
    summary: str
    turn_count: int
    tools_used: list[str] = field(default_factory=list)
    key_files: list[str] = field(default_factory=list)
    outcome: str = ""  # "success", "failed", "in_progress"
    timestamp: float = 0.0


class EpisodicMemory:
    """Medium-term memory — compressed summaries of past conversation turns.

    When the conversation grows past a threshold:
    1. Older turns are summarized into Episodes
    2. The full history is replaced with the summary
    3. Each Episode tracks: what was done, what tools were used, outcome

    Only the last N episodes are kept (FIFO).
    """

    def __init__(self, max_episodes: int = 10, summarize_every: int = 15):
        self.episodes: list[Episode] = []
        self.max_episodes = max_episodes
        self.summarize_every = summarize_every
        self._next_index = 0

    def add(self, turns: list[dict], tools_used: list[str], key_files: list[str], outcome: str = "in_progress"):
        """Summarize a segment of turns and store as episode."""
        summary = self._summarize_turns(turns)
        episode = Episode(
            index=self._next_index,
            summary=summary,
            turn_count=len(turns),
            tools_used=tools_used,
            key_files=key_files,
            outcome=outcome,
            timestamp=time.time(),
        )
        self._next_index += 1
        self.episodes.append(episode)

        # FIFO eviction
        if len(self.episodes) > self.max_episodes:
            self.episodes.pop(0)

    def _summarize_turns(self, turns: list[dict]) -> str:
        """Simple heuristic summarizer — extracts key info from turn dicts."""
        parts = []
        for t in turns:
            role = t.get("role", "")
            content = str(t.get("content", ""))[:300]
            if role == "user":
                # Extract the first line/question
                first_line = content.split("\n")[0] if content else ""
                if first_line:
                    parts.append(f"Q: {first_line[:150]}")
            elif role == "assistant":
                # Check if contains tool calls
                if "invoke" in content or "tool_call" in content:
                    parts.append("A: [tool calls]")
                elif content:
                    parts.append(f"A: {content[:150]}")
            elif role == "tool":
                parts.append(f"[tool result: {len(content)} chars]")
        return " | ".join(parts[-20:])  # Keep last 20 items max

    def all_episodes_text(self) -> str:
        """Return all episodes as compact text for LLM context."""
        if not self.episodes:
            return ""

        lines = ["[Previous Conversation Summary]"]
        for ep in reversed(self.episodes):  # Most recent first
            outcome_flag = "✓" if ep.outcome == "success" else ("✗" if ep.outcome == "failed" else "→")
            lines.append(f"  #{ep.index} [{outcome_flag}] {ep.summary[:300]}")
            if ep.key_files:
                lines.append(f"     files: {', '.join(ep.key_files[:5])}")
        return "\n".join(lines)

    def snapshot(self) -> str:
        return self.all_episodes_text()

    def to_dict(self) -> list[dict]:
        return [
            {"index": e.index, "summary": e.summary, "tools": e.tools_used, "files": e.key_files, "outcome": e.outcome}
            for e in self.episodes
        ]


# ═══════════════════════════════════════════════════════════════════
# 4. Semantic Memory
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Fact:
    """A persistent fact extracted from conversation."""

    key: str
    value: str
    source: str = ""  # e.g. "read_file", "user_said"
    confidence: float = 1.0  # 0.0-1.0
    created_at: float = 0.0
    tags: list[str] = field(default_factory=list)


class SemanticMemory:
    """Long-term memory — persistent facts backed by wiki/crux_memory.

    Stores:
    - Project structure facts (file locations, module purposes)
    - User preferences (verbosity, style, patterns)
    - Recurring error patterns and fixes
    - Architecture decisions

    Facts are key-value pairs with confidence scores.
    Low-confidence facts are pruned automatically.
    """

    def __init__(self, max_facts: int = 100, persist: bool = True):
        self._facts: dict[str, Fact] = {}
        self.max_facts = max_facts
        self.persist = persist

    def remember(self, key: str, value: str, source: str = "", confidence: float = 1.0, tags: list[str] | None = None):
        """Store a fact."""
        self._facts[key] = Fact(
            key=key,
            value=value,
            source=source,
            confidence=confidence,
            created_at=time.time(),
            tags=tags or [],
        )
        self._prune()

    def recall(self, key: str) -> str:
        """Retrieve a fact by key."""
        fact = self._facts.get(key)
        return fact.value if fact and fact.confidence > 0.3 else ""

    def forget(self, key: str):
        self._facts.pop(key, None)

    def query(self, tag: str) -> list[Fact]:
        """Find all facts matching a tag."""
        return [f for f in self._facts.values() if tag in f.tags]

    def _prune(self):
        """Remove low-confidence facts if over limit."""
        if len(self._facts) <= self.max_facts:
            return
        sorted_facts = sorted(self._facts.items(), key=lambda x: x[1].confidence)
        to_remove = sorted_facts[: len(sorted_facts) - self.max_facts]
        for k, _ in to_remove:
            del self._facts[k]

    def snapshot(self, max_facts: int = 10) -> str:
        """Return top facts as compact text."""
        if not self._facts:
            return ""

        sorted_facts = sorted(self._facts.values(), key=lambda x: -x.confidence)
        lines = ["[Known Facts]"]
        for fact in sorted_facts[:max_facts]:
            lines.append(f"  {fact.key}={fact.value[:150]}")
        if len(sorted_facts) > max_facts:
            lines.append(f"  ... and {len(sorted_facts) - max_facts} more")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {k: {"value": v.value, "confidence": v.confidence, "tags": v.tags} for k, v in self._facts.items()}


# ═══════════════════════════════════════════════════════════════════
# 5. Context Compiler
# ═══════════════════════════════════════════════════════════════════


@dataclass
class CompiledContext:
    """The assembled context from all memory tiers."""

    working_memory: str = ""
    episodic_memory: str = ""
    semantic_memory: str = ""
    budget_status: BudgetStatus | None = None
    total_estimate: int = 0

    def assemble(self, separator: str = "\n\n---\n\n") -> str:
        """Assemble all memory tiers into a single context string."""
        parts = []
        if self.working_memory:
            parts.append(self.working_memory)
        if self.episodic_memory:
            parts.append(self.episodic_memory)
        if self.semantic_memory:
            parts.append(self.semantic_memory)
        return separator.join(parts)

    @property
    def has_content(self) -> bool:
        return bool(self.working_memory or self.episodic_memory or self.semantic_memory)


class ContextCompiler:
    """Orchestrates all three memory tiers + budget tracking.

    Usage in ChatSession:
        self.context_compiler = ContextCompiler()

        # After each turn:
        self.context_compiler.record_turn(user_msg, assistant_msg, tool_results)

        # Before LLM call, inject into system prompt:
        ctx = self.context_compiler.compile()
        if ctx.has_content:
            sys_prompt += "\\n\\n" + ctx.assemble()
    """

    def __init__(
        self,
        hard_token_limit: int = 64000,
        enable_working_memory: bool = True,
        enable_episodic_memory: bool = True,
        enable_semantic_memory: bool = True,
        enable_budget_tracker: bool = True,
    ):
        self.budget = TokenBudgetTracker(hard_limit=hard_token_limit) if enable_budget_tracker else None
        self.working = WorkingMemory() if enable_working_memory else None
        self.episodic = EpisodicMemory() if enable_episodic_memory else None
        self.semantic = SemanticMemory() if enable_semantic_memory else None

        # Internal state for episode creation
        self._turn_buffer: list[dict] = []
        self._tools_this_segment: set[str] = set()
        self._files_this_segment: set[str] = set()
        self._total_turns: int = 0

    def record_turn(self, user_msg: str, assistant_msg: str, tool_calls: list[dict] | None = None):
        """Record a conversation turn for memory management."""
        self._total_turns += 1

        # Buffer for episodic memory
        turn = {
            "role": "user",
            "content": user_msg,
        }
        self._turn_buffer.append(turn)

        if tool_calls:
            turn2 = {"role": "assistant", "content": f"[tool_calls: {len(tool_calls)} calls]", "tool_calls": True}
            self._turn_buffer.append(turn2)
            for tc in tool_calls:
                self._tools_this_segment.add(tc.get("name", "?"))
                for k, v in tc.get("arguments", {}).items():
                    if "path" in k and isinstance(v, str):
                        self._files_this_segment.add(v)
        else:
            turn2 = {"role": "assistant", "content": assistant_msg}
            self._turn_buffer.append(turn2)

        # Check if we should create an episode
        if self.episodic and self._total_turns % self.episodic.summarize_every == 0:
            outcome = "in_progress"
            self.episodic.add(
                turns=self._turn_buffer[-self.episodic.summarize_every * 2 :],
                tools_used=list(self._tools_this_segment),
                key_files=list(self._files_this_segment),
                outcome=outcome,
            )
            self._tools_this_segment.clear()
            self._files_this_segment.clear()

    def track_tool_use(self, tool_name: str, args: dict, result: str, success: bool):
        """Track tool usage for working memory."""
        self._tools_this_segment.add(tool_name)

        # Update working memory with last tool result
        if self.working:
            result_summary = f"{tool_name} -> {'OK' if success else 'FAIL'}"
            self.working.set("last_tool", result_summary, priority=5)

            if "path" in args:
                self.working.set("active_file", str(args["path"]), priority=3)
                self._files_this_segment.add(str(args["path"]))

    def set_current_task(self, task: str):
        """Set the current task description in working memory (highest priority)."""
        if self.working:
            self.working.set("current_task", task, priority=10, ttl=600)

    def compile(self, current_tokens: int = 0) -> CompiledContext:
        """Compile context from all tiers + budget check."""
        ctx = CompiledContext()

        # Budget check
        if self.budget and current_tokens > 0:
            ctx.budget_status = self.budget.check(current_tokens)

        # Working memory
        if self.working:
            ctx.working_memory = self.working.snapshot()

        # Episodic memory
        if self.episodic:
            ctx.episodic_memory = self.episodic.snapshot()

        # Semantic memory (only if there are facts)
        if self.semantic and self.semantic._facts:
            ctx.semantic_memory = self.semantic.snapshot()

        # Estimate total
        ctx.total_estimate = len(ctx.assemble())

        return ctx

    def inject_into_system_prompt(self, system_prompt: str, current_tokens: int = 0) -> str:
        """Inject compiled context into system prompt."""
        ctx = self.compile(current_tokens=current_tokens)
        if ctx.has_content:
            return system_prompt + "\n\n" + ctx.assemble()
        if ctx.budget_status and ctx.budget_status.should_alert_user:
            return system_prompt + f"\n\n[Note: Context usage at {ctx.budget_status.pct:.0f}%]"
        return system_prompt

    @property
    def stats(self) -> dict:
        return {
            "total_turns": self._total_turns,
            "working_memory_items": len(self.working._items) if self.working else 0,
            "episodes": len(self.episodic.episodes) if self.episodic else 0,
            "semantic_facts": len(self.semantic._facts) if self.semantic else 0,
            "budget": self.budget.stats if self.budget else None,
        }
