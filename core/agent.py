"""Agent infrastructure - Plan execution / Sub-agent / Context compression / Multi-model routing

This module provides the "thinking brain" behind crux-studio:
- ContextManager: token counting + layered auto-compression for long conversations
- PlanExecutor: step-by-step task execution with state machine and dependencies
- SubAgent: independent agent with its own tool-calling loop and session history
- ModelRouter: intelligent model selection based on task type and cost

ModelRouter now unifies two routing paths:
- Heuristic prompt classification (classify_prompt) — for main chat auto-model
- Tier/task-type selection (select / select_for_tier) — for sub-agent dispatch
"""

import json
import logging
import re
import unicodedata
from enum import Enum

logger = logging.getLogger("crux.agent")

__all__ = [
    "COMPRESS_PROMPT",
    "ContextManager",
    "ModelRouter",
    "PLAN_PROMPT",
    "PlanExecutor",
    "PlanStep",
    "SUBAGENT_PROMPT",
    "StepStatus",
    "SubAgent",
    "classify_prompt",
    "compress_messages",
    "parse_plan",
    "spawn_subagent",
]


# ======================================================================
# Context Window Manager
# ======================================================================


class ContextManager:
    """Token counting + layered auto-compression for conversation history.

    Strategy:
    1. Estimate token count per message (no external dependency)
    2. When total exceeds threshold, trigger compression
    3. Preserve: system prompt, recent N messages, user's original messages
    4. Compress: old tool results (truncate), old assistant messages (summarize)
    """

    def __init__(self, max_tokens: int = 60000, preserve_recent: int = 10, preserve_system: bool = True) -> None:
        self.max_tokens = max_tokens
        self.preserve_recent = preserve_recent
        self.preserve_system = preserve_system
        self._summary: str = ""  # accumulated compression summary

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count without external dependencies.

        Heuristic: ~4 chars per token for narrow (ASCII/Latin), ~2 chars
        for wide (CJK, Kana, Hangul, fullwidth). Uses Unicode East Asian
        Width to cover all wide scripts correctly.
        """
        if not text:
            return 0
        wide_count = sum(1 for c in text if unicodedata.east_asian_width(c) in ("W", "F"))
        narrow_count = len(text) - wide_count
        return wide_count // 2 + narrow_count // 4 + 1

    @staticmethod
    def estimate_message_tokens(msg: dict) -> int:
        """Estimate tokens for a single message dict."""
        content = msg.get("content", "")
        if isinstance(content, list):
            # Multimodal: count text parts
            text = " ".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
            content = text
        if not isinstance(content, str):
            content = str(content)

        tokens = ContextManager.estimate_tokens(content)

        # Tool calls add tokens (arguments are separate from content)
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            fn = tc.get("function", {})
            tokens += ContextManager.estimate_tokens(fn.get("arguments", ""))

        return tokens + 4  # message overhead

    def total_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens in the message list."""
        if not messages:
            return 0
        total = 0
        for msg in messages:
            total += self.estimate_message_tokens(msg)
        if self._summary:
            total += self.estimate_tokens(self._summary)
        return total

    def needs_compression(self, messages: list[dict]) -> bool:
        """Check if messages need compression."""
        return self.total_tokens(messages) > self.max_tokens

    def compress(self, messages: list[dict], client, model: str = "") -> list[dict]:
        """Compress conversation history using layered strategy.

        - Never touch system messages
        - Preserve the most recent N messages verbatim (but truncate
          oversized single messages — e.g. tool results returning whole files)
        - Preserve user's original messages (truncate if too long)
        - Summarize old assistant/tool messages
        """
        if not model:
            model = ModelRouter._default_light()
        if len(messages) <= self.preserve_recent + 1:
            return self._truncate_messages(messages)

        # Split messages
        system_msgs = []
        conversation = []

        for msg in messages:
            if msg.get("role") == "system" and self.preserve_system:
                system_msgs.append(msg)
            else:
                conversation.append(msg)

        if len(conversation) <= self.preserve_recent:
            return self._truncate_messages(messages)

        # Messages to compress vs preserve
        to_compress = conversation[: -self.preserve_recent]
        to_keep = conversation[-self.preserve_recent :]

        # Build compression input: extract key info from old messages
        compress_parts = []
        for msg in to_compress:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
                )
            if not isinstance(content, str):
                content = str(content)

            # Preserve user messages more (200 chars), compress others (100 chars)
            max_len = 200 if role == "user" else 100
            if len(content) > max_len:
                content = content[:max_len] + "..."

            # Note tool calls and results
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                tool_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                content += f" [called: {', '.join(tool_names)}]"

            compress_parts.append(f"[{role}] {content}")

        # Use existing summary + new content
        compress_text = "Previous summary:\n" + self._summary + "\n\n" if self._summary else ""
        compress_text += "Compress these conversation turns into a concise summary (max 300 words):\n\n"
        compress_text += "\n".join(compress_parts)

        try:
            r = client.chat(
                model=model,
                messages=[{"role": "user", "content": compress_text}],
                max_tokens=600,
            )
            new_summary = r["choices"][0]["message"]["content"] or ""
            self._summary = new_summary
        except (OSError, ValueError, RuntimeError):
            # Fallback: simple truncation
            self._summary = "\n".join(compress_parts[-10:])

        # Rebuild: system + summary message + recent messages
        # 对最近保留的消息也做单条体量限制，防止工具返回的大文件撑爆上下文
        summary_msg = {
            "role": "system",
            "content": f"[Context Summary]\n{self._summary}",
        }
        return system_msgs + [summary_msg] + self._truncate_messages(to_keep)

    # 单条消息 content 字符上限（超过则截断尾部，保留头部）
    _MAX_MSG_CHARS = 8000

    def _truncate_messages(self, messages: list[dict]) -> list[dict]:
        """截断超大单条消息，防止工具返回的大文件撑爆上下文窗口。

        工具结果（role=tool）常包含整个文件内容，单条可达数百万字符。
        这里保留头部 + 尾部，中间用省略标记，确保关键信息不丢但体量可控。

        实现已委托给 core.context_tools.truncate_messages（单一真源），
        本方法保留为向后兼容入口。head+tail 比例和标记格式由
        context_tools.DEFAULT_MAX_CHARS / truncate_tool_result 统一维护。
        """
        from core.context_tools import truncate_messages

        return truncate_messages(messages, ContextManager._MAX_MSG_CHARS)

    def auto_compress_if_needed(self, messages: list[dict], client, model: str = "") -> list[dict]:
        """Two-tier compression: truncate first (free), LLM summary only if still over.

        Tier 1 (free): _truncate_messages — cap each message at _MAX_MSG_CHARS.
            This alone often resolves token pressure caused by large tool results.
        Tier 2 (costly): full LLM compress — only triggered if tier 1 is insufficient.
        """
        if not model:
            model = ModelRouter._default_light()
        # Tier 1: free truncation (always applied)
        truncated = self._truncate_messages(messages)
        if not self.needs_compression(truncated):
            return truncated

        # Tier 2: LLM compression only if still over threshold
        return self.compress(truncated, client, model)


# ======================================================================
# Plan Execution Engine
# ======================================================================


class StepStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep:
    """A single step in an execution plan."""

    def __init__(
        self,
        name: str,
        purpose: str = "",
        tool: str = "",
        args: dict | None = None,
        depends_on: list[int] | None = None,
    ) -> None:
        self.name = name
        self.purpose = purpose
        self.tool = tool
        self.args: dict = args or {}
        self.depends_on = depends_on or []
        self.status = StepStatus.PENDING
        self.result: str = ""
        self.error: str = ""
        self.retries: int = 0
        self.max_retries: int = 2

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "tool": self.tool,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": self.result[:500] if self.result else "",
            "error": self.error,
        }


class PlanExecutor:
    """Execute a multi-step plan with dependencies, retries, and context passing.

    Usage:
        executor = PlanExecutor(client, tools)
        plan = executor.create_plan("build a web app")
        results = executor.execute(plan)
    """

    def __init__(self, client, tools=None, model: str = "", tier: str = "auto", task_type: str = "") -> None:
        """Init plan executor.

        Args:
            model: 显式模型 ID（空 = 使用活跃供应商模型）
            tier: "auto"/"light"/"pro"/"heavy" — auto 时按 task_type 路由
            task_type: tier=auto 时传给 ModelRouter.select()
        """
        self.client = client
        self.tools = tools
        self.max_steps = 15
        # 未指定 model 时从活跃供应商获取
        if not model:
            try:
                from core.provider import get_provider_manager

                model = get_provider_manager().get_model(tier if tier != "auto" else "pro")
            except (KeyError, ValueError, RuntimeError, OSError) as e:
                logger.warning(
                    "Agent model resolution failed (%s: %s), falling back to deepseek-v4-pro", type(e).__name__, e
                )
                model = "deepseek-v4-pro"
        # tier 路由
        if tier in ("light", "pro", "heavy"):
            self.model = ModelRouter().select_for_tier(tier)
        elif task_type:
            self.model = ModelRouter().select(task_type=task_type)
        else:
            self.model = model

    def create_plan(self, task: str) -> list[PlanStep]:
        """Ask LLM to generate an execution plan, parse into PlanStep list."""
        messages = [
            {"role": "system", "content": PLAN_PROMPT},
            {"role": "user", "content": task},
        ]
        try:
            r = self.client.chat(model=self.model, messages=messages, max_tokens=2048)
            text = r["choices"][0]["message"]["content"] or ""
            return parse_plan(text)
        except (OSError, ValueError, RuntimeError) as e:
            return [PlanStep(name="error", purpose=f"Plan generation failed: {e}")]

    def execute(self, steps: list[PlanStep], on_progress=None) -> list[PlanStep]:
        """Execute steps in order, respecting dependencies.

        Args:
            steps: List of PlanStep objects
            on_progress: Optional callback(step_index, step, status)
        """
        results = []
        context = ""  # Accumulated context from previous steps

        for i, step in enumerate(steps[: self.max_steps]):
            # Check dependencies
            blocked = False
            for dep_idx in step.depends_on:
                if dep_idx - 1 < len(results) and results[dep_idx - 1].status != StepStatus.COMPLETED:
                    step.status = StepStatus.SKIPPED
                    step.error = f"Dependency step {dep_idx} not completed"
                    blocked = True
                    break

            if blocked:
                if on_progress:
                    on_progress(i, step, step.status)
                results.append(step)
                continue

            # Execute step with retry
            step.status = StepStatus.IN_PROGRESS
            if on_progress:
                on_progress(i, step, step.status)

            for attempt in range(step.max_retries + 1):
                try:
                    result = self._execute_step(step, context)
                    step.result = result
                    step.status = StepStatus.COMPLETED
                    step.error = ""
                    # Pass context to next step
                    context += f"\n[Step {i + 1}: {step.name}] Result: {result[:500]}"
                    break
                except (OSError, ValueError, RuntimeError) as e:
                    step.error = str(e)
                    step.retries = attempt + 1
                    if attempt < step.max_retries:
                        continue
                    step.status = StepStatus.FAILED

            if on_progress:
                on_progress(i, step, step.status)
            results.append(step)

        return results

    def _execute_step(self, step: PlanStep, context: str = "") -> str:
        """Execute a single step. If tool is specified, use it; otherwise ask LLM."""
        if step.tool and self.tools and self.tools.has(step.tool):
            # Execute the specified tool
            args = self._infer_tool_args(step, context)
            return self.tools.execute(step.tool, args)
        # Ask LLM to execute
        prompt = f"Execute this step: {step.name}\nPurpose: {step.purpose}\n"
        if context:
            prompt += f"\nPrevious context:\n{context[:2000]}\n"
        prompt += "\nProvide the result directly."

        r = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        return r["choices"][0]["message"]["content"] or "[no output]"

    def _infer_tool_args(self, step: PlanStep, context: str) -> dict:
        """Try to infer tool arguments from step purpose and context."""
        # Simple heuristic: try to extract key-value pairs from purpose
        args = {}
        for match in re.finditer(r"(\w+)[:=]\s*(\S+)", step.purpose):
            args[match.group(1)] = match.group(2).strip("\"'")
        return args

    def get_summary(self, results: list[PlanStep]) -> str:
        """Generate a human-readable summary of execution results."""
        lines = []
        for i, step in enumerate(results):
            status_icon = {
                StepStatus.COMPLETED: "[OK]",
                StepStatus.FAILED: "[FAIL]",
                StepStatus.SKIPPED: "[SKIP]",
                StepStatus.PENDING: "[ ]",
                StepStatus.IN_PROGRESS: "[...]",
            }.get(step.status, "[?]")
            lines.append(f"{status_icon} Step {i + 1}: {step.name}")
            if step.result:
                lines.append(f"    Result: {step.result[:200]}")
            if step.error:
                lines.append(f"    Error: {step.error}")
        return "\n".join(lines)


# ======================================================================
# Sub-Agent with Tool Calling Loop
# ======================================================================


class SubAgent:
    """An independent sub-agent with its own session history and tool-calling loop.

    Unlike the old spawn_subagent(), this agent can:
    - Execute tools in a loop (up to max_rounds)
    - Maintain independent conversation history
    - Report results back to the parent
    """

    def __init__(
        self,
        client,
        tools=None,
        model: str = "",
        max_rounds: int = 5,
        tier: str = "auto",
        task_type: str = "",
    ) -> None:
        """Init sub-agent.

        Args:
            model: 显式模型 ID（空字符串 = 使用活跃供应商的 pro 模型）
            tier: "auto" / "light" / "pro" / "heavy" — auto 时按 task_type 路由
            task_type: 传给 ModelRouter.select() 的任务类型（tier=auto 时生效）
        """
        self.client = client
        self.tools = tools
        self.max_rounds = max_rounds
        self.history: list[dict] = []
        self.context_mgr = ContextManager(max_tokens=20000)
        self._session_approved: set[str] = set()  # high-risk tools auto-approved for this session
        # 如果没指定 model，从活跃供应商获取
        if not model:
            try:
                from core.provider import get_provider_manager

                model = get_provider_manager().get_model(tier if tier != "auto" else "pro")
            except Exception:
                model = "deepseek-v4-pro"  # 最终 fallback
        # tier 路由
        if tier in ("light", "pro", "heavy"):
            router = ModelRouter()
            self.model = router.select_for_tier(tier)
        elif task_type:
            router = ModelRouter()
            self.model = router.select(task_type=task_type)
        else:
            self.model = model

    def run(self, task: str, system_prompt: str = "") -> str:
        """Execute a task with tool-calling loop.

        Returns the final text result.
        """
        if not system_prompt:
            system_prompt = SUBAGENT_PROMPT.format(task=task)

        self.history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        tool_defs = None
        if self.tools and self.tools.definitions:
            tool_defs = self.tools.definitions

        for _round_num in range(self.max_rounds):
            # Auto-compress if needed
            self.history = self.context_mgr.auto_compress_if_needed(self.history, self.client)

            try:
                r = self.client.chat(
                    model=self.model,
                    messages=self.history,
                    max_tokens=4096,
                    tools=tool_defs,
                )
            except (OSError, ValueError, RuntimeError) as e:
                return f"[SubAgent error] {e}"

            msg = r["choices"][0]["message"]
            self.history.append(msg)

            # Check if model wants to call tools
            tool_calls = msg.get("tool_calls", [])
            if not tool_calls:
                # No tool calls - return the text response
                return msg.get("content", "")

            # Execute each tool call
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                tool_args_str = fn.get("arguments", "{}")

                try:
                    tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                except json.JSONDecodeError:
                    tool_args = {}

                # Execute tool
                if self.tools and self.tools.has(tool_name):
                    # 高风险守卫：SubAgent 无法弹确认框，命中即拒绝
                    # 与 chat.py._dispatch_tool 的 _HIGH_RISK_TOOLS 对齐
                    _HIGH_RISK = {
                        "git_add_commit",
                        "git_push",
                        "git_pr_create",
                        "git_pr_merge",
                    }
                    is_risky = tool_name in _HIGH_RISK or (
                        tool_name == "github_write_file" and not tool_args.get("branch", "").strip()
                    )
                    if is_risky:
                        result = (
                            f"[安全拦截] 工具 '{tool_name}' 属高风险写操作，"
                            "SubAgent 自主循环不允许执行，请由主会话确认后调用。"
                        )
                    else:
                        result = self.tools.execute(tool_name, tool_args)
                else:
                    result = f"[Error] Unknown tool: {tool_name}"

                # Add tool result to history
                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": result[:4000],  # Truncate long results
                    }
                )

        return "[SubAgent] Max rounds reached without final answer."


# ======================================================================
# Multi-Model Intelligent Router
# ======================================================================


# ── Heuristic prompt classification (for main chat auto-model) ──

_CODE_SIGNALS = re.compile(
    r"```|import\s+\w+|def\s+\w+|class\s+\w+|"
    r"Traceback|Error:|Exception|"
    r"\.py\b|\.js\b|\.ts\b|\.go\b|\.rs\b|"
    r"function|component|hook|api|endpoint|"
    r"bug|fix|debug|refactor|test|commit|"
    r"error|crash|fail|broken|"
    r"函数|类\b|模块|接口|错误|异常|修复|提交|测试|重构|"
    r"代码|实现|写|改|加|补|删|优化|拆分",
    re.IGNORECASE,
)

_STRONG_REASONER = re.compile(
    r"security\s+(?:audit|review|assessment|hole|flaw|vulnerability)|"
    r"threat\s+model|attack\s+(?:surface|vector|tree)|"
    r"architecture\s+(?:design|review|decision)|"
    r"architect\s+(?:a\s+)?(?:new|system|solution|pattern)|"
    r"refactor\s+(?:across|entire|whole)|"
    r"event\s+sourcing|CQRS|domain[\s-]?driven|"
    r"comprehensive\s+(?:review|audit|analysis)|"
    r"root\s+cause|diagnose\s+(?:this|the|why)|"
    r"database\s+(?:schema|migration|design|architecture)|"
    r"investigate\s+(?:this|the|why|how)|"
    r"optimize\s+(?:.*\s)?performance|"
    r"架构\s*(?:设计|审查|决策|重构)|"
    r"安全\s*(?:审计|漏洞|审查|扫描)|"
    r"(?:全面|深度|彻底|详细)\s*(?:审查|分析|检查|方案)|"
    r"性能\s*(?:优化|调优|瓶颈)|"
    r"数据库\s*(?:设计|迁移|架构)|"
    r"根因|底层原因|排查|"
    r"内存\s*泄漏|OOM|死循环|"
    r"分析\s*(?:这段|这个|代码|为什么|原因)|"
    # 浏览器 / CDP / GPT 操作 — 需要完整工具链
    r"\bgpt\b|chatgpt|cdp|ask_chatgpt|"
    r"pw_navigate|cdp_ask|cdp_session|"
    r"浏览器\s*(?:操作|控制|自动化|连接|打开)|"
    r"(?:打开|启动|使用)\s*浏览器|"
    r"(?:连[接上]|操控|打开|控制)\s*gpt|"
    r"edge\s*cdp|playwright|"
    r"网页\s*(?:操作|控制|自动化|打开)",
    re.IGNORECASE,
)

_MODERATE_REASONER = re.compile(
    r"architect(?:ure|ural)?\b|"
    r"design\s+(?:system|pattern|decision|doc|spec)|"
    r"multi[\s-]?file|"
    r"refactor|"
    r"security\s+vulnerability|"
    r"why\s+(?:.*\s)?(?:fail|crash|break|wrong)|"
    r"\bmath\b|algorithm\s+(?:design|analysis|complexity|ic)|"
    r"proof|prove\s+(?:that|it|the|this)|"
    r"distributed|concurrent|race\s+condition|deadlock|"
    r"scal(?:e|able|ability)\b|throughput|latency|"
    r"migrat(?:e|ion)\s+(?:plan|strategy|to|from)|"
    r"upgrade\s+.*major|breaking\s+change|"
    r"deep\s+(?:dive|analysis)\b|"
    r"设计\s*(?:方案|模式|系统)|"
    r"算法|排序|搜索|加密|解密|"
    r"为什么\s*(?:失败|崩溃|出错|不对)|"
    r"多\s*(?:文件|模块|服务)|"
    r"重构\s*(?:整个|全面|大|代码)|"
    r"迁移\s*(?:计划|方案|到)|"
    r"并发|死锁|扩展|吞吐|延迟",
    re.IGNORECASE,
)

_LIGHT_SIGNALS = re.compile(
    r"^(?:what\s+is|who\s+is|when\s+|where\s+|"
    r"how\s+(?:do|to|can)\s+I\s+|"
    r"show\s+me|list\s+|find\s+|search\s+|grep\s+|"
    r"explain\s+(?:this|what)|what\s+does|meaning\s+of|"
    r"definition\s+of|example\s+of|"
    r"\bformat\b|\bconvert\b|\btranslate\b|"
    r"run\s+(?:the\s+)?(?:test|pytest|smoke|check|lint))",
    re.IGNORECASE,
)

_LIGHT_COMMANDS = re.compile(
    r"^(?:run|执行|跑)\s*(?:测试|test|smoke|check|lint)|"
    r"^(?:format|lint|sort|organize)\s",
    re.IGNORECASE,
)


def _count_matches(pattern: re.Pattern, text: str) -> int:
    """Count non-overlapping matches of pattern in text."""
    return sum(1 for _ in pattern.finditer(text))


def _resolve_tier_from_dict(tier: str, provider_models: dict[str, str]) -> str:
    """Map a tier to an actual model ID from a provider's model dict.

    Search order tries exact tier first, then falls back through canonical tiers.
    Normalizes 'reasoner' to look for 'reasoner' key, then 'heavy', then 'pro', etc.
    """
    # Build search order: exact tier, then canonical fallback chain
    search_order = [tier]
    if tier == "reasoner":
        search_order += ["heavy", "pro", "light"]
    elif tier == "heavy":
        search_order += ["pro", "light"]
    elif tier == "pro":
        search_order += ["light", "heavy", "reasoner"]
    elif tier == "light":
        search_order += ["pro", "heavy"]
    else:
        search_order += ["pro", "light", "heavy", "reasoner"]

    for t in search_order:
        if t in provider_models:
            return provider_models[t]
    if provider_models:
        return next(iter(provider_models.values()))
    return "unknown"


class ModelRouter:
    """Unified model selection — prompt heuristics + task-type routing + tier dispatch.

    三级 tier 路由（对标 Claude Haiku/Sonnet/Opus 分层）:
    - light tier (≈ Haiku):  机械任务，最便宜 — 搜索/读文件/grep/格式化/简单对话
    - pro tier (≈ Sonnet):   中等复杂度 — 单文件修改/写测试/tool calling
    - heavy tier (≈ Opus):   深度推理 — 架构设计/多文件分析/安全审查

    视觉通道独立，不受 tier 切换影响。
    """

    # 三级 tier 常量 — 对标 Claude 的 haiku/sonnet/opus
    TIER_LIGHT = "light"
    TIER_PRO = "pro"
    TIER_HEAVY = "heavy"
    TIER_REASONER = "reasoner"  # 同 heavy，语义更明确（用于 prompt 分类）

    # Model metadata now in core.provider.MODEL_REGISTRY (single source of truth)

    def __init__(self, primary: str | None = None, light: str = "", pro: str = "", vision_model: str = "") -> None:
        if primary is None:
            primary = self._default_primary()
        if not light:
            light = self._default_light()
        if not pro:
            pro = self._default_pro()
        if not vision_model:
            vision_model = self._default_vision()
        self.primary = primary  # heavy tier（深度推理/长上下文）
        self.light = light  # light tier（机械任务，动态跟随 active provider）
        self.pro = pro  # pro tier（日常编码 tool calling，动态跟随 active provider）
        self.vision_model = vision_model  # 跟随 models.json vision_models 配置
        self._fallback_chain = self._build_fallback_chain()
        # Session tracking for auto-model mode
        self.switch_count: int = 0
        self.last_tier: str = "pro"
        self.tier_stats: dict[str, int] = {"light": 0, "pro": 0, "heavy": 0}

    # ── Heuristic prompt classification (auto-model) ──────────

    # ── Enhanced complexity signals (HybridRouter P0) ──────────

    _HEAVY_PAT = re.compile(
        r"(架构|路线图|根因|多文件|全局|系统性|评审|fallback|router|"
        r"traceback|stack\s*trace|pytest|CI|workflow|TUI|prompt_toolkit|"
        r"security\s+(?:audit|review|assessment|hole|flaw|vulnerability)|"
        r"threat\s+model|attack\s+(?:surface|vector|tree)|"
        r"architecture\s+(?:design|review|decision)|"
        r"migrat(?:e|ion)\s+(?:plan|strategy|方案)|"
        r"重构\s*(?:跨模块|整个项目|全部|架构|系统)|"
        r"并发|死锁|扩展|吞吐|延迟|安全审查)",
        re.IGNORECASE,
    )

    _TRIVIAL_SET: frozenset[str] = frozenset({
        "你好", "hello", "hi", "hey", "在吗", "在不在", "谢谢", "thanks",
        "ok", "好的", "okay", "嗯", "哦", "好", "行", "可以",
    })

    @staticmethod
    def _is_trivial(prompt: str) -> bool:
        s = prompt.strip().lower()
        return len(s) <= 20 and s in ModelRouter._TRIVIAL_SET

    @staticmethod
    def _is_heavy(prompt: str) -> bool:
        return (
            len(prompt) > 1800
            or len(re.findall(r"```|\.py\b|Traceback|Exception", prompt)) >= 2
        )

    @staticmethod
    def _is_pro(prompt: str) -> bool:
        return len(prompt) > 600

    @staticmethod
    def classify_prompt(prompt: str, ctx: dict | None = None) -> str:
        """Classify a user prompt into model tier.

        Enhanced (P0): vision input → vision tier; trivial greetings → fallback;
        complex code/arch → heavy; moderate → pro; else → light.

        Returns one of: 'light', 'pro', 'heavy', 'vision', 'fallback'. Never raises.
        """
        ctx = ctx or {}
        if ctx.get("has_image_input"):
            return "vision"

        if not prompt or not isinstance(prompt, str):
            return "pro"

        stripped = prompt.strip()
        length = len(stripped)

        # Trivial greeting / short simple question → fallback tier
        if ModelRouter._is_trivial(prompt):
            return "fallback"

        # Light commands: explicit test/format/lint invocations → light tier
        if _LIGHT_COMMANDS.search(stripped):
            return "light"

        # Heavy tier: HEAVY_PAT (Chinese + English complex keywords)
        if ModelRouter._HEAVY_PAT.search(stripped):
            return "heavy"

        # Heavy tier: long context or multiple traceback/exception signals
        if ModelRouter._is_heavy(stripped):
            return "heavy"

        # Strong reasoner regex from original (architecture, security, etc.)
        strong_hits = _count_matches(_STRONG_REASONER, stripped)
        if strong_hits >= 1:
            return "heavy"

        # Pro tier: moderate complexity (length > 600 chars with code signals)
        if ModelRouter._is_pro(stripped):
            return "pro"

        moderate_hits = _count_matches(_MODERATE_REASONER, stripped)
        if moderate_hits >= 2:
            return "heavy"
        if moderate_hits >= 1 and length > 400:
            return "heavy"

        code_hits = _count_matches(_CODE_SIGNALS, stripped)
        if code_hits >= 5 and length > 300:
            return "heavy"
        if code_hits >= 1 or length >= 30:
            return "pro"

        # Light: very short or pure command
        if length < 30 and not _CODE_SIGNALS.search(stripped) and not _STRONG_REASONER.search(stripped):
            return "light"
        if _LIGHT_COMMANDS.search(stripped):
            return "light"
        if _LIGHT_SIGNALS.search(stripped) and length < 200:
            has_code = _CODE_SIGNALS.search(stripped)
            if has_code:
                code_match = has_code.group()
                if code_match in (".py", ".js", ".ts", ".go", ".rs"):
                    has_code = False
            if not has_code and not _MODERATE_REASONER.search(stripped):
                return "light"

        return "pro"

    def classify_and_track(self, prompt: str) -> str:
        """Classify prompt and update session stats. Returns tier string."""
        tier = self.classify_prompt(prompt)
        self.tier_stats[tier] = self.tier_stats.get(tier, 0) + 1
        if tier != self.last_tier:
            self.switch_count += 1
            self.last_tier = tier
        return tier

    def resolve_model(self, tier: str, provider_models: dict[str, str] | None = None) -> str:
        """Map a tier to an actual model ID.

        Args:
            tier: 'light' / 'pro' / 'reasoner' / 'heavy' / 'vision' / 'fallback'
            provider_models: optional dict like {'light': '...', 'pro': '...', 'reasoner': '...'}
                            If None, uses self.light / self.pro / self.primary.

        Falls back through _resolve_tier_from_dict chain.
        """
        if provider_models:
            return _resolve_tier_from_dict(tier, provider_models)

        # Use internal model assignments (normalize reasoner→heavy)
        resolved_tier = "heavy" if tier == "reasoner" else tier
        tier_map = {
            "light": self.light,
            "pro": self.pro,
            "heavy": self.primary,
            "vision": self.vision_model,
            "fallback": self.light,
        }
        return tier_map.get(resolved_tier, self.primary)

    def resolve_route(self, tier: str) -> dict[str, str]:
        """Resolve tier → {provider, model} using models.json tiers config (P0).

        New hybrid routing: reads tiers from models.json to determine which
        provider+model combo serves each tier, enabling cross-provider routing.
        Falls back to self.resolve_model() if tiers config is absent.
        """
        try:
            import json
            from pathlib import Path

            cfg_path = Path(__file__).parent.parent / "models.json"
            cfg = json.loads(cfg_path.read_text("utf-8"))
            tiers_cfg = cfg.get("tiers", {})
            if tier in tiers_cfg:
                return dict(tiers_cfg[tier])
        except (OSError, json.JSONDecodeError, KeyError):
            pass

        # Fallback: use internal assignments (pre-hybrid behavior)
        model_id = self.resolve_model(tier)
        return {"provider": "unknown", "model": model_id}

    # ── Task-type routing (sub-agent dispatch) ──────────────────

    def select(
        self,
        task_type: str = "",
        needs_tools: bool = False,
        needs_vision: bool = False,
        needs_thinking: bool = False,
        needs_long_context: bool = False,
    ) -> str:
        """Select the best model for the task.

        Args:
            task_type: "chat", "code", "reasoning", "image_generation", etc.
            needs_tools: Whether tool calling is required
            needs_vision: Whether image understanding is required
            needs_thinking: Whether deep reasoning is required
            needs_long_context: Whether 1M+ token context is needed
        """
        # 媒体生成：CRUX 模型
        # 注意：文本对话供应商（如 deepseek）不参与媒体生成路由
        if task_type == "image_generation":
            try:
                from core.provider import get_provider_manager

                mgr = get_provider_manager()
                crux = mgr.providers.get("crux", {})
                return crux.get("models", {}).get("image") or "agnes-image-2.1-flash"
            except Exception as e:
                logger.debug("unexpected error: %s", e, exc_info=True)

                return "agnes-image-2.1-flash"
        if task_type == "video_generation":
            try:
                from core.provider import get_provider_manager

                mgr = get_provider_manager()
                crux = mgr.providers.get("crux", {})
                return crux.get("models", {}).get("video") or "agnes-video-v2.0"
            except Exception as e:
                logger.debug("unexpected error: %s", e, exc_info=True)

                return "agnes-video-v2.0"

        # Vision requirement — 独立通道
        if needs_vision:
            return self.vision_model

        # Long context → primary (1M context)
        if needs_long_context:
            return self.primary

        # Tools + thinking → primary (need capable model)
        if needs_tools and needs_thinking:
            return self.primary

        # Tools only, no deep thinking → light model
        if needs_tools and not needs_thinking:
            return self.light

        # Thinking but no tools → primary
        if needs_thinking:
            return self.primary

        # Task type routing
        type_map = {
            # ── light tier ──
            "chat": self.light,
            "simple_qa": self.light,
            "summarize": self.light,
            "search": self.light,
            "read_file": self.light,
            "format": self.light,
            "tool_calling": self.light,
            # ── vision ──
            "vision": self.vision_model,
            # ── heavy tier ──
            "code": self.primary,
            "reasoning": self.primary,
            "planning": self.primary,
            "agent": self.primary,
            "architecture": self.primary,
            "security": self.primary,
        }
        if task_type in type_map:
            return type_map[task_type]

        return self.primary

    def select_for_tier(self, tier: str) -> str:
        """按三级 tier 直接选模型（对标 Claude Haiku/Sonnet/Opus）。

        Args:
            tier: "light" / "pro" / "heavy"（或 "auto"）
        Returns:
            模型 ID。auto 时退回 self.primary（heavy tier）。

        tier 映射（v6.0 统一路由）:
        - light:    light 模型（机械任务/简单对话，最便宜）
        - pro:      pro 模型（编码/工具调用/日常推理）
        - heavy:    heavy 模型（深度思考 + 大上下文）
        """
        if tier in (self.TIER_LIGHT,):
            return self.light
        if tier in (self.TIER_PRO,):
            return self.pro
        if tier in (self.TIER_HEAVY, self.TIER_REASONER):
            return self.primary
        # auto / unknown → 主力模型（最稳）
        return self.primary

    @staticmethod
    def _default_primary() -> str:
        """从 models.json active provider 读 pro 模型，读不到退回 deepseek-v4-pro。"""
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            return mgr.get_model("pro") or "deepseek-v4-pro"
        except (ImportError, OSError, RuntimeError):
            return "deepseek-v4-pro"

    @staticmethod
    def _default_light() -> str:
        """从 models.json active provider 读 light 模型，读不到退回 deepseek-v4-flash。"""
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            return mgr.get_model("light") or "deepseek-v4-flash"
        except (ImportError, OSError, RuntimeError):
            return "deepseek-v4-flash"

    @staticmethod
    def _default_pro() -> str:
        """从 models.json active provider 读 pro 模型，读不到退回 deepseek-v4-flash。"""
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            return mgr.get_model("pro") or "deepseek-v4-flash"
        except (ImportError, OSError, RuntimeError):
            return "deepseek-v4-flash"

    @staticmethod
    def _default_vision() -> str:
        """优先用 CRUX 视觉模型（计数/OCR/细节识别最优），其次智谱兜底。"""
        try:
            import os

            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            mgr.load()
            # 优先 CRUX 视觉模型（检查 models.json + 环境变量）
            crux = mgr.providers.get("crux", {})
            crux_key = crux.get("api_key") or os.getenv("CRUX_API_KEY") or os.getenv("AGNES_API_KEY")
            if crux_key:
                return crux.get("models", {}).get("pro") or "agnes-2.0-flash"
            # 其次智谱视觉模型
            zhipu = mgr.providers.get("zhipu", {})
            zhipu_vmodels = zhipu.get("vision_models", {})
            if zhipu_vmodels:
                return zhipu_vmodels.get("pro") or zhipu_vmodels.get("light") or next(iter(zhipu_vmodels.values()))
            return "GLM-4V-Flash"
        except (ImportError, OSError, RuntimeError):
            return "GLM-4V-Flash"

    def _build_fallback_chain(self) -> list[str]:
        """动态构建 fallback 链：免费优先，付费兜底。

        每个 provider 收集 pro + light 模型，按 cost_tier 排序。
        """
        chain: list[str] = []
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            seen: set[str] = set()

            # Sort: free providers first, then by fallback priority
            def _sort_key(pid):
                p = mgr.providers.get(pid, {})
                is_free = 0 if p.get("cost_tier") == "free" else 1
                try:
                    idx = mgr.fallback_priority.index(pid)
                except ValueError:
                    idx = 99
                return (is_free, idx)

            sorted_pids = sorted(mgr.fallback_priority, key=_sort_key)
            for pid in sorted_pids:
                provider = mgr.providers.get(pid, {})
                models = provider.get("models", {})
                for tier_key in ("pro", "light"):
                    mid = models.get(tier_key, "")
                    if mid and isinstance(mid, str) and mid not in seen:
                        chain.append(mid)
                        seen.add(mid)
                for mid_val in models.values():
                    if isinstance(mid_val, str) and mid_val not in seen:
                        chain.append(mid_val)
                        seen.add(mid_val)
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("fallback skipped: %s", e)

            pass
        return chain or ["deepseek-v4-pro", "deepseek-v4-flash"]

    def get_fallback(self, failed_model: str) -> str | None:
        """Get the next model in the fallback chain."""
        try:
            idx = self._fallback_chain.index(failed_model)
            if idx + 1 < len(self._fallback_chain):
                return self._fallback_chain[idx + 1]
        except ValueError:
            pass
        return None

    def with_fallback(self, client, **chat_kwargs) -> dict:
        """Call client.chat with automatic fallback on failure."""
        model = chat_kwargs.get("model", self.primary)
        last_error = None

        while model:
            try:
                chat_kwargs["model"] = model
                return client.chat(**chat_kwargs)
            except (OSError, ValueError, RuntimeError) as e:
                last_error = e
                next_model = self.get_fallback(model)
                if next_model and next_model != model:
                    model = next_model
                else:
                    break

        if last_error is not None:
            raise last_error
        raise RuntimeError("Retry loop exhausted with no exception captured")


# Module-level shortcut for backward compatibility
def classify_prompt(prompt: str) -> str:
    """Module-level shortcut for ModelRouter.classify_prompt."""
    return ModelRouter.classify_prompt(prompt)


# ======================================================================
# Plan prompt and parse_plan (kept for backward compatibility)
# ======================================================================

PLAN_PROMPT = """You are a task planner. Output JSON:

```json
{"steps": [{"name": "...", "purpose": "...", "tool": "tool_name", "args": {}, "depends_on": []}]}
```

Rules: steps in execution order, max 10, depends_on is 0-based indices. args must be valid JSON."""


def parse_plan(text: str) -> list[PlanStep]:
    """Parse execution plan from LLM JSON output. Tries ```json``` block first, then raw JSON."""
    import json as _json

    json_text = ""
    match = re.search(r"```(?:json)?\s*\n(.+?)```", text, re.DOTALL)
    json_text = match.group(1) if match else text.strip()
    try:
        data = _json.loads(json_text)
        step_list = data.get("steps", []) if isinstance(data, dict) else data
        if not isinstance(step_list, list):
            return []
    except (_json.JSONDecodeError, TypeError, ValueError) as e:
        logger.debug("parse error: %s", e)

        return []
    steps = []
    for i, s in enumerate(step_list):
        if not isinstance(s, dict):
            continue
        steps.append(
            PlanStep(
                name=s.get("name", f"step_{i + 1}"),
                purpose=s.get("purpose", ""),
                tool=s.get("tool", ""),
                args=s.get("args", {}),
                depends_on=s.get("depends_on", []),
            )
        )
    return steps


# ======================================================================
# Backward-compatible functions
# ======================================================================

SUBAGENT_PROMPT = """You are a sub-agent. Complete the assigned task using available tools.

Task: {task}

Rules:
- Use tools when needed
- Report results clearly
- If you fail, explain why
- Be concise"""


def spawn_subagent(client, task: str, model: str = "", task_type: str = "search") -> str:
    """Spawn a sub-agent with a real tool-calling loop.

    Args:
        client: CruxClient instance
        task: Task description for the sub-agent
        model: Explicit model ID (empty = auto-route by task_type)
        task_type: Task type for auto-routing ("search"/"read_file"/"code"/"planning" etc.)
                   Default "search" since most sub-agents do exploration.
    """
    from core.tools import get_registry

    tools = get_registry()
    if model:
        agent = SubAgent(client, tools=tools, model=model)
    else:
        agent = SubAgent(client, tools=tools, tier="auto", task_type=task_type)
    return agent.run(task)


COMPRESS_PROMPT = """Summarize the following conversation, preserving:
- User's requirements and preferences
- Completed steps and results
- Important decisions and corrections
- Pending items

Output a concise summary (max 300 words):"""


def compress_messages(messages: list[dict], client, model: str = "") -> str:
    """Compress conversation history into a summary (backward compatible)."""
    mgr = ContextManager()
    if not model:
        model = ModelRouter._default_light()
    mgr.compress(messages, client, model)
    return mgr._summary
