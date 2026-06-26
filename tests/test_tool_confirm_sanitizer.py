"""Tests for 高风险工具确认 + sanitize_tool_call_history 安全网。

三组契约：
1. sanitize_tool_call_history: 孤儿 assistant tool_calls / tool 消息清洗
2. confirm 机制: 高风险工具首次调用返回 confirm side-effect, confirmed=True 跳过
3. 安全网: confirm 占位消息在 history 中合法（不会被 sanitizer 误删）
"""
# pyright: reportAttributeAccessIssue=false

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.chat import sanitize_tool_call_history
from core.constraints import is_tool_high_risk

# ═══════════════════════════════════════════════════════════════
# 1. sanitize_tool_call_history — 孤儿清洗
# ═══════════════════════════════════════════════════════════════


class TestSanitizeToolCallHistory:
    def test_empty_messages(self):
        """空列表直接返回。"""
        assert sanitize_tool_call_history([]) == []

    def test_no_tool_calls(self):
        """纯对话消息不受影响。"""
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = sanitize_tool_call_history(msgs)
        assert len(result) == 2
        assert result[1].get("tool_calls") is None

    def test_well_paired_tool_calls_unchanged(self):
        """assistant tool_calls + 配对 tool 消息 → 原样保留。"""
        tc_id = "call_abc123"
        msgs = [
            {"role": "user", "content": "do it"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": tc_id, "type": "function", "function": {"name": "git_push", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": tc_id, "content": "pushed"},
        ]
        result = sanitize_tool_call_history(msgs)
        assert len(result) == 3
        assert "tool_calls" in result[1]
        assert result[2]["role"] == "tool"

    def test_orphan_assistant_tool_calls_stripped(self):
        """assistant 含 tool_calls 但无配对 tool 消息 → 剥离 tool_calls，保留 content。"""
        msgs = [
            {"role": "user", "content": "do it"},
            {
                "role": "assistant",
                "content": "I'll push for you",
                "tool_calls": [
                    {"id": "call_orphan", "type": "function", "function": {"name": "git_push", "arguments": "{}"}},
                ],
            },
        ]
        result = sanitize_tool_call_history(msgs)
        assert len(result) == 2
        assert "tool_calls" not in result[1]
        assert result[1]["content"] == "I'll push for you"

    def test_partial_orphan_assistant(self):
        """assistant 有 2 个 tool_calls 但只有 1 条 tool 回复 → 剥离整个 tool_calls。"""
        msgs = [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_a", "type": "function", "function": {"name": "git_push", "arguments": "{}"}},
                    {"id": "call_b", "type": "function", "function": {"name": "git_add_commit", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_a", "content": "ok"},
        ]
        result = sanitize_tool_call_history(msgs)
        # 配对不完整 → 整个 tool_calls 被剥离
        assert "tool_calls" not in result[1]

    def test_orphan_tool_message_removed(self):
        """tool 消息无配对 assistant → 被移除。"""
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ok"},
            {"role": "tool", "tool_call_id": "call_ghost", "content": "ghost result"},
        ]
        result = sanitize_tool_call_history(msgs)
        assert len(result) == 2
        assert result[1]["role"] == "assistant"

    def test_pure_function_no_mutation(self):
        """不修改原始输入。"""
        msgs = [
            {
                "role": "assistant",
                "content": "x",
                "tool_calls": [
                    {"id": "call_z", "type": "function", "function": {"name": "git_push", "arguments": "{}"}},
                ],
            },
        ]
        original_str = str(msgs)
        sanitize_tool_call_history(msgs)
        assert str(msgs) == original_str

    def test_confirm_placeholder_is_valid_tool_message(self):
        """confirm 占位消息 [高风险工具 xxx: 等待用户确认] 作为合法 tool 消息不被移除。"""
        tc_id = "call_confirm_1"
        msgs = [
            {"role": "user", "content": "push it"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": tc_id, "type": "function", "function": {"name": "git_push", "arguments": "{}"}}],
            },
            {
                "role": "tool",
                "tool_call_id": tc_id,
                "content": "[高风险工具 git_push: 等待用户确认]",
            },
        ]
        result = sanitize_tool_call_history(msgs)
        assert len(result) == 3
        assert result[2]["role"] == "tool"
        assert "等待用户确认" in result[2]["content"]


# ═══════════════════════════════════════════════════════════════
# 2. Confirm 机制 — is_tool_high_risk
# ═══════════════════════════════════════════════════════════════


class TestHighRiskDetection:
    def test_git_push_is_high_risk(self):
        assert is_tool_high_risk("git_push", {}) is True

    def test_git_add_commit_is_high_risk(self):
        assert is_tool_high_risk("git_add_commit", {"message": "fix"}) is True

    def test_safe_tool_is_not_high_risk(self):
        assert is_tool_high_risk("read_file", {"path": "/tmp/x"}) is False

    def test_github_write_file_no_branch(self):
        """默认分支写入是高风险。"""
        assert is_tool_high_risk("github_write_file", {"path": "x", "content": "y"}) is True

    def test_github_write_file_with_branch(self):
        """指定分支写入非高风险。"""
        assert is_tool_high_risk("github_write_file", {"path": "x", "content": "y", "branch": "feat/x"}) is False

    def test_git_push_force(self):
        assert is_tool_high_risk("git_push", {"force": True}) is True

    def test_git_branch_delete(self):
        assert is_tool_high_risk("git_branch", {"action": "delete", "name": "old"}) is True

    def test_git_branch_create_not_risk(self):
        assert is_tool_high_risk("git_branch", {"action": "create", "name": "new"}) is False


# ═══════════════════════════════════════════════════════════════
# 3. Confirm 流程 — _dispatch_tool_impl confirmed 参数
# ═══════════════════════════════════════════════════════════════


class TestDispatchToolConfirm:
    def _make_session(self, tools_execute_return="default result"):
        """创建带 mock 的 ChatSession 用于测试 _dispatch_tool_impl。

        _dispatch_tool_impl 内部通过局部 from core.constraints import is_tool_high_risk
        导入，所以测试需要 patch core.constraints.is_tool_high_risk。
        外部工具走 self.tools（ToolRegistry 实例），需要 mock self.tools。
        """
        from core.chat import ChatSession

        mock_client = MagicMock()
        mock_client.model = "test-model"
        mock_client.provider_name = "test"
        session = ChatSession(client=mock_client)
        session.model = "test-model"
        # mock self.tools —— 外部工具路径走 self.tools.has() + self.tools.execute()
        mock_tools = MagicMock()
        mock_tools.has.return_value = True
        mock_tools.execute.return_value = tools_execute_return
        session.tools = mock_tools
        # mock self.brain / self.t2i / self.vid —— 避免内置引擎路径干扰
        session.brain = MagicMock()
        session.t2i = MagicMock()
        session.vid = MagicMock()
        return session

    @patch("core.constraints.is_tool_high_risk", return_value=True)
    def test_high_risk_without_confirmed_returns_confirm(self, mock_risk):
        """高风险工具 + confirmed=False → 返回 confirm side-effect，不执行工具。"""
        session = self._make_session()
        text, side_effects = session._dispatch_tool("git_push", "{}", confirmed=False)
        assert text == ""
        assert any(k == "confirm" for k, _ in side_effects)
        confirm_data = [v for k, v in side_effects if k == "confirm"][0]
        assert confirm_data["tool"] == "git_push"
        # self.tools.execute 不应被调用（confirm 拦截在前）
        session.tools.execute.assert_not_called()

    @patch("core.constraints.is_tool_high_risk", return_value=True)
    def test_high_risk_with_confirmed_executes(self, mock_risk):
        """高风险工具 + confirmed=True → 跳过确认检查，执行工具。"""
        session = self._make_session(tools_execute_return="pushed successfully")
        text, side_effects = session._dispatch_tool("git_push", "{}", confirmed=True)
        assert text == "pushed successfully"
        assert not any(k == "confirm" for k, _ in side_effects)
        session.tools.execute.assert_called_once()

    @patch("core.constraints.is_tool_high_risk", return_value=False)
    def test_low_risk_always_executes(self, mock_risk):
        """低风险工具 → 无论 confirmed 值如何，都直接执行。"""
        session = self._make_session(tools_execute_return="read result")
        text, _ = session._dispatch_tool("read_file", '{"path": "/tmp/x"}', confirmed=False)
        assert text == "read result"
        session.tools.execute.assert_called_once()

    @patch("core.constraints.is_tool_high_risk", return_value=False)
    def test_low_risk_confirmed_true_still_executes(self, mock_risk):
        """低风险工具 + confirmed=True → 正常执行（无副作用）。"""
        session = self._make_session(tools_execute_return="ok")
        text, _ = session._dispatch_tool("read_file", '{"path": "/tmp/y"}', confirmed=True)
        assert text == "ok"
        session.tools.execute.assert_called_once()
