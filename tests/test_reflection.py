"""Tests for #2 — 反思步骤（self-critique span）。

守护四条契约：
1. **触发逻辑**: 每 N 次工具调用触发一次（counter % interval == 0）
2. **critique 拼接**: 返回的文本格式为 "\\n[反思] ..." 并拼到 event.result
3. **失败降级**: LLM 异常 → 返回 None，绝不阻塞主流程
4. **配置开关**: enabled=False 永不触发
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.reflection import ReflectionEngine, CRITIQUE_PROMPT
from core.hooks import (
    HookEvent,
    HookType,
    hook_manager,
    register_reflection_hook,
    get_reflection_engine,
    reset_reflection_engine,
    _reflection_handler,
)


# ── ReflectionEngine 单元测试 ─────────────────────────────────────────


class TestReflectionEngineTrigger:

    def _make_engine(self, interval=3, client=None, enabled=True):
        return ReflectionEngine(
            client=client or MagicMock(),
            interval=interval,
            enabled=enabled,
        )

    def test_no_critique_before_interval(self):
        """未到 interval 不触发。"""
        engine = self._make_engine(interval=5)
        for i in range(4):
            engine.record_call("read_file", '{"path":"x"}', "content", False)
            assert engine.maybe_critique() is None

    def test_triggers_at_interval(self):
        """正好到 interval 时触发。"""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "计划正常，继续。"}}]
        }
        engine = self._make_engine(interval=3, client=mock_client)
        engine.record_call("read_file", "{}", "ok", False)
        assert engine.maybe_critique() is None  # 1
        engine.record_call("read_file", "{}", "ok", False)
        assert engine.maybe_critique() is None  # 2
        engine.record_call("read_file", "{}", "ok", False)
        result = engine.maybe_critique()  # 3 → 触发
        assert result is not None
        assert "[反思]" in result

    def test_triggers_every_n_calls(self):
        """每 N 次都触发（3, 6, 9...）。"""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "继续。"}}]
        }
        engine = self._make_engine(interval=3, client=mock_client)
        triggers = 0
        for i in range(10):
            engine.record_call("t", "{}", "ok", False)
            if engine.maybe_critique() is not None:
                triggers += 1
        # i=0..9, counter=1..10, 触发点 3,6,9 → 3 次
        assert triggers == 3

    def test_disabled_never_triggers(self):
        """enabled=False 永不触发。"""
        engine = self._make_engine(interval=1, enabled=False)
        engine.record_call("t", "{}", "ok", False)
        assert engine.maybe_critique() is None

    def test_no_client_skips(self):
        """无 client → 跳过（不崩溃）。"""
        engine = ReflectionEngine(client=None, interval=1, enabled=True)
        engine.record_call("t", "{}", "ok", False)
        assert engine.maybe_critique() is None

    def test_no_recent_calls_skips(self):
        """无记录 → 跳过。"""
        mock_client = MagicMock()
        engine = self._make_engine(interval=1, client=mock_client)
        # 不 record_call，直接 maybe_critique
        # counter 会递增到 1（% 1 == 0），但 recent_calls 为空
        result = engine.maybe_critique()
        assert result is None
        mock_client.chat.assert_not_called()


class TestReflectionEngineLLM:

    def test_critique_format(self):
        """critique 文本格式正确。"""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "  建议换用 search 工具。  "}}]
        }
        engine = ReflectionEngine(client=mock_client, interval=1)
        engine.record_call("read_file", "{}", "not found", True)
        result = engine.maybe_critique()
        assert result is not None
        assert result.startswith("\n[反思] ")
        assert "建议换用 search" in result

    def test_llm_failure_returns_none(self):
        """LLM 调用失败 → 返回 None（静默降级）。"""
        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("API error")
        engine = ReflectionEngine(client=mock_client, interval=1)
        engine.record_call("t", "{}", "ok", False)
        result = engine.maybe_critique()
        assert result is None  # 不抛异常

    def test_empty_response_returns_none(self):
        """LLM 返回空内容 → 返回 None。"""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": ""}}]
        }
        engine = ReflectionEngine(client=mock_client, interval=1)
        engine.record_call("t", "{}", "ok", False)
        result = engine.maybe_critique()
        assert result is None

    def test_llm_call_args(self):
        """验证 client.chat 调用参数正确。"""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        engine = ReflectionEngine(
            client=mock_client, interval=1, model="deepseek-v4-pro"
        )
        engine.record_call("t", "{}", "ok", False)
        engine.maybe_critique()
        mock_client.chat.assert_called_once()
        call_kwargs = mock_client.chat.call_args[1]
        assert call_kwargs["model"] == "deepseek-v4-pro"
        assert call_kwargs["max_tokens"] == 300


class TestReflectionEngineContext:

    def test_error_calls_prioritized(self):
        """error=True 的调用在 context 中排在前面。"""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        engine = ReflectionEngine(client=mock_client, interval=1)
        engine.record_call("read_file", "{}", "ok", False)
        engine.record_call("bad_tool", "{}", "[错误] failed", True)
        engine.record_call("edit_file", "{}", "ok", False)

        context = engine._build_context()
        lines = context.split("\n")
        # error 调用应在第 1 个位置（idx=0 处的 "1. 工具: bad_tool [错误]"）
        assert "[错误]" in lines[0]
        assert "bad_tool" in lines[0]

    def test_args_result_truncated(self):
        """超长 args/result 被截断到 200/300 字符。"""
        engine = ReflectionEngine(client=MagicMock(), interval=100)
        long_args = "A" * 500
        long_result = "B" * 500
        engine.record_call("t", long_args, long_result, False)
        call = engine._recent_calls[0]
        assert len(call["args"]) <= 200
        assert len(call["result"]) <= 300

    def test_max_recent_limit(self):
        """recent_calls 超过 max_recent 时只保留最近 N 条。"""
        engine = ReflectionEngine(client=MagicMock(), interval=100, max_recent=3)
        for i in range(5):
            engine.record_call(f"tool_{i}", "{}", "ok", False)
        assert len(engine._recent_calls) == 3
        # 保留最后 3 条
        assert engine._recent_calls[0]["tool"] == "tool_2"

    def test_clears_recent_after_critique(self):
        """触发 critique 后清空 recent_calls（避免重复分析）。"""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        engine = ReflectionEngine(client=mock_client, interval=1)
        engine.record_call("t", "{}", "ok", False)
        engine.maybe_critique()
        assert len(engine._recent_calls) == 0


# ── Hook 集成测试 ─────────────────────────────────────────────────────


class TestReflectionHook:

    def teardown_method(self):
        """每个测试后重置全局反思引擎。"""
        reset_reflection_engine()

    def test_register_creates_engine(self):
        """register_reflection_hook 创建引擎并注册 hook。"""
        mock_client = MagicMock()
        register_reflection_hook(client=mock_client, interval=5, enabled=True)
        engine = get_reflection_engine()
        assert engine is not None
        assert engine.enabled is True
        assert engine.counter == 0

    def test_handler_appends_critique(self):
        """handler 将 critique 拼接到 event.result。"""
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "方向正确，继续。"}}]
        }
        register_reflection_hook(client=mock_client, interval=1, enabled=True)

        event = HookEvent(
            hook_type=HookType.POST_TOOL_USE,
            data={"tool_name": "read_file", "args": {}, "result": "ok", "error": False},
            result="ok",
        )
        result_event = _reflection_handler(event)
        assert "[反思]" in result_event.result
        assert result_event.result.startswith("ok")  # 原始 result 保留

    def test_handler_no_engine_passthrough(self):
        """无引擎时 handler 直接返回 event（不崩溃）。"""
        reset_reflection_engine()
        event = HookEvent(
            hook_type=HookType.POST_TOOL_USE,
            data={"tool_name": "t", "args": {}, "result": "ok", "error": False},
            result="ok",
        )
        result_event = _reflection_handler(event)
        assert result_event.result == "ok"  # 原样返回

    def test_handler_records_call(self):
        """handler 调用 record_call 记录工具调用。"""
        mock_client = MagicMock()
        register_reflection_hook(client=mock_client, interval=100, enabled=True)
        engine = get_reflection_engine()

        event = HookEvent(
            hook_type=HookType.POST_TOOL_USE,
            data={"tool_name": "edit_file", "args": {"path": "x"}, "result": "done", "error": False},
            result="done",
        )
        _reflection_handler(event)
        assert engine.recent_calls_count == 1

    def test_handler_error_flag_recorded(self):
        """handler 正确记录 error 标记。"""
        mock_client = MagicMock()
        register_reflection_hook(client=mock_client, interval=100, enabled=True)
        engine = get_reflection_engine()

        event = HookEvent(
            hook_type=HookType.POST_TOOL_USE,
            data={"tool_name": "bad", "args": {}, "result": "[错误] failed", "error": True},
            result="[错误] failed",
        )
        _reflection_handler(event)
        assert engine._recent_calls[0]["error"] is True


class TestReflectionConfig:
    """验证 config.Settings 的反思配置字段。"""

    def test_config_has_reflection_fields(self):
        """Settings 包含 reflection_enabled 和 reflection_interval。"""
        from core.config import SETTINGS
        assert hasattr(SETTINGS, "reflection_enabled")
        assert hasattr(SETTINGS, "reflection_interval")
        assert isinstance(SETTINGS.reflection_enabled, bool)
        assert isinstance(SETTINGS.reflection_interval, int)

    def test_default_values(self):
        """默认值正确。"""
        from core.config import Settings
        s = Settings()
        assert s.reflection_enabled is True
        assert s.reflection_interval == 5
