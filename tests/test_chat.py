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

from core.chat import ChatSession, MAX_TOOL_LOOPS, _normalize_tool_args


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


# ═══════════════════════════════════════════════════════════════════
# v5.0+ 回归：语义去重 / 模型默认值 / 视觉 fallback 链
# ═══════════════════════════════════════════════════════════════════

class TestSemanticDedup:
    """测试 _merge_tool_calls 的语义去重（推理模型跨阶段重复发工具）。"""

    def test_dedup_same_name_same_args(self):
        """同名同参的多个 tool_call 只保留一个。"""
        fragments = [
            {"index": 0, "id": "a", "function": {"name": "generate_image", "arguments": '{"prompt":"cat"}'}},
            {"index": 1, "id": "b", "function": {"name": "generate_image", "arguments": '{"prompt":"cat"}'}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert len(result) == 1
        assert result[0]["id"] == "a"  # 保留首个

    def test_dedup_key_order_invariant(self):
        """args 的 key 顺序不同应判为相同调用。"""
        fragments = [
            {"index": 0, "id": "x", "function": {"name": "f", "arguments": '{"a":1,"b":2}'}},
            {"index": 1, "id": "y", "function": {"name": "f", "arguments": '{"b":2,"a":1}'}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert len(result) == 1

    def test_dedup_whitespace_invariant(self):
        """args 仅空白差异应判为相同调用。"""
        fragments = [
            {"index": 0, "id": "x", "function": {"name": "f", "arguments": '{"a": 1, "b": 2}'}},
            {"index": 1, "id": "y", "function": {"name": "f", "arguments": '{"a":1,"b":2}'}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert len(result) == 1

    def test_keep_different_args(self):
        """同名不同参的两个调用都保留。"""
        fragments = [
            {"index": 0, "id": "a", "function": {"name": "generate_image", "arguments": '{"prompt":"cat"}'}},
            {"index": 1, "id": "b", "function": {"name": "generate_image", "arguments": '{"prompt":"dog"}'}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert len(result) == 2

    def test_keep_different_names(self):
        """不同名的调用都保留。"""
        fragments = [
            {"index": 0, "id": "a", "function": {"name": "generate_image", "arguments": '{"prompt":"cat"}'}},
            {"index": 1, "id": "b", "function": {"name": "generate_video", "arguments": '{"prompt":"cat"}'}},
        ]
        result = ChatSession._merge_tool_calls(fragments)
        assert len(result) == 2


class TestNormalizeToolArgs:
    """测试 _normalize_tool_args 归一化。"""

    def test_empty(self):
        assert _normalize_tool_args("") == ""
        assert _normalize_tool_args("   ") == ""

    def test_invalid_json_falls_back_to_whitespace_strip(self):
        assert _normalize_tool_args('{a: 1, b: 2}') == '{a:1,b:2}'

    def test_dict_keys_sorted(self):
        a = _normalize_tool_args('{"b":2,"a":1}')
        b = _normalize_tool_args('{"a":1,"b":2}')
        assert a == b


class TestModelDefaultsNotForced:
    """修复2e：toggle_agent_mode / load_skill 不再强制赋值 agnes-2.0-flash。"""

    def test_toggle_agent_mode_keeps_current_model(self):
        """切到 agent_mode 不应改 model（只要模型支持 tools）。"""
        s = make_session()
        s.model = "deepseek-v4-pro"  # 用户已选 deepseek
        before = s.model
        s.toggle_agent_mode()
        assert s.model == before  # 保持不变
        assert s.agent_mode is True
        # 再切回仍保持
        s.toggle_agent_mode()
        assert s.model == before

    def test_toggle_code_mode_keeps_current_model(self):
        """切 code_mode 也不改 model（已是既定行为，回归保护）。"""
        s = make_session()
        s.model = "deepseek-v4-pro"
        before = s.model
        s.toggle_code_mode()
        assert s.model == before


class TestVisionFallback:
    """修复3：视觉通道 fallback 链。"""

    def test_vision_model_chain_dedup(self):
        """_vision_model_chain 去重并把 self.vision_model 放首位。"""
        s = make_session()
        s.vision_model = "agnes-1.5-flash"
        chain = s._vision_model_chain()
        assert chain[0] == "agnes-1.5-flash"
        assert len(chain) == len(set(chain))  # 无重复

    def test_vision_fallback_first_model_success(self):
        """首选模型成功时直接返回内容。"""
        s = make_session()
        s.vision_client = MagicMock()
        s.vision_client.chat_multimodal.return_value = {
            "choices": [{"message": {"content": "这是一只猫"}}]
        }
        out = s._vision_fallback("描述图", "http://img")
        assert out == "这是一只猫"
        # 只调了一次（首选成功）
        assert s.vision_client.chat_multimodal.call_count == 1

    def test_vision_fallback_chain_on_network_error(self):
        """首选网络错误时尝试链中下一个模型。"""
        s = make_session()
        s.vision_model = "agnes-1.5-flash"
        s.vision_client = MagicMock()
        # 首选抛 OSError，第二次（同 client/同模型，链只有一条）也会再试
        s.vision_client.chat_multimodal.side_effect = OSError("timeout")
        out = s._vision_fallback("描述", "http://img")
        assert "视觉理解失败" in out
        assert "timeout" in out
        assert "agnes-1.5-flash" in out  # 列出尝试过的模型

    def test_vision_fallback_format_error_reports(self):
        """返回格式异常（KeyError）应在错误信息中体现。"""
        s = make_session()
        s.vision_client = MagicMock()
        s.vision_client.chat_multimodal.side_effect = KeyError("choices")
        out = s._vision_fallback("描述", "http://img")
        assert "视觉理解失败" in out
        assert "返回格式异常" in out


class TestProviderVisionAPI:
    """provider.get_vision_models / model_supports_vision。"""

    def test_get_vision_models_non_empty(self):
        from core.provider import get_vision_models
        models = get_vision_models()
        assert isinstance(models, list)
        assert "agnes-1.5-flash" in models

    def test_model_supports_vision_true_for_agnes_flash(self):
        from core.provider import model_supports_vision
        assert model_supports_vision("agnes-1.5-flash") is True

    def test_model_supports_vision_false_for_text_only(self):
        from core.provider import model_supports_vision
        assert model_supports_vision("deepseek-v4-pro") is False
        assert model_supports_vision("agnes-2.0-flash") is False


class TestDefaultModelsDeepseek:
    """修复2a/2b/2c/2d：默认模型统一为 deepseek-v4-pro。"""

    def test_plan_executor_default_model(self):
        from core.agent import PlanExecutor
        import inspect
        sig = inspect.signature(PlanExecutor.__init__)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_subagent_default_model(self):
        from core.agent import SubAgent
        import inspect
        sig = inspect.signature(SubAgent.__init__)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_model_router_default_primary(self):
        from core.agent import ModelRouter
        router = ModelRouter()
        assert router.primary == "deepseek-v4-pro"

    def test_spawn_subagent_default_model(self):
        from core.agent import spawn_subagent
        import inspect
        sig = inspect.signature(spawn_subagent)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_run_team_default_model(self):
        from core.project import run_team
        import inspect
        sig = inspect.signature(run_team)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_test_generator_default_model(self):
        from core.test_loop import TestGenerator
        import inspect
        sig = inspect.signature(TestGenerator.__init__)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_test_loop_default_model(self):
        from core.test_loop import TestLoop
        import inspect
        sig = inspect.signature(TestLoop.__init__)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_router_profile_model_all_deepseek_except_chat(self):
        """router._PROFILE_MODEL: 非 CHAT/SKIP 档位全部 deepseek。"""
        from core.router import _PROFILE_MODEL, TaskProfile
        assert _PROFILE_MODEL[TaskProfile.QUICK_FIX] == "deepseek-v4-pro"
        assert _PROFILE_MODEL[TaskProfile.CODING] == "deepseek-v4-pro"
        assert _PROFILE_MODEL[TaskProfile.CREATIVE] == "deepseek-v4-pro"
        assert _PROFILE_MODEL[TaskProfile.DEEP] == "deepseek-v4-pro"
        # CHAT 仍是轻量
        assert _PROFILE_MODEL[TaskProfile.CHAT] == "agnes-1.5-flash"
