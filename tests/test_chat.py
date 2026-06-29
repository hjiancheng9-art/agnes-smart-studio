"""Unit tests for ChatSession — tool calling merge logic and session state.

The _merge_tool_calls method is the core of OpenAI streaming tool_call
reassembly. If it breaks, all tool calling (generate_image/generate_video)
silently fails. These tests protect that critical path without needing
a real API connection.
"""
# pyright: reportOptionalMemberAccess=false

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.chat import MAX_TOOL_LOOPS, ChatSession, _normalize_tool_args


def make_session():
    """创建一个 mock client 的 ChatSession（不打真实 API）。"""
    mock_client = MagicMock()
    mock_client.chat_stream.return_value = iter([])
    return ChatSession(mock_client)


class TestMergeToolCalls:
    """测试 OpenAI 流式 tool_calls 分片合并。"""

    def test_single_complete_call(self):
        """单个完整 tool_call（无分片）。"""
        fragments = [
            {
                "index": 0,
                "id": "call_abc",
                "type": "function",
                "function": {"name": "generate_image", "arguments": '{"prompt":"cat"}'},
            }
        ]
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
            {"index": 0, "function": {"name": "image", "arguments": "{}"}},
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
        assert s.model == "deepseek-v4-flash"
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
        assert _normalize_tool_args("{a: 1, b: 2}") == "{a:1,b:2}"

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

    def test_vision_chain_light_complexity_picks_light_first(self):
        """阶段4b: 轻量任务首选 light tier 模型（agnes-1.5-flash）。"""
        s = make_session()
        s.vision_model = "agnes-1.5-flash"
        chain = s._vision_model_chain("light")
        assert chain[0] == "agnes-1.5-flash"  # light tier 首选

    def test_vision_chain_complex_complexity_picks_pro_first(self):
        """阶段4b: 复杂任务首选 pro tier 模型（agnes-2.0-flash 等）。"""
        s = make_session()
        s.vision_model = "agnes-1.5-flash"
        chain = s._vision_model_chain("complex")
        # 首项必须是 pro tier（agnes-2.0-flash / Kimi / Qwen）
        from core.provider import get_model_info

        first_tier = get_model_info(chain[0]).tier if get_model_info(chain[0]) else "pro"
        assert first_tier != "light", f"Complex task should not pick light tier first: {chain[0]}"
        # agnes-1.5-flash 应在链末尾（作为最后 fallback）
        assert chain[-1] == "agnes-1.5-flash"

    def test_vision_chain_all_models_vision_capable(self):
        """阶段4a: 除 deepseek 外所有模型都在视觉链中。"""
        s = make_session()
        s.vision_model = "agnes-1.5-flash"
        chain = s._vision_model_chain("light")
        # 应包含视觉模型（zhipu + crux）
        assert "agnes-1.5-flash" in chain
        assert "agnes-2.0-flash" in chain
        assert "GLM-4V-Flash" in chain
        # deepseek 不在链中
        assert "deepseek-v4-pro" not in chain
        assert "deepseek-v4-flash" not in chain

    def test_vision_fallback_picks_pro_for_complex_task(self):
        """阶段4b: 复杂视觉任务应调用 pro tier 模型（非 agnes-1.5-flash）。"""
        s = make_session()
        s.vision_client = MagicMock()
        s.vision_client.chat_multimodal.return_value = {"choices": [{"message": {"content": "有 3 只猫"}}]}
        out = s._vision_fallback("数一数有几只猫", "http://img")
        assert out == "有 3 只猫"
        # 被调用的模型不应该是 agnes-1.5-flash（complex 应走 pro tier）
        called_model = s.vision_client.chat_multimodal.call_args.kwargs.get("model", "")
        assert called_model != "agnes-1.5-flash", f"Complex vision task should not use light tier: {called_model}"

    def test_vision_fallback_first_model_success(self):
        """首选模型成功时直接返回内容。"""
        s = make_session()
        s.vision_client = MagicMock()
        s.vision_client.chat_multimodal.return_value = {"choices": [{"message": {"content": "这是一只猫"}}]}
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

        # 阶段4a: deepseek-* 不支持视觉；其余模型（agnes/Kimi/Qwen）均支持
        assert model_supports_vision("deepseek-v4-pro") is False
        assert model_supports_vision("deepseek-v4-flash") is False
        # 非 deepseek 模型均支持视觉
        assert model_supports_vision("agnes-2.0-flash") is True
        assert model_supports_vision("GLM-4V-Flash") is True
        assert model_supports_vision("glm-4.1v-thinking-flash") is True
        assert model_supports_vision("deepseek-v4-pro") is False


class TestDefaultModelsDeepseek:
    """修复2a/2b/2c/2d：默认模型统一为 deepseek-v4-pro。"""

    def test_plan_executor_default_model(self):
        import inspect

        from core.agent import PlanExecutor

        sig = inspect.signature(PlanExecutor.__init__)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_subagent_default_model(self):
        import inspect

        from core.agent import SubAgent

        sig = inspect.signature(SubAgent.__init__)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_model_router_default_primary(self):
        from core.agent import ModelRouter

        router = ModelRouter()
        # primary 取决于 models.json active provider 的 pro model
        assert router.primary in ("deepseek-v4-pro", "agnes-2.0-flash")

    def test_spawn_subagent_default_model(self):
        import inspect

        from core.agent import spawn_subagent

        sig = inspect.signature(spawn_subagent)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_run_team_default_model(self):
        import inspect

        from core.project import run_team

        sig = inspect.signature(run_team)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_test_generator_default_model(self):
        import inspect

        from core.test_loop import TestGenerator

        sig = inspect.signature(TestGenerator.__init__)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_test_loop_default_model(self):
        import inspect

        from core.test_loop import TestLoop

        sig = inspect.signature(TestLoop.__init__)
        assert sig.parameters["model"].default == "deepseek-v4-pro"

    def test_router_profile_model_all_deepseek_except_chat(self):
        """router._PROFILE_MODEL: 非 CHAT/SKIP 档位全部 deepseek。"""
        from core.router import _get_profile_candidates, TaskProfile

        # profile → 候选列表（从 active provider 动态派生）
        candidates = _get_profile_candidates(TaskProfile.QUICK_FIX)
        # quick_fix 应优先 flash 档
        assert all("flash" in m.lower() for m in candidates[:2]), f"quick_fix candidates {candidates} should prioritize flash"

        candidates = _get_profile_candidates(TaskProfile.CODING)
        assert any("pro" in m.lower() or "reasoner" in m.lower() for m in candidates[:2]), f"coding candidates {candidates} should prioritize pro/reasoner"

        candidates = _get_profile_candidates(TaskProfile.DEEP)
        assert any("pro" in m.lower() or "reasoner" in m.lower() for m in candidates[:2]), f"deep candidates {candidates} should prioritize pro/reasoner"

        candidates = _get_profile_candidates(TaskProfile.CHAT)
        assert any("flash" in m.lower() for m in candidates[:2]), f"chat candidates {candidates} should prioritize flash"


# ═══════════════════════════════════════════════════════════════════
# 阶段 4: send_stream 模型级 fallback 测试
# ═══════════════════════════════════════════════════════════════════


class TestTextFallbackChain:
    """_text_fallback_chain 构建 (model, client) 备选列表。"""

    def test_chain_starts_with_current_model(self):
        """fallback 链首项是当前 (model, client)。"""
        s = make_session()
        chain = s._text_fallback_chain()
        assert chain[0] == (s.model, s.client)

    def test_chain_length_at_least_one(self):
        """即使没有 fallback provider，链也至少有 1 项。"""
        s = make_session()
        chain = s._text_fallback_chain()
        assert len(chain) >= 1


class TestIsStreamError:
    """_is_stream_error 检测流式输出错误标记。"""

    def test_detect_connect_error(self):
        s = make_session()
        assert s._is_stream_error("[流中断: ConnectError]") is True

    def test_detect_http_error(self):
        s = make_session()
        assert s._is_stream_error("[HTTP 503]") is True

    def test_normal_text_not_error(self):
        s = make_session()
        assert s._is_stream_error("这是一段正常回复") is False

    def test_empty_buffer_not_error(self):
        s = make_session()
        assert s._is_stream_error("") is False


class TestVisionComplexity:
    """_classify_vision_complexity 视觉任务复杂度分级。"""

    def test_simple_description_is_light(self):
        s = make_session()
        complexity, max_tok = s._classify_vision_complexity("描述这张图片")
        assert complexity == "light"
        assert max_tok == 2048

    def test_code_in_image_is_complex(self):
        s = make_session()
        complexity, max_tok = s._classify_vision_complexity("读一下这段代码")
        assert complexity == "complex"
        assert max_tok == 4096

    def test_counting_is_complex(self):
        s = make_session()
        complexity, max_tok = s._classify_vision_complexity("数一数有几只猫")
        assert complexity == "complex"
        assert max_tok == 4096

    def test_comparison_is_complex(self):
        s = make_session()
        complexity, max_tok = s._classify_vision_complexity("对比这两张图的区别")
        assert complexity == "complex"
        assert max_tok == 4096

    def test_empty_text_is_light(self):
        s = make_session()
        complexity, max_tok = s._classify_vision_complexity("")
        assert complexity == "light"
        assert max_tok == 2048


class TestSendStreamFallback:
    """send_stream 主对话流式 fallback 集成测试。

    使用 mock client 模拟主模型流中断 → 自动降级到备选模型。
    """

    def _make_fallback_session(self, primary_error, fallback_response):
        """构造一个主模型报错、备选模型成功的 session。

        Args:
            primary_error: 主模型 chat_stream yield 的错误内容
            fallback_response: 备选模型 chat_stream yield 的正常内容
        """
        mock_primary = MagicMock()
        mock_fallback = MagicMock()

        # 主模型产生错误标记
        mock_primary.chat_stream.return_value = iter(
            [
                {"content": primary_error, "_finish": "error"},
            ]
        )
        # 备选模型产生正常回复
        mock_fallback.chat_stream.return_value = iter(
            [
                {"content": fallback_response},
            ]
        )

        s = ChatSession(mock_primary)
        # 手动注入 fallback chain
        s._text_fallback_chain = lambda: [
            ("model-a", mock_primary),
            ("model-b", mock_fallback),
        ]
        return s

    def test_fallback_on_stream_error(self):
        """主模型流中断时自动降级到备选。"""
        s = self._make_fallback_session(
            primary_error="\n[流中断: ConnectError]",
            fallback_response="fallback reply",
        )
        results = list(s.send_stream("hello"))
        # 应有 info 提示 + fallback 回复
        texts = [r[1] for r in results if r[0] == "text"]
        infos = [r[1] for r in results if r[0] == "info"]
        assert any("连接中断" in i for i in infos), f"Expected fallback info, got {infos}"
        assert "fallback reply" in "".join(texts)

    def test_no_fallback_on_normal_response(self):
        """正常响应时不触发 fallback。"""
        mock_client = MagicMock()
        mock_client.chat_stream.return_value = iter(
            [
                {"content": "正常回复"},
            ]
        )
        s = ChatSession(mock_client)
        results = list(s.send_stream("hello"))
        texts = [r[1] for r in results if r[0] == "text"]
        infos = [r[1] for r in results if r[0] == "info"]
        assert "正常回复" in "".join(texts)
        assert not any("fallback" in i.lower() for i in infos)

    def test_no_fallback_when_chain_exhausted(self):
        """fallback 链耗尽时返回错误信息。"""
        mock_client = MagicMock()
        mock_client.chat_stream.return_value = iter(
            [
                {"content": "\n[HTTP 503]", "_finish": "error"},
            ]
        )
        s = ChatSession(mock_client)
        # 只有主模型，无备选
        s._text_fallback_chain = lambda: [
            ("model-a", mock_client),
        ]
        results = list(s.send_stream("hello"))
        texts = [r[1] for r in results if r[0] == "text"]
        assert "[HTTP 503]" in "".join(texts)
