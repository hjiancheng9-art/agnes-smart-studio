"""ChatSession toggle Mixin — mode switching (code/agent/browser/notebook/audio).

Extracted from core/chat.py to reduce module size (brain.py Mixin precedent).
Methods in this Mixin access ChatSession attributes via type stubs (see class body).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.provider import get_provider_name
from core.tools import AGENT_SYSTEM_PROMPT, get_registry


class ChatToggleMixin:
    """Mixin for ChatSession toggle methods.

    Intended to be mixed into core.chat.ChatSession via multiple inheritance.
    All self.* attribute accesses below are resolved at runtime on the full ChatSession object.
    """

    # ── type stubs: attributes provided by ChatSession or other Mixins ──
    _build_system_prompt: Callable[[], str]
    _render_tool_categories: Callable[[], str]
    _reload_tools: Callable[[], None]

    # state booleans
    code_mode: bool
    agent_mode: bool
    browser_enabled: bool
    notebook_enabled: bool
    audio_enabled: bool
    enable_thinking: bool
    unlimited_tools: bool

    # core attributes
    messages: list[dict[str, Any]]
    model: str
    tools: Any  # ToolRegistry
    skills: Any  # SkillManager
    client: Any  # CruxClient
    model_router: Any

    # ── toggle methods ──

    def toggle_code_mode(self) -> bool:
        """切换代码助手模式，返回切换后的状态"""
        self.code_mode = not self.code_mode
        self.enable_thinking = self.code_mode
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.code_mode

    def toggle_agent_mode(self) -> bool:
        """切换智能体模式，加载 tools.json 中定义的外部工具"""
        self.agent_mode = not self.agent_mode
        self.enable_thinking = True
        self.unlimited_tools = self.agent_mode
        if self.agent_mode:
            self.tools = get_registry()
            self.tools.load(
                browser=self.browser_enabled,
                notebook=self.notebook_enabled,
                audio=self.audio_enabled,
                mcp=True,
            )
            try:
                from core.hooks import register_code_hooks

                register_code_hooks()
            except (ImportError, OSError):
                pass
            try:
                from core.config import SETTINGS
                from core.hooks import register_reflection_hook

                register_reflection_hook(
                    client=self.client,
                    interval=SETTINGS.reflection_interval,
                    enabled=SETTINGS.reflection_enabled,
                )
            except (ImportError, OSError):
                pass
            self.tools.model_router = self.model_router  # pyright: ignore[reportAttributeAccessIssue] — monkey-patch for agent mode
            provider_name = get_provider_name(self.model)
            prompt = AGENT_SYSTEM_PROMPT.format(provider_name=provider_name, model_name=self.model)
            prompt += self._render_tool_categories()
        else:
            prompt = self._build_system_prompt()
        prompt = self.skills.get_system_prompt(prompt)
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.agent_mode

    def toggle_browser(self) -> bool:
        """切换 Browser Companion 网页生成工具"""
        self.browser_enabled = not self.browser_enabled
        self._reload_tools()
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.browser_enabled

    def toggle_notebook(self) -> bool:
        """切换 Notebook (.ipynb) 工具"""
        self.notebook_enabled = not self.notebook_enabled
        self._reload_tools()
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.notebook_enabled

    def toggle_audio(self) -> bool:
        """切换音频工具（edge-tts 旁白/BGM/SFX/混音）"""
        self.audio_enabled = not self.audio_enabled
        self._reload_tools()
        prompt = self._build_system_prompt()
        self.messages[0] = {"role": "system", "content": prompt}
        for msg in self.messages[1:]:
            c = msg.get("content", "")
            if isinstance(c, str) and len(c) > 2000 and msg.get("role") == "tool":
                msg["content"] = c[:2000] + "\n...[trimmed]"
        return self.audio_enabled
