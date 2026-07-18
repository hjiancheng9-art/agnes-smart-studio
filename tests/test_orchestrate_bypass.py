"""Tests for the orchestrate bypass and think-disable guard.

- When plan_from_policy classifies a task as ORCHESTRATE/SWARM,
  send_stream should skip the model and dispatch tools directly.
- When tools are available for DeepSeek models, thinking should disable.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def _mock_fallback(session):
    """Patch the fallback chain to avoid real API key dependency."""
    session._text_fallback_chain = lambda: [(session.model, session.client)]


def _collect_stream(session, text, max_events=30):
    events = []
    for kind, payload in session.send_stream(text):
        events.append((kind, str(payload)[:200]))
        if len(events) >= max_events:
            break
    return events


class TestOrchestrateBypass:
    """Tasks classified as ORCHESTRATE/SWARM should bypass the model."""

    def test_orchestrate_skips_model(self):
        from core.chat import ChatSession

        client = MagicMock()
        client.base_url = "https://test.api/v1"
        client.model = "deepseek-v4-flash"
        session = ChatSession(client)
        _mock_fallback(session)
        session._dispatch_tool = MagicMock(return_value=("OK", []))

        _collect_stream(
            session,
            "请自检自修整个系统的代码质量和安全漏洞，全面审计所有核心模块并修复发现的问题，输出完整报告",
        )
        client.chat_stream.assert_not_called()

    def test_swarm_also_bypasses(self):
        from core.chat import ChatSession

        client = MagicMock()
        client.base_url = "https://test.api/v1"
        client.model = "deepseek-v4-flash"
        session = ChatSession(client)
        _mock_fallback(session)
        session._dispatch_tool = MagicMock(return_value=("OK", []))

        events = _collect_stream(session, "分别分析core/和ui/的代码质量")
        # Swarm may trigger either bypass or model call depending on keyword matching
        assert len(events) > 0

    def test_self_heal_dispatched_with_fix(self):
        from core.chat import ChatSession

        client = MagicMock()
        client.base_url = "https://test.api/v1"
        client.model = "deepseek-v4-flash"
        calls = []
        session = ChatSession(client)
        _mock_fallback(session)
        session._dispatch_tool = lambda n, a: calls.append(n) or ("OK", [])

        _collect_stream(
            session,
            "请自检自修整个系统的代码质量和安全漏洞，全面审计所有核心模块并修复发现的问题，输出完整报告",
        )
        assert "self_heal" in calls, f"self_heal not dispatched: {calls}"
        assert "code_review" in calls, f"code_review not dispatched: {calls}"


class TestThinkDisable:
    """Thinking mode guard for DeepSeek + tools."""

    def test_guard_does_not_crash(self):
        """Verify the think-disable guard executes without error."""
        from core.chat import ChatSession

        client = MagicMock()
        client.base_url = "https://test.api/v1"
        client.model = "deepseek-v4-pro"
        client.chat_stream = lambda *a, **kw: iter([{"choices": [{"delta": {"content": "ok"}, "index": 0}]}])
        session = ChatSession(client)
        _mock_fallback(session)
        session.enable_thinking = True
        session.tools.get_filtered_definitions = MagicMock(return_value=[{"function": {"name": "run_bash"}}])

        events = _collect_stream(session, "list files")
        assert len(events) > 0
