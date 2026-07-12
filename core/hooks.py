"""Hook system for intercepting and modifying agent behavior at key lifecycle points."""

import importlib
import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.config import OUTPUT_DIR

__all__ = [
    "Hook",
    "HookEvent",
    "HookManager",
    "HookType",
    "hook_manager",
    "logger",
    "on_notification",
    "on_post_tool",
    "on_pre_tool",
    "on_prompt_submit",
    "on_session_start",
    "on_stop",
    "register_code_hooks",
    "register_learning_hooks",
    "register_safety_hooks",
    "register_stop_guard",
]
logger = logging.getLogger(__name__)

# ── Hook Types ──────────────────────────────────────────────────────────────


class HookType(Enum):
    """Lifecycle points where hooks can fire."""

    SESSION_START = "session_start"
    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    CHAT_TURN_START = "chat_turn_start"
    CHAT_TURN_END = "chat_turn_end"
    STOP = "stop"
    NOTIFICATION = "notification"


# ── Data Structures ─────────────────────────────────────────────────────────


@dataclass
class HookEvent:
    """Event passed to hook handlers. Handlers may mutate these fields.

    PreToolUse-specific fields:
        permission_decision: "allow" | "deny" | "ask" (deny > ask > allow priority)
        permission_reason: human-readable reason for the decision
        updated_input: if set, replaces the tool's input params entirely

    Stop-specific fields:
        stop_decision: "block" to prevent agent from stopping
        stop_reason: when blocking, becomes the new user request for the agent
        loop_count: how many times Stop has been blocked in this turn
        loop_limit: max allowed Stop blocks before forced stop (default 5)
    """

    hook_type: HookType
    data: dict = field(default_factory=dict)
    result: Any = None
    stop_processing: bool = False
    # PreToolUse extension
    permission_decision: str = "allow"
    permission_reason: str = ""
    updated_input: dict | None = None
    # Stop extension
    stop_decision: str = ""
    stop_reason: str = ""
    loop_count: int = 0
    loop_limit: int = 5


@dataclass
class Hook:
    """A registered hook definition."""

    name: str
    hook_type: HookType
    handler: Callable[[HookEvent], HookEvent]
    priority: int = 0  # Higher runs first
    enabled: bool = True


# ── Hook Manager ────────────────────────────────────────────────────────────


class HookManager:
    """Central registry and dispatcher for hooks."""

    def __init__(self) -> None:
        self._hooks: dict[str, Hook] = {}
        self._lock = threading.Lock()
        self._load_from_config()

    # ── Registration ────────────────────────────────────────────────────────

    def register(
        self,
        name: str,
        hook_type: HookType,
        handler: Callable[[HookEvent], HookEvent],
        priority: int = 0,
    ) -> bool:
        """Register a new hook. Returns False if name already exists."""
        with self._lock:
            if name in self._hooks:
                logger.debug("Hook '%s' already registered, skipping", name)
                return False
            self._hooks[name] = Hook(
                name=name,
                hook_type=hook_type,
                handler=handler,
                priority=priority,
            )
            logger.debug("Registered hook '%s' (%s, priority=%d)", name, hook_type.value, priority)
            return True

    def unregister(self, name: str) -> bool:
        """Remove a hook by name. Returns False if not found."""
        with self._lock:
            if name not in self._hooks:
                logger.warning("Hook '%s' not found, cannot unregister", name)
                return False
            del self._hooks[name]
            logger.debug("Unregistered hook '%s'", name)
            return True

    def clear(self) -> None:
        """Remove all registered hooks (test isolation / hot reload)."""
        with self._lock:
            n = len(self._hooks)
            self._hooks.clear()
            logger.debug("Cleared %d hook(s)", n)

    def enable(self, name: str) -> None:
        """Enable a hook by name."""
        with self._lock:
            hook = self._hooks.get(name)
            if hook:
                hook.enabled = True
                logger.debug("Enabled hook '%s'", name)
            else:
                logger.warning("Hook '%s' not found, cannot enable", name)

    def disable(self, name: str) -> None:
        """Disable a hook by name."""
        with self._lock:
            hook = self._hooks.get(name)
            if hook:
                hook.enabled = False
                logger.debug("Disabled hook '%s'", name)
            else:
                logger.warning("Hook '%s' not found, cannot disable", name)

    # ── Query ───────────────────────────────────────────────────────────────

    def list_hooks(self) -> list[dict]:
        """Return a summary list of all registered hooks."""
        with self._lock:
            return [
                {
                    "name": h.name,
                    "type": h.hook_type.value,
                    "priority": h.priority,
                    "enabled": h.enabled,
                }
                for h in sorted(self._hooks.values(), key=lambda h: -h.priority)
            ]

    # ── Dispatch ────────────────────────────────────────────────────────────

    def fire(
        self,
        hook_type: HookType,
        data: dict | None = None,
        result: Any = None,
    ) -> HookEvent:
        """Fire all hooks of the given type in priority order (highest first).

        Short-circuits if any handler sets stop_processing=True.
        For PreToolUse: aggregates permission_decision (deny > ask > allow).
        For Stop: respects loop_limit to prevent infinite blocking.
        Returns the final HookEvent with the accumulated result.
        """
        event = HookEvent(
            hook_type=hook_type,
            data=data or {},
            result=result,
        )

        with self._lock:
            candidates = sorted(
                [h for h in self._hooks.values() if h.hook_type == hook_type and h.enabled],
                key=lambda h: -h.priority,
            )

        # Track highest-severity decisions across all handlers
        best_perm = "allow"
        best_perm_reason = ""

        for hook in candidates:
            try:
                new_event = hook.handler(event)
                # Merge permission decisions (deny > ask > allow, tracked independently)
                if hook_type == HookType.PRE_TOOL_USE:
                    perm = new_event.permission_decision
                    if perm == "deny":
                        best_perm = "deny"
                        best_perm_reason = new_event.permission_reason or best_perm_reason
                    elif perm == "ask" and best_perm != "deny":
                        best_perm = "ask"
                        best_perm_reason = new_event.permission_reason or best_perm_reason
                    # Propagate updated_input (last non-None wins)
                    if new_event.updated_input is not None:
                        event.updated_input = new_event.updated_input
                # Merge Stop decisions
                if hook_type == HookType.STOP:
                    if new_event.stop_decision == "block":
                        event.stop_decision = "block"
                        event.stop_reason = new_event.stop_reason or event.stop_reason
                # Propagate result and stop_processing
                event.result = new_event.result if new_event.result is not None else event.result
                event.stop_processing = new_event.stop_processing or event.stop_processing
                event.data = new_event.data or event.data
            except (TypeError, ValueError, RuntimeError):
                logger.exception("Hook '%s' raised an exception", hook.name)
            if event.stop_processing:
                logger.debug("Hook '%s' set stop_processing, short-circuiting", hook.name)
                break

        if hook_type == HookType.PRE_TOOL_USE:
            event.permission_decision = best_perm
            event.permission_reason = best_perm_reason or event.permission_reason

        return event

    # ── Config Loading ──────────────────────────────────────────────────────

    def _load_from_config(self) -> None:
        """Load hook definitions from OUTPUT_DIR / hooks.json if it exists."""
        config_path = OUTPUT_DIR / "hooks.json"
        if not config_path.exists():
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                hooks_config = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to read hooks config from %s", config_path)
            return

        for entry in hooks_config:
            name = entry.get("name")
            type_str = entry.get("type")
            handler_module = entry.get("handler_module")
            handler_func = entry.get("handler_func")
            priority = entry.get("priority", 0)

            if not all([name, type_str, handler_module, handler_func]):
                logger.warning("Incomplete hook config entry: %s", entry)
                continue

            try:
                hook_type = HookType(type_str)
            except ValueError:
                logger.warning("Unknown hook type '%s' in config entry: %s", type_str, name)
                continue

            try:
                mod = importlib.import_module(handler_module)
                handler = getattr(mod, handler_func)
            except (ImportError, AttributeError):
                logger.warning(
                    "Cannot load handler %s.%s for hook '%s'",
                    handler_module,
                    handler_func,
                    name,
                )
                continue

            self.register(name, hook_type, handler, priority)


# ── Global Singleton ────────────────────────────────────────────────────────

hook_manager = HookManager()


def reset_hook_manager() -> None:
    """Clear the global hook_manager (test isolation / hot reload).

    Clears all registered hooks but keeps the same HookManager instance
    so existing `hook_manager` references stay valid.
    """
    hook_manager.clear()


# ── Helper Registration Functions ───────────────────────────────────────────


def on_prompt_submit(
    name: str,
    handler: Callable[[HookEvent], HookEvent],
    priority: int = 0,
) -> bool:
    """Shortcut to register a USER_PROMPT_SUBMIT hook."""
    return hook_manager.register(name, HookType.USER_PROMPT_SUBMIT, handler, priority)


def on_pre_tool(
    name: str,
    handler: Callable[[HookEvent], HookEvent],
    priority: int = 0,
) -> bool:
    """Shortcut to register a PRE_TOOL_USE hook."""
    return hook_manager.register(name, HookType.PRE_TOOL_USE, handler, priority)


def on_post_tool(
    name: str,
    handler: Callable[[HookEvent], HookEvent],
    priority: int = 0,
) -> bool:
    """Shortcut to register a POST_TOOL_USE hook."""
    return hook_manager.register(name, HookType.POST_TOOL_USE, handler, priority)


def on_stop(
    name: str,
    handler: Callable[[HookEvent], HookEvent],
    priority: int = 0,
) -> bool:
    """Shortcut to register a STOP hook.

    Stop hooks fire when the agent finishes its turn and is about to return
    control.  The handler can set ``stop_decision="block"`` to force the
    agent to continue working.  Respects ``loop_limit`` (default 5) to
    prevent infinite loops.
    """
    return hook_manager.register(name, HookType.STOP, handler, priority)


def on_session_start(
    name: str,
    handler: Callable[[HookEvent], HookEvent],
    priority: int = 0,
) -> bool:
    """Shortcut to register a SESSION_START hook."""
    return hook_manager.register(name, HookType.SESSION_START, handler, priority)


def on_notification(
    name: str,
    handler: Callable[[HookEvent], HookEvent],
    priority: int = 0,
) -> bool:
    """Shortcut to register a NOTIFICATION hook (async, non-blocking)."""
    return hook_manager.register(name, HookType.NOTIFICATION, handler, priority)


# ── Built-in Safety Filter ──────────────────────────────────────────────
# 提示词安全检查：复用 sandbox.py 的 DANGEROUS_PATTERNS 作为单一真源，
# 不在 hooks 中维护重复列表（避免四象融合时安全规则漂移）。


def _get_dangerous_patterns() -> list[str]:
    """从 sandbox.py 获取危险模式列表（单一真源，均为正则）。"""
    try:
        from core.sandbox import DANGEROUS_PATTERNS

        return DANGEROUS_PATTERNS
    except ImportError:
        return []  # sandbox 不可用时降级为空（不阻断主流程）


def _safety_filter_handler(event: HookEvent) -> HookEvent:
    """Check user prompt for dangerous commands and prepend a warning.

    DANGEROUS_PATTERNS 是正则（见 sandbox.py），必须用 ``re.search`` 匹配。
    旧实现用 ``pattern in prompt`` 子串匹配会把 ``\\s``/``\\b`` 当字面量，
    导致过滤几乎永不命中——这是一个真实的安全失效。
    """
    prompt = event.data.get("prompt", "")
    if not prompt:
        return event

    import re

    patterns = _get_dangerous_patterns()
    for pattern in patterns:
        if not isinstance(pattern, str):
            continue
        try:
            if re.search(pattern, prompt, flags=re.IGNORECASE):
                warning = (
                    "[SAFETY WARNING] The prompt contains a potentially dangerous command "
                    "pattern. Please verify before proceeding.\n\n"
                )
                if isinstance(event.result, str):
                    event.result = warning + event.result
                else:
                    event.result = warning + prompt
                break
        except re.error:
            # 个别模式正则编译失败：跳过该模式，不打断其它模式的检查
            logger.warning("Invalid dangerous pattern regex skipped: %s", pattern[:60])

    return event


def register_safety_hooks() -> None:
    """Private learning tool — safety hooks disabled by design."""
    pass  # No content restrictions for private learning use


# ── Learning Hooks ─────────────────────────────────────────────────────────


def _learning_post_tool_handler(event: HookEvent) -> HookEvent:
    """Record tool call success/failure to memory for learning.

    On failure, records a correction so the agent can avoid repeating
    the same mistake in future sessions.
    """
    try:
        from utils import memory

        tool_name = event.data.get("tool_name", "")
        result = event.data.get("result", "")
        error = event.data.get("error", "")

        if not tool_name:
            return event

        is_error = bool(error) or (isinstance(result, str) and result.startswith("[错误]"))

        if is_error:
            # Record correction: what went wrong and what to avoid
            memory.record_correction(
                what_happened=f"Tool '{tool_name}' failed: {str(error or result)[:200]}",
                what_should_happen=f"Check parameters and prerequisites before calling '{tool_name}'",
                context=f"tool_call:{tool_name}",
            )
    except (ImportError, AttributeError, OSError):
        pass  # memory module not available or disabled

    return event


def register_learning_hooks() -> None:
    """Register built-in learning hooks (POST_TOOL_USE → correction memory)."""
    hook_manager.register(
        name="learning_post_tool",
        hook_type=HookType.POST_TOOL_USE,
        handler=_learning_post_tool_handler,
        priority=50,
    )


# ── Code Guard Hooks（write/edit 后自动验证）───────────────────────────────


def _syntax_guard_handler(event: HookEvent) -> HookEvent:
    """POST_TOOL_USE hook: 对 .py 文件在 write_file/edit_file 后做 AST 语法验证。

    检测到语法错误时把提示附加到 event.result，让模型看到失败信号、自检修正。
    """
    tool_name = event.data.get("tool_name", "")
    if tool_name not in ("write_file", "edit_file"):
        return event

    args = event.data.get("args", {}) or {}
    file_path = args.get("path", "")
    if not file_path or not str(file_path).endswith(".py"):
        return event

    try:
        import ast
        from pathlib import Path

        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
        ast.parse(source, filename=file_path)
    except SyntaxError as e:
        msg = f"\n[⚠ 语法错误 {file_path}:{e.lineno}] {e.msg}"
        if isinstance(event.result, str):
            event.result = (event.result or "") + msg
        else:
            event.result = msg
    except (OSError, ImportError):
        pass  # 文件不可读或 ast 不可用：静默降级
    return event


def _test_guard_handler(event: HookEvent) -> HookEvent:
    """POST_TOOL_USE hook: edit_file 后自动跑 smoke 测试（非递归、限时）。

    失败时把摘要附到 event.result，让模型感知"改动破坏了测试"。
    smoke 测试集在 pytest 内运行时会被 pytest_runner 递归守卫短路，安全。
    """
    tool_name = event.data.get("tool_name", "")
    if tool_name not in ("edit_file", "patch_file"):
        return event

    args = event.data.get("args", {}) or {}
    file_path = args.get("path", "")
    if not file_path or not str(file_path).endswith(".py"):
        return event

    try:
        from pathlib import Path

        from core.pytest_runner import run_pytest_safe

        root = Path(file_path).resolve().parent.parent
        smoke = root / "tests" / "test_smoke.py"
        if not smoke.exists():
            return event  # 无 smoke 测试集：跳过
        r = run_pytest_safe(str(smoke), timeout=15, cwd=root)
        if r.returncode != 0:
            tail = (r.stdout or r.stderr or "")[-300:]
            msg = f"\n[⚠ smoke 测试失败（改动可能破坏了现有测试）]\n{tail}"
            if isinstance(event.result, str):
                event.result = (event.result or "") + msg
            else:
                event.result = msg
    except (OSError, ImportError, RuntimeError):
        pass  # 守卫或 pytest 不可用：静默降级
    return event


def register_code_hooks() -> None:
    """注册代码守卫 hook：语法验证（高优先级）+ smoke 测试守卫（中优先级）。

    幂等：重复调用不会重复注册（hook_manager 已有同名检查）。
    """
    hook_manager.register(
        name="syntax_guard",
        hook_type=HookType.POST_TOOL_USE,
        handler=_syntax_guard_handler,
        priority=80,  # 先于 test_guard
    )
    hook_manager.register(
        name="test_guard",
        hook_type=HookType.POST_TOOL_USE,
        handler=_test_guard_handler,
        priority=60,  # syntax_guard 之后
    )


# ── #2 反思 Hook（定期 critique，辅助模型分析工具调用序列）──────────────


# 模块级反思引擎实例（由 register_reflection_hook 设置）
_reflection_engine = None


def _reflection_handler(event: HookEvent) -> HookEvent:
    """POST_TOOL_USE hook: 定期反思，将 critique 附加到 event.result。

    每次工具调用后记录到反思引擎，达到 interval 时触发 LLM critique。
    critique 文本通过 event.result 拼接返回给主模型（唯一合法通道）。
    """
    global _reflection_engine
    if _reflection_engine is None:
        return event

    tool_name = event.data.get("tool_name", "")
    args = event.data.get("args", {}) or {}
    result = event.result or ""
    is_error = event.data.get("error", False)

    # 记录本次调用
    _reflection_engine.record_call(
        tool_name=tool_name,
        args_summary=str(args),
        result_summary=str(result),
        is_error=is_error,
    )

    # 尝试触发反思（未到 interval 或 LLM 失败时返回 None）
    critique = _reflection_engine.maybe_critique()
    if critique:
        if isinstance(event.result, str):
            event.result = (event.result or "") + critique
        else:
            event.result = critique
    return event


def register_reflection_hook(
    client=None,
    interval: int = 5,
    enabled: bool = True,
    model: str = "deepseek-v4-pro",
) -> None:
    """注册反思 hook（幂等）。

    Args:
        client: CruxClient 实例（用于 LLM critique）
        interval: 每 N 次工具调用触发一次反思（默认 5）
        enabled: 是否启用反思
        model: 用于 critique 的辅助模型
    """
    global _reflection_engine
    from core.reflection import ReflectionEngine

    _reflection_engine = ReflectionEngine(
        client=client,
        model=model,
        interval=interval,
        enabled=enabled,
    )
    hook_manager.register(
        name="reflection",
        hook_type=HookType.POST_TOOL_USE,
        handler=_reflection_handler,
        priority=40,  # 低于 syntax_guard(80) 和 test_guard(60)
    )


def get_reflection_engine():
    """获取当前反思引擎实例（供测试访问）。"""
    return _reflection_engine


def reset_reflection_engine() -> None:
    """重置反思引擎（供测试隔离）。"""
    global _reflection_engine
    _reflection_engine = None


# ── Stop 守卫 Hook（Agent 结束前自动验证）─────────────────────────────
# 对标 TRAE Stop 事件：Agent 宣布完成时触发，支持 loop_limit。
# 默认注册为最低优先级的 Stop hook，可由用户通过 hooks.json 覆盖。


def _stop_guard_handler(event: HookEvent) -> HookEvent:
    """Stop 守卫：检查 Agent 输出的代码是否存在明显的语法问题。

    这是一个示例性的轻量守卫。用户可替换为运行测试套件的脚本。
    """
    last_message = event.data.get("last_assistant_message", "")
    if not last_message:
        return event

    # Check for common "I'm pretending to be done" patterns
    fake_done_markers = [
        "should be working",
        "should be fixed",
        "seems to work",
        "probably fine",
        "might work",
        "理论上应该",
        "应该可以了",
        "看起来没问题",
    ]
    for marker in fake_done_markers:
        if marker in last_message:
            event.stop_decision = "block"
            event.stop_reason = (
                f"检测到不确定的完成声明 ('{marker}')。请运行验证命令确认修复，"
                "或提供具体的测试通过截图/输出作为证据。"
            )
            break

    return event


def register_stop_guard() -> None:
    """注册内置 Stop 守卫（最低优先级，允许用户 hook 先执行）。"""
    hook_manager.register(
        name="stop_guard",
        hook_type=HookType.STOP,
        handler=_stop_guard_handler,
        priority=0,  # 最低优先级，先跑用户 hook
    )
