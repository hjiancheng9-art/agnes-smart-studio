"""Hook system for intercepting and modifying agent behavior at key lifecycle points."""

import importlib
import json
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from collections.abc import Callable

from core.config import OUTPUT_DIR

__all__ = [
    "Hook", "HookEvent", "HookManager", "HookType", "hook_manager", "logger", "on_post_tool", "on_pre_tool", "on_prompt_submit", "register_learning_hooks", "register_safety_hooks",
]
logger = logging.getLogger(__name__)

# ── Hook Types ──────────────────────────────────────────────────────────────


class HookType(Enum):
    """Lifecycle points where hooks can fire."""

    USER_PROMPT_SUBMIT = "user_prompt_submit"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    CHAT_TURN_START = "chat_turn_start"
    CHAT_TURN_END = "chat_turn_end"


# ── Data Structures ─────────────────────────────────────────────────────────


@dataclass
class HookEvent:
    """Event passed to hook handlers. Handlers may mutate result and data."""

    hook_type: HookType
    data: dict = field(default_factory=dict)
    result: Any = None
    stop_processing: bool = False


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
                logger.warning("Hook '%s' already registered, skipping", name)
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

        for hook in candidates:
            try:
                event = hook.handler(event)
            except (TypeError, ValueError, RuntimeError):
                logger.exception("Hook '%s' raised an exception", hook.name)
            if event.stop_processing:
                logger.debug("Hook '%s' set stop_processing, short-circuiting", hook.name)
                break

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


# ── Built-in Safety Filter Example ──────────────────────────────────────────

# Dangerous patterns to detect in user prompts
_DANGEROUS_PATTERNS = [
    "rm -rf",
    "rm -r /",
    "DROP TABLE",
    "DELETE FROM",
    "TRUNCATE TABLE",
    "shutdown",
    "format c:",
    "del /s /q",
    ":(){ :|:& };:",
]


def _safety_filter_handler(event: HookEvent) -> HookEvent:
    """Check user prompt for dangerous commands and prepend a warning."""
    prompt = event.data.get("prompt", "")
    if not prompt:
        return event

    for pattern in _DANGEROUS_PATTERNS:
        if pattern.lower() in prompt.lower():
            warning = (
                "[SAFETY WARNING] The prompt contains a potentially dangerous command "
                f"('{pattern}'). Please verify before proceeding.\n\n"
            )
            if isinstance(event.result, str):
                event.result = warning + event.result
            else:
                event.result = warning + prompt
            break

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
