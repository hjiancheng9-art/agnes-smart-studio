"""Agent infrastructure - Plan execution / Sub-agent / Context compression / Multi-model routing

This module provides the "thinking brain" behind crux-studio:
- ContextManager: token counting + layered auto-compression for long conversations
- PlanExecutor: step-by-step task execution with state machine and dependencies
- SubAgent: independent agent with its own tool-calling loop and session history
- ModelRouter: intelligent model selection based on task type and cost
"""

import json
import re
import unicodedata
from enum import Enum

__all__ = [
    'COMPRESS_PROMPT', 'ContextManager', 'ModelRouter', 'PLAN_PROMPT', 'PlanExecutor', 'PlanStep', 'SUBAGENT_PROMPT', 'StepStatus', 'SubAgent', 'compress_messages', 'parse_plan', 'spawn_subagent',
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

    def __init__(self, max_tokens: int = 60000, preserve_recent: int = 10,
                 preserve_system: bool = True) -> None:
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
        wide_count = sum(
            1 for c in text
            if unicodedata.east_asian_width(c) in ('W', 'F')
        )
        narrow_count = len(text) - wide_count
        return wide_count // 2 + narrow_count // 4 + 1

    @staticmethod
    def estimate_message_tokens(msg: dict) -> int:
        """Estimate tokens for a single message dict."""
        content = msg.get("content", "")
        if isinstance(content, list):
            # Multimodal: count text parts
            text = " ".join(
                c.get("text", "") for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
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

    def compress(self, messages: list[dict], client,
                 model: str = "agnes-1.5-flash") -> list[dict]:
        """Compress conversation history using layered strategy.

        - Never touch system messages
        - Preserve the most recent N messages verbatim (but truncate
          oversized single messages — e.g. tool results returning whole files)
        - Preserve user's original messages (truncate if too long)
        - Summarize old assistant/tool messages
        """
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
        to_compress = conversation[:-self.preserve_recent]
        to_keep = conversation[-self.preserve_recent:]

        # Build compression input: extract key info from old messages
        compress_parts = []
        for msg in to_compress:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    c.get("text", "") for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
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

    def auto_compress_if_needed(self, messages: list[dict], client,
                                model: str = "agnes-1.5-flash") -> list[dict]:
        """Two-tier compression: truncate first (free), LLM summary only if still over.

        Tier 1 (free): _truncate_messages — cap each message at _MAX_MSG_CHARS.
            This alone often resolves token pressure caused by large tool results.
        Tier 2 (costly): full LLM compress — only triggered if tier 1 is insufficient.
        """
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

    def __init__(self, name: str, purpose: str = "", tool: str = "",
                 depends_on: list[int] | None = None) -> None:
        self.name = name
        self.purpose = purpose
        self.tool = tool
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

    def __init__(self, client, tools=None, model: str = "deepseek-v4-pro",
                 tier: str = "auto", task_type: str = "") -> None:
        """Init plan executor.

        Args:
            model: 显式模型 ID（向后兼容，优先级最高）
            tier: "auto"/"light"/"pro"/"heavy" — auto 时按 task_type 路由
            task_type: tier=auto 时传给 ModelRouter.select()
        """
        self.client = client
        self.tools = tools
        self.max_steps = 15
        # tier 路由（与 SubAgent 同逻辑）
        if model != "deepseek-v4-pro":
            self.model = model
        elif tier in ("light", "pro", "heavy"):
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

    def execute(self, steps: list[PlanStep],
                on_progress=None) -> list[PlanStep]:
        """Execute steps in order, respecting dependencies.

        Args:
            steps: List of PlanStep objects
            on_progress: Optional callback(step_index, step, status)
        """
        results = []
        context = ""  # Accumulated context from previous steps

        for i, step in enumerate(steps[:self.max_steps]):
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
                    context += f"\n[Step {i+1}: {step.name}] Result: {result[:500]}"
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
        else:
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
        for match in re.finditer(r'(\w+)[:=]\s*(\S+)', step.purpose):
            args[match.group(1)] = match.group(2).strip('"\'')
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
            lines.append(f"{status_icon} Step {i+1}: {step.name}")
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

    def __init__(self, client, tools=None, model: str = "deepseek-v4-pro",
                 max_rounds: int = 5, tier: str = "auto",
                 task_type: str = "") -> None:
        """Init sub-agent.

        Args:
            model: 显式模型 ID（向后兼容，优先级最高）
            tier: "auto" / "light" / "pro" / "heavy" — auto 时按 task_type 路由
            task_type: 传给 ModelRouter.select() 的任务类型（tier=auto 时生效）
        """
        self.client = client
        self.tools = tools
        self.max_rounds = max_rounds
        self.history: list[dict] = []
        self.context_mgr = ContextManager(max_tokens=20000)
        # tier 路由：model 显式指定时尊重之；否则按 tier/task_type 自动选
        if model != "deepseek-v4-pro" or tier == "auto":
            # 用户显式传了 model（非默认值）→ 直接用
            if model != "deepseek-v4-pro":
                self.model = model
            else:
                router = ModelRouter()
                if tier in ("light", "pro", "heavy"):
                    self.model = router.select_for_tier(tier)
                elif task_type:
                    self.model = router.select(task_type=task_type)
                else:
                    self.model = model  # auto + 无 task_type → 退回默认
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
            self.history = self.context_mgr.auto_compress_if_needed(
                self.history, self.client, "agnes-1.5-flash"
            )

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
                        "git_add_commit", "git_push", "git_pr_create", "git_pr_merge",
                    }
                    is_risky = (
                        tool_name in _HIGH_RISK
                        or (tool_name == "github_write_file"
                            and not tool_args.get("branch", "").strip())
                    )
                    if is_risky:
                        result = (f"[安全拦截] 工具 '{tool_name}' 属高风险写操作，"
                                  "SubAgent 自主循环不允许执行，请由主会话确认后调用。")
                    else:
                        result = self.tools.execute(tool_name, tool_args)
                else:
                    result = f"[Error] Unknown tool: {tool_name}"

                # Add tool result to history
                self.history.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": result[:4000],  # Truncate long results
                })

        return "[SubAgent] Max rounds reached without final answer."


# ======================================================================
# Multi-Model Intelligent Router
# ======================================================================

class ModelRouter:
    """Intelligent model selection based on task type, cost, and capability.

    三级 tier 路由（对标 Claude Haiku/Sonnet/Opus 分层）:
    - light tier (≈ Haiku):  deepseek-v4-flash — 搜索/读文件/grep/格式化/简单对话，最便宜（同 key 同 base_url）
    - pro tier (≈ Sonnet):   deepseek-v4-flash（轻量 tool calling）/ agnes-2.0-flash — 单文件修改、写测试
    - heavy tier (≈ Opus):   deepseek-v4-pro — 架构设计、多文件分析、安全审查（深度思考 + 1M 上下文）

    视觉通道独立：agnes-1.5-flash（唯一原生多模态），由 self.vision_model 固定，
    不受 light/pro/heavy tier 切换影响。

    Routing logic (v5.0+):
    - Simple chat/Q&A / 搜索/读文件 -> light tier (deepseek-v4-flash, 省 ~50% vs Pro)
    - Code/complex reasoning / long context -> heavy tier (deepseek-v4-pro, 1M context)
    - Image generation -> agnes-image-2.1-flash
    - Video generation -> agnes-video-v2.0
    - Tool calling + thinking -> heavy tier; tool calling 无 thinking -> light (flash)
    - Vision/multimodal -> agnes-1.5-flash（独立通道，非 light tier）
    """

    # 三级 tier 常量 — 对标 Claude 的 haiku/sonnet/opus
    TIER_LIGHT = "light"  # 机械任务（搜索/读文件/grep/简单对话）
    TIER_PRO = "pro"      # 中等复杂度（单文件修改/写测试）
    TIER_HEAVY = "heavy"  # 深度推理（架构/多文件/安全审查）

    MODEL_PROFILES = {
        "agnes-1.5-flash": {
            "cost": 1,  # relative cost unit
            "supports_tools": True,
            "supports_thinking": False,
            "supports_vision": True,
            "max_tokens": 4096,
            "best_for": ["chat", "simple_qa", "vision", "summarize", "search", "read_file"],
            "tier": "light",
        },
        "agnes-2.0-flash": {
            "cost": 3,
            "supports_tools": True,
            "supports_thinking": True,
            "supports_vision": True,
            "max_tokens": 8192,
            "best_for": ["code", "reasoning", "planning", "agent", "tool_calling"],
            "tier": "pro",
        },
        "agnes-image-2.1-flash": {
            "cost": 5,
            "supports_tools": False,
            "supports_thinking": False,
            "supports_vision": False,
            "max_tokens": 0,
            "best_for": ["image_generation"],
            "tier": "pro",
        },
        "agnes-video-v2.0": {
            "cost": 10,
            "supports_tools": False,
            "supports_thinking": False,
            "supports_vision": False,
            "max_tokens": 0,
            "best_for": ["video_generation"],
            "tier": "pro",
        },
        "deepseek-v4-pro": {
            "cost": 2,
            "supports_tools": True,
            "supports_thinking": True,
            "supports_vision": False,
            "max_tokens": 8192,
            "best_for": ["code", "reasoning", "long_context", "architecture", "security"],
            "tier": "heavy",
        },
        "deepseek-v4-flash": {
            "cost": 1,  # 约 Pro 的 50%（对标 Claude Haiku 档）
            "supports_tools": True,
            "supports_thinking": False,  # 非思考模式（思考需切 Pro）
            "supports_vision": False,
            "max_tokens": 8192,
            "best_for": ["chat", "simple_qa", "search", "read_file", "format",
                         "summarize", "tool_calling", "code"],
            "tier": "light",
        },
        "Pro/moonshotai/Kimi-K2.6": {
            "cost": 4,
            "supports_tools": True,
            "supports_thinking": False,
            "supports_vision": False,
            "max_tokens": 8192,
            "best_for": ["code", "reasoning", "long_context"],
            "tier": "pro",
        },
        "Qwen3.6-27B-PRISM-PRO-DQ": {
            "cost": 0,  # local, 离线
            "supports_tools": True,
            "supports_thinking": True,
            "supports_vision": False,
            "max_tokens": 8192,
            "best_for": ["code", "reasoning", "offline"],
            "tier": "heavy",
        },
    }

    def __init__(self, primary: str | None = None,
                 light: str = "deepseek-v4-flash",
                 vision_model: str = "agnes-1.5-flash") -> None:
        # primary 默认从 models.json active provider 的 pro 模型读，
        # 读不到则退回 deepseek-v4-pro（向后兼容）
        if primary is None:
            primary = self._default_primary()
        self.primary = primary      # heavy tier（深度推理/长上下文）
        self.light = light          # light tier（机械任务/简单对话，默认 deepseek-v4-flash）
        self.vision_model = vision_model  # 视觉通道独立（唯一原生多模态 agnes-1.5-flash）
        self._fallback_chain = self._build_fallback_chain()

    def select(self, task_type: str = "", needs_tools: bool = False,
               needs_vision: bool = False, needs_thinking: bool = False,
               needs_long_context: bool = False) -> str:
        """Select the best model for the task.

        Args:
            task_type: "chat", "code", "reasoning", "image_generation", etc.
            needs_tools: Whether tool calling is required
            needs_vision: Whether image understanding is required
            needs_thinking: Whether deep reasoning is required
            needs_long_context: Whether 1M+ token context is needed
        """
        # Hard requirements first
        if task_type == "image_generation":
            return "agnes-image-2.1-flash"
        if task_type == "video_generation":
            return "agnes-video-v2.0"

        # Vision requirement — 独立通道，不受 light/pro/heavy tier 影响
        if needs_vision:
            return self.vision_model  # agnes-1.5-flash（唯一原生多模态）

        # Long context
        if needs_long_context:
            return self.primary  # deepseek-v4-pro: 1M context

        # Tools + thinking -> need a capable model
        if needs_tools and needs_thinking:
            return self.primary  # heavy tier

        # Just tools, no deep thinking -> light model is cheaper
        if needs_tools and not needs_thinking:
            return self.light  # agnes-1.5-flash

        # Thinking but no tools
        if needs_thinking:
            return self.primary

        # Task type routing — 对标 Claude 的 tier 分层
        type_map = {
            # ── light tier（机械任务，最便宜，deepseek-v4-flash）──
            "chat": self.light,
            "simple_qa": self.light,
            "summarize": self.light,
            "search": self.light,       # 搜索/读文件/grep
            "read_file": self.light,    # 机械读文件
            "format": self.light,       # 格式化
            "tool_calling": self.light, # 轻量 tool calling（flash 支持 tools，无需思考）
            # ── 视觉通道（独立，非 tier 体系）──
            "vision": self.vision_model,
            # ── heavy tier（深度推理，deepseek-v4-pro）──
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

        tier 映射（v5.0+，DeepSeek 双档化后）:
        - light: deepseek-v4-flash（机械任务/简单对话，最便宜）
        - pro:   deepseek-v4-flash（轻量 tool calling；比 agnes-2.0-flash 更稳）
        - heavy: deepseek-v4-pro（深度思考 + 1M 上下文）
        """
        if tier == self.TIER_LIGHT:
            return self.light
        if tier == self.TIER_PRO:
            return self.light  # flash 覆盖 pro 档的轻量 tool calling 场景
        if tier == self.TIER_HEAVY:
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

    def _build_fallback_chain(self) -> list[str]:
        """从 models.json fallback.priority 动态构建模型级 fallback 链。

        链结构：[active_pro_model, 其他 provider 的 pro 模型, light 兜底]
        对标 Claude 的 fallbackModel 数组。
        """
        chain: list[str] = [self.primary]
        try:
            from core.provider import get_provider_manager
            mgr = get_provider_manager()
            for pid in mgr.fallback_priority:
                provider = mgr.providers.get(pid, {})
                mid = provider.get("models", {}).get("pro")
                if mid and mid not in chain:
                    chain.append(mid)
            # light 兜底
            if self.light not in chain:
                chain.append(self.light)
        except (ImportError, OSError, RuntimeError):
            # 退回硬编码（向后兼容）
            for m in ("agnes-2.0-flash", "agnes-1.5-flash"):
                if m not in chain:
                    chain.append(m)
        return chain

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

        assert last_error is not None  # guaranteed by loop logic
        raise last_error


# ======================================================================
# Plan prompt and parse_plan (kept for backward compatibility)
# ======================================================================

PLAN_PROMPT = """You are a task planner. Given a user request, output an execution plan.

Output format:
```plan
1. [Step Name] - Purpose: xxx - Tool: tool_name
2. [Step Name] - Purpose: xxx - Tool: tool_name
...
```

Rules:
- Each step should specify what tool to use and expected result
- Steps should be in execution order
- If a step depends on a previous step, note it as "depends: N"
- Keep plans under 10 steps
- After the plan, begin executing step 1"""


def parse_plan(text: str) -> list[PlanStep]:
    """Parse an execution plan from LLM output text.

    Returns a list of PlanStep objects (was list[dict] before).
    """
    # Extract ```plan ... ``` block
    match = re.search(r'```plan\s*\n(.+?)```', text, re.DOTALL)
    if not match:
        # Also try plain numbered list
        match = re.search(r'((?:\d+\..+\n?)+)', text)
        if not match:
            return []
        plan_text = match.group(1)
    else:
        plan_text = match.group(1)

    steps = []
    for line in plan_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        num_match = re.match(r'(\d+)\.\s*(.+)', line)
        if not num_match:
            continue

        step_text = num_match.group(2)

        # Extract components
        name_match = re.match(r'\[(.+?)\]', step_text)
        purpose_match = re.search(r'(?:Purpose|目的)[：:]\s*(.+?)(?:\s*-|\s—|$)', step_text)
        tool_match = re.search(r'(?:Tool|工具)[：:]\s*(\w+)', step_text)
        dep_match = re.search(r'(?:depends|依赖)[：:]\s*(\d+(?:\s*,\s*\d+)*)', step_text)

        deps = []
        if dep_match:
            deps = [int(d.strip()) for d in dep_match.group(1).split(",")]

        steps.append(PlanStep(
            name=name_match.group(1) if name_match else step_text[:30],
            purpose=purpose_match.group(1).strip() if purpose_match else "",
            tool=tool_match.group(1) if tool_match else "",
            depends_on=deps,
        ))

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


def spawn_subagent(client, task: str, model: str = "deepseek-v4-pro") -> str:
    """Spawn a sub-agent with a real tool-calling loop.

    This is the upgraded version that can actually execute tools,
    not just make a single LLM call.
    """
    from core.tools import get_registry
    tools = get_registry()
    agent = SubAgent(client, tools=tools, model=model)
    return agent.run(task)


COMPRESS_PROMPT = """Summarize the following conversation, preserving:
- User's requirements and preferences
- Completed steps and results
- Important decisions and corrections
- Pending items

Output a concise summary (max 300 words):"""


def compress_messages(messages: list[dict], client,
                      model: str = "agnes-1.5-flash") -> str:
    """Compress conversation history into a summary (backward compatible)."""
    mgr = ContextManager()
    mgr.compress(messages, client, model)
    return mgr._summary
