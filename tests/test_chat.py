"""Unit tests for ChatSession — tool calling merge logic and session state.

The _merge_tool_calls method is the core of OpenAI streaming tool_call
reassembly. If it breaks, all tool calling (generate_image/generate_video)
silently fails. These tests protect that critical path without needing
a real API connection.
"""
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.chat import ChatSession, MAX_TOOL_LOOPS


def make_session():
    """创建一个 mock client 的 ChatSession（不打真实 API）。"""
    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter([])
    return ChatSession(mock_client)


class TestMergeToolCalls:
    """测试 OpenAI 流式 tool_calls 分片合并。"""

    def test_single_complete_call(self):
        """单个完整 tool_call（无分片）。"""
        fragments = [{
            "index": 0,
            "id": "call_abc",
            "type": "function",
            "function": {"name": "generate_image", "arguments": '{"prompt":"cat"}'},
        }]
        result = ChatSession._merge_tool_calls(fragments)
        assert len(result) == 1
        assert result[0]["id"] == "call_abc"
        assert result[0]["function"]["name"] == "generate_image"
        assert json.loads(result[0]["function"]["arguments"]) == {"prompt": "cat"}

    def test_split_arguments_across_deltas(self):
        """arguments 被 API 拆成多个 delta 分片送达。"""
        fragments = [
            {"index": 0, "id": "call_1", "function": {"name": "generate_image", "arguments": ""}},
            {"index": 0, "function": {"arguments": '{"prom'}},
            {"index": 0, "function": {"arguments": 'pt":"dog"}'}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "generate_image"
        assert json.loads(result[0]["function"]["arguments"]) == {"prompt": "dog"}

    def test_multiple_parallel_calls(self):
        """并行多个 tool_call（不同 index）。"""
        fragments = [
            {"index": 0, "id": "call_a", "function": {"name": "generate_image", "arguments": '{"prompt":"x"}'}},
            {"index": 1, "id": "call_b", "function": {"name": "generate_video", "arguments": '{"prompt":"y"}'}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert len(result) == 2
        assert result[0]["function"]["name"] == "generate_image"
        assert result[1]["function"]["name"] == "generate_video"

    def test_name_split_across_deltas(self):
        """name 也可能被拆分（罕见但 API 可能这么做）。"""
        fragments = [
            {"index": 0, "id": "x", "function": {"name": "generate_", "arguments": ""}},
            {"index": 0, "function": {"name": "image", "arguments": '{}'}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert result[0]["function"]["name"] == "generate_image"

    def test_empty_fragments(self):
        assert ChatSession._merge_tool_calls([]) == []

    def test_missing_index_defaults_to_zero(self):
        """没有 index 字段的 fragment 默认归到 index 0。"""
        fragments = [
            {"id": "x", "function": {"name": "f", "arguments": "{}"}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert len(result) == 1

    def test_id_updates_when_present(self):
        """后续分片带 id 时应更新（id 可能在第一个分片之后才到）。"""
        fragments = [
            {"index": 0, "function": {"name": "f", "arguments": "{}"}},
            {"index": 0, "id": "late_id", "function": {"arguments": ""}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert result[0]["id"] == "late_id"

    def test_results_sorted_by_index(self):
        """合并结果按 index 排序。"""
        fragments = [
            {"index": 2, "id": "c", "function": {"name": "c", "arguments": "{}"}},
            {"index": 0, "id": "a", "function": {"name": "a", "arguments": "{}"}},
            {"index": 1, "id": "b", "function": {"name": "b", "arguments": "{}"}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert [r["id"] for r in result] == ["a", "b", "c"]


class TestChatSessionState:
    """测试 ChatSession 的状态管理。"""

    def test_initial_state(self):
        s = make_session()
        assert s.model == "agnes-1.5-flash"
        assert s.mode == "chat"
        assert s.code_mode is False
        assert s.agent_mode is False
        assert len(s.messages) == 1  # system prompt

    def test_reset_clears_history(self):
        s = make_session()
        s.messages.append({"role": "user", "content": "hello"})
        s.messages.append({"role": "assistant", "content": "hi"})
        s.reset()
        assert len(s.messages) == 1  # 只剩 system

    def test_toggle_code_mode(self):
        s = make_session()
        assert s.code_mode is False
        s.toggle_code_mode()
        assert s.code_mode is True
        assert s.enable_thinking is True  # 代码模式自动开 thinking
        s.toggle_code_mode()
        assert s.code_mode is False

    def test_supports_tools_property(self):
        s = make_session()
        s.model = "agnes-1.5-flash"
        assert s.supports_tools is False
        s.model = "agnes-2.0-flash"
        assert s.supports_tools is True

    def test_system_prompt_contains_model_name(self):
        s = make_session()
        s.model = "agnes-2.0-flash"
        prompt = s._build_system_prompt()
        assert "agnes-2.0-flash" in prompt

    def test_system_prompt_contains_provider_name(self):
        s = make_session()
        s.model = "deepseek-v4-pro"
        prompt = s._build_system_prompt()
        assert "DeepSeek" in prompt


class TestMaxToolLoops:
    def test_constant_exists(self):
        assert isinstance(MAX_TOOL_LOOPS, int)
        assert MAX_TOOL_LOOPS > 0
        assert MAX_TOOL_LOOPS <= 100  # 合理上限
