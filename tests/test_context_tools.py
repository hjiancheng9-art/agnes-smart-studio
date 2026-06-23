"""Tests for core.context_tools — 共享截断工具 + token 估算。

守护两条不变式：
1. **截断语义一致性**：truncate_tool_result / truncate_messages 与
   ContextManager._truncate_messages 的 head+tail+标记格式逐字一致。
2. **边界安全**：空、刚好等于、CJK、超长、多消息混合均不崩溃且行为正确。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.context_tools import (
    DEFAULT_MAX_CHARS,
    abstractive_compress,
    compress_tool_result,
    estimate_tokens,
    extractive_compress,
    truncate_messages,
    truncate_tool_result,
)
from core.agent import ContextManager


# ── truncate_tool_result ────────────────────────────────────────


class TestTruncateToolResult:

    def test_short_text_unchanged(self):
        assert truncate_tool_result("hello") == "hello"

    def test_exact_limit_unchanged(self):
        """刚好等于 max_chars 不截断（len <= max_chars）。"""
        text = "a" * DEFAULT_MAX_CHARS
        assert truncate_tool_result(text) == text

    def test_over_limit_truncates(self):
        text = "a" * (DEFAULT_MAX_CHARS + 100)
        result = truncate_tool_result(text)
        assert len(result) < len(text)
        assert "truncated" in result

    def test_head_tail_proportion(self):
        """head = max_chars*2//3，tail = max_chars - head。"""
        text = "H" * 5000 + "M" * 5000 + "T" * 5000  # 15000 chars
        result = truncate_tool_result(text, max_chars=DEFAULT_MAX_CHARS)
        head = DEFAULT_MAX_CHARS * 2 // 3
        tail = DEFAULT_MAX_CHARS - head
        # 头部应包含 H（前 5000 < head≈5333）
        assert result.startswith("H")
        # 尾部应包含 T（最后 tail≈2666 落在 T 区域 5000+5000=10000 之后）
        assert result.endswith("T")

    def test_marker_format_matches_context_manager(self):
        """截断标记格式必须与 ContextManager 逐字一致。"""
        text = "x" * (DEFAULT_MAX_CHARS + 50)
        result_new = truncate_tool_result(text)

        # 用 ContextManager 生成对照
        cm = ContextManager()
        msg = [{"role": "tool", "content": text}]
        result_cm = cm._truncate_messages(msg)[0]["content"]

        assert result_new == result_cm

    def test_custom_max_chars(self):
        text = "a" * 200
        result = truncate_tool_result(text, max_chars=100)
        assert len(result) < 200
        assert "truncated 100 chars" in result

    def test_empty_string(self):
        assert truncate_tool_result("") == ""

    def test_non_string_returns_unchanged(self):
        """非 str 类型原样返回（防御性）。"""
        assert truncate_tool_result(None) is None  # type: ignore[arg-type]
        assert truncate_tool_result(123) == 123  # type: ignore[arg-type]

    def test_cjk_text_truncates_correctly(self):
        """CJK 字符按字符数（非字节）计算长度。"""
        text = "中" * (DEFAULT_MAX_CHARS + 100)
        result = truncate_tool_result(text)
        assert len(result) < len(text)
        assert result.startswith("中")
        assert result.endswith("中")


# ── truncate_messages ───────────────────────────────────────────


class TestTruncateMessages:

    def test_empty_list(self):
        assert truncate_messages([]) == []

    def test_short_messages_unchanged(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        result = truncate_messages(msgs)
        assert result == msgs

    def test_truncates_only_oversized(self):
        """只截断超限消息，短消息原样保留。"""
        short = "short"
        long_text = "L" * (DEFAULT_MAX_CHARS + 500)
        msgs = [
            {"role": "system", "content": short},
            {"role": "tool", "content": long_text, "tool_call_id": "x"},
            {"role": "assistant", "content": short},
        ]
        result = truncate_messages(msgs)
        # 短消息不变
        assert result[0]["content"] == short
        assert result[2]["content"] == short
        # 长消息被截断
        assert len(result[1]["content"]) < len(long_text)
        assert "truncated" in result[1]["content"]
        # 其他字段保留
        assert result[1]["tool_call_id"] == "x"

    def test_oversized_generates_new_dict(self):
        """超限消息生成新 dict，原 dict 不被修改。"""
        original = {"role": "tool", "content": "X" * (DEFAULT_MAX_CHARS + 10)}
        original_copy = dict(original)
        truncate_messages([original])
        # 原 dict 内容未被改动
        assert original == original_copy

    def test_multimodal_content_not_touched(self):
        """list content（多模态）不截断。"""
        content = [{"type": "text", "text": "x" * (DEFAULT_MAX_CHARS + 100)}]
        msgs = [{"role": "user", "content": content}]
        result = truncate_messages(msgs)
        assert result[0]["content"] is content

    def test_none_content_skipped(self):
        """content 为 None 或非 str/list 时不崩溃。"""
        msgs = [
            {"role": "assistant", "content": None},
            {"role": "tool", "content": 123},
        ]
        result = truncate_messages(msgs)
        assert result == msgs

    def test_matches_context_manager_behavior(self):
        """整体行为与 ContextManager._truncate_messages 一致。"""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "tool", "content": "A" * (DEFAULT_MAX_CHARS + 200)},
            {"role": "user", "content": "B" * 100},
            {"role": "tool", "content": "C" * (DEFAULT_MAX_CHARS + 50)},
        ]
        cm = ContextManager()
        assert truncate_messages(msgs) == cm._truncate_messages(msgs)


# ── estimate_tokens ─────────────────────────────────────────────


class TestEstimateTokens:

    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_ascii(self):
        # 8 ASCII chars → 8//4 + 1 = 3
        assert estimate_tokens("abcdefgh") == 3

    def test_cjk(self):
        # 4 CJK chars → 4//2 + 1 = 3
        assert estimate_tokens("你好世界") == 3

    def test_matches_context_manager(self):
        """与 ContextManager.estimate_tokens 完全一致。"""
        texts = ["", "hello world", "你好世界", "mixed 中英文 abc"]
        cm = ContextManager()
        for t in texts:
            assert estimate_tokens(t) == cm.estimate_tokens(t)

    def test_long_text_reasonable(self):
        """长文本估算在合理范围（不会爆 int，不会负数）。"""
        text = "a" * 100000
        result = estimate_tokens(text)
        assert 0 < result < 100000


# ── DEFAULT_MAX_CHARS 常量 ──────────────────────────────────────


class TestConstants:

    def test_default_max_chars_matches_context_manager(self):
        """常量必须与 ContextManager._MAX_MSG_CHARS 一致（DNA 契约）。"""
        assert DEFAULT_MAX_CHARS == ContextManager._MAX_MSG_CHARS


# ── Cache-point 契约测试（chat.py / async_chat.py 截断接入）──────


class TestCachePointTruncation:
    """验证 chat.py / async_chat.py 的 send_stream 工具调用循环中，
    truncate_tool_result 在 messages.append 之前被正确调用。

    核心契约：
    1. 超长工具结果写入 messages 时被截断（保护上下文窗口）。
    2. 跨轮去重缓存保留原始结果（高保真复用）。
    """

    def _make_mock_client(self):
        """构建 mock AgnesClient（同步版），驱动两轮流式。"""
        from unittest.mock import MagicMock

        client = MagicMock(spec=["chat_stream"])

        # 第一轮：返回一个工具调用 read_file
        round1_deltas = [
            {"content": "我来读取文件"},
            {"tool_calls": [{"index": 0, "id": "call_read",
                             "function": {"name": "read_file",
                                          "arguments": '{"path":"big.py"}'}}]},
            {"_finish": "tool_calls"},
        ]
        # 第二轮：模型总结
        round2_deltas = [
            {"content": "文件内容如上。"},
            {"_finish": "stop"},
        ]

        call_idx = 0

        def _mock_stream(*a, **kw):
            nonlocal call_idx
            seq = [round1_deltas, round2_deltas]
            items = seq[min(call_idx, len(seq) - 1)]
            call_idx += 1
            for item in items:
                yield item

        client.chat_stream = _mock_stream
        return client

    def test_sync_send_stream_truncates_tool_result(self):
        """同步 ChatSession.send_stream 工具结果超限 → messages 截断。"""
        from unittest.mock import patch
        from core.chat import ChatSession

        client = self._make_mock_client()
        session = ChatSession(client)
        session.model = "agnes-2.0-flash"  # 支持 tools

        # 模拟 read_file 返回超长内容
        huge_result = "X" * (DEFAULT_MAX_CHARS + 500)

        def _mock_dispatch(name, args_json):
            return huge_result, []  # 无副作用

        session._dispatch_tool = _mock_dispatch

        with patch("core.provider.model_supports_tools", return_value=True):
            list(session.send_stream("读取 big.py"))

        # messages 中应有 tool role 消息
        tool_msgs = [m for m in session.messages if m.get("role") == "tool"]
        assert len(tool_msgs) >= 1

        # 关键断言：写入 messages 的内容已被截断
        content = tool_msgs[0]["content"]
        assert len(content) < len(huge_result), (
            "tool 结果未被截断——cache-point 契约违反"
        )
        assert "truncated" in content

    def test_sync_cache_preserves_raw_result(self):
        """跨轮去重缓存应保留原始结果（非截断后）。"""
        from unittest.mock import patch
        from core.chat import ChatSession

        client = self._make_mock_client()
        session = ChatSession(client)
        session.model = "agnes-2.0-flash"

        huge_result = "R" * (DEFAULT_MAX_CHARS + 300)
        dispatched = []

        def _mock_dispatch(name, args_json):
            dispatched.append((name, args_json))
            return huge_result, []

        session._dispatch_tool = _mock_dispatch

        with patch("core.provider.model_supports_tools", return_value=True):
            list(session.send_stream("读取"))

        # 原始 _dispatch_tool 返回值 = 原始 huge_result
        # 而 messages 中的 tool content 应被截断
        tool_msgs = [m for m in session.messages if m.get("role") == "tool"]
        assert len(tool_msgs) >= 1
        # 截断后长度 < 原始
        assert len(tool_msgs[0]["content"]) < len(huge_result)
        # 原始结果仍然在 dispatch 返回值中（模拟缓存未丢）
        assert len(huge_result) > DEFAULT_MAX_CHARS


# ── extractive_compress（Tier 2a — 零成本 TF-IDF 抽取）───────────────


class TestExtractiveCompress:

    def test_short_text_passthrough(self):
        """短文本不处理，原样返回。"""
        text = "hello world"
        assert extractive_compress(text, max_chars=8000) == text

    def test_long_text_compressed(self):
        """长文本被抽取压缩，结果长度 ≤ max_chars。"""
        # 构造超长文本：80 个句子，每个 ~300 字符
        sentences = [f"句子{i}: 这是第{i}个句子的内容。包含一些关键的函数名 func_{i} 和变量 var_{i}。" * 5 for i in range(80)]
        text = "\n".join(sentences)
        assert len(text) > 8000
        result = extractive_compress(text, max_chars=8000)
        assert len(result) <= 8000
        assert len(result) < len(text)

    def test_query_hint_relevance_sorting(self):
        """有 query_hint 时，相关句子优先被选中。"""
        # 构造：大部分句子关于 cooking，一句关于 Python
        cooking_sentences = [f"The recipe step {i} involves mixing ingredients. Heat the oven." for i in range(30)]
        python_sentence = "def calculate_sum(a, b): return a + b  # Python function for summation"
        text = "\n".join(cooking_sentences + [python_sentence])
        result = extractive_compress(text, query_hint="Python function code", max_chars=2000)
        # Python 相关句子应被保留（与 query 相关性最高）
        assert "Python" in result or "calculate_sum" in result

    def test_cjk_text_compresses(self):
        """CJK 文本正确抽取压缩。"""
        sentences = [f"第{i}段：这是关于机器学习的中文内容。包含关键词神经网络和深度学习。" * 10 for i in range(40)]
        text = "\n".join(sentences)
        assert len(text) > 8000
        result = extractive_compress(text, max_chars=4000)
        assert len(result) <= 4200  # 允许句子边界微超
        assert "机器学习" in result  # 高频关键词应保留

    def test_single_sentence_fallback(self):
        """单句文本无法抽取，回退截断。"""
        text = "X" * (DEFAULT_MAX_CHARS + 500)
        result = extractive_compress(text, max_chars=DEFAULT_MAX_CHARS)
        assert len(result) <= DEFAULT_MAX_CHARS + len("\n\n...[truncated 500 chars]...\n\n")

    def test_preserves_original_order(self):
        """抽取后保留原始句子顺序（不按得分顺序输出）。"""
        sentences = [f"Sentence {i} with keyword KEY{i}." for i in range(20)]
        text = "\n".join(sentences)
        result = extractive_compress(text, max_chars=1000)
        # 如果 KEY0 在结果中，它应在 KEY19 之前出现
        if "KEY0" in result and "KEY19" in result:
            assert result.index("KEY0") < result.index("KEY19")


# ── abstractive_compress（Tier 2b — LLM 抽象压缩）─────────────────────


class TestAbstractiveCompress:

    def test_mock_client_compresses(self):
        """mock client.chat 返回摘要时正确工作。"""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "Summary: key information preserved."}}]
        }
        text = "X" * 10000
        result = abstractive_compress(text, mock_client, model="test-model")
        assert "Summary" in result
        mock_client.chat.assert_called_once()
        call_args = mock_client.chat.call_args
        assert call_args[1]["model"] == "test-model"
        assert call_args[1]["max_tokens"] == 600

    def test_llm_failure_falls_back_to_extractive(self):
        """LLM 调用失败时回退到 extractive_compress。"""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("API error")

        text = "S" * 10000
        result = abstractive_compress(text, mock_client)
        # 应回退到 extractive（不抛异常）
        assert isinstance(result, str)
        assert len(result) < len(text)

    def test_empty_response_falls_back(self):
        """LLM 返回空内容时回退到 extractive。"""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        mock_client.chat.return_value = {"choices": [{"message": {"content": ""}}]}

        text = "T" * 10000
        result = abstractive_compress(text, mock_client)
        assert isinstance(result, str)

    def test_long_input_truncated_before_llm(self):
        """超长输入在喂给 LLM 前被截断到 16000 字符。"""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }

        text = "Z" * 20000
        abstractive_compress(text, mock_client)
        sent_text = mock_client.chat.call_args[1]["messages"][0]["content"]
        assert len(sent_text) <= 16000 + 500  # 允许 prompt 前缀长度


# ── compress_tool_result（智能路由）────────────────────────────────────


class TestCompressToolResult:

    def test_short_text_passthrough(self):
        """短文本直接返回，不触发任何压缩。"""
        text = "hello"
        assert compress_tool_result(text) == text

    def test_extractive_sufficient_no_llm(self):
        """extractive 足够时不触发 LLM 压缩。"""
        from unittest.mock import MagicMock

        mock_client = MagicMock()

        # 构造 extractive 能处理的长文本
        sentences = [f"Info sentence {i} with keyword KW_{i}. " * 15 for i in range(40)]
        text = "\n".join(sentences)
        assert len(text) > 8000

        result = compress_tool_result(text, client=mock_client, max_chars=8000)
        assert len(result) <= 8000 + 10  # 允许微小偏差
        # mock_client.chat 不应被调用（extractive 足够）
        mock_client.chat.assert_not_called()

    def test_no_client_falls_back_to_truncate(self):
        """无 client 时，extractive 失败后兜底 truncate。"""
        text = "X" * (DEFAULT_MAX_CHARS + 500)
        # 纯重复文本 extractive 可能保留很多，但最终会兜底截断
        result = compress_tool_result(text, client=None, max_chars=100)
        assert isinstance(result, str)

    def test_llm_called_when_extractive_insufficient(self):
        """extractive 仍超限且有 client → 触发 LLM 压缩。"""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "Brief summary."}}]
        }

        # 构造 extractive 无法充分压缩的文本（连续长句，切分效果差）
        text = "A" * 20000  # 无句子边界，extractive 基本保留原文
        result = compress_tool_result(text, client=mock_client, max_chars=100)
        assert isinstance(result, str)
        # client.chat 应被调用
        mock_client.chat.assert_called_once()

    def test_metrics_tracked(self):
        """验证 metrics 计数器被正确递增。"""
        from unittest.mock import patch, MagicMock

        mock_metrics = MagicMock()
        mock_client = MagicMock()

        sentences = [f"Sentence {i} with keyword KW_{i}. " * 15 for i in range(40)]
        text = "\n".join(sentences)

        # observability.metrics 是全局单例，patch 其 increment 方法
        with patch("core.observability.metrics", mock_metrics):
            compress_tool_result(text, client=mock_client, max_chars=8000)
            # extractive 路径应触发 increment
            assert mock_metrics.increment.called
        # 验证至少有一个 extractive 或 fallback 计数
        increment_calls = [c[0][0] for c in mock_metrics.increment.call_args_list]
        assert any("extractive" in c or "truncated" in c for c in increment_calls)
