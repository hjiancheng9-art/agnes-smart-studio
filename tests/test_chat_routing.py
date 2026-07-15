"""Unit tests for core/chat_routing.py — pure routing helpers (refactor P2).

Covers classify_vision_complexity and is_stream_error. Also asserts the
ChatSession wrappers delegate to these, so behavior is identical to pre-refactor.
"""

from core.chat import ChatSession
from core.chat_routing import classify_vision_complexity, is_stream_error


class TestClassifyVisionComplexity:
    def test_simple_description_is_light(self):
        assert classify_vision_complexity("describe this image") == ("light", 2048)
        assert classify_vision_complexity("这是什么") == ("light", 2048)

    def test_empty_is_light(self):
        assert classify_vision_complexity("") == ("light", 2048)

    def test_counting_is_complex(self):
        assert classify_vision_complexity("数一数几个") == ("complex", 4096)
        assert classify_vision_complexity("how many people") == ("complex", 4096)

    def test_code_is_complex(self):
        assert classify_vision_complexity("分析这段 code") == ("complex", 4096)

    def test_chart_is_complex(self):
        assert classify_vision_complexity("画个流程图 flowchart") == ("complex", 4096)

    def test_compare_is_complex(self):
        assert classify_vision_complexity("对比这两张图的区别") == ("complex", 4096)

    def test_returns_tier_and_token_budget(self):
        tier, budget = classify_vision_complexity("compute the area")
        assert tier == "complex"
        assert budget == 4096


class TestIsStreamError:
    def test_empty_is_not_error(self):
        assert is_stream_error("") is False

    def test_stream_break_prefix_is_error(self):
        assert is_stream_error("[流中断] something") is True

    def test_http_prefix_is_error(self):
        assert is_stream_error("[HTTP 500] boom") is True

    def test_plain_text_is_not_error(self):
        assert is_stream_error("hello world") is False

    def test_substring_not_at_start_is_not_error(self):
        # "流中断" appearing mid-text must NOT false-trigger.
        assert is_stream_error("用户提到流中断这个词") is False


class TestChatSessionDelegation:
    def test_classify_delegates(self):
        assert ChatSession._classify_vision_complexity("数一数") == classify_vision_complexity("数一数")

    def test_is_stream_error_delegates(self):
        class Dummy:
            pass

        assert ChatSession._is_stream_error(Dummy(), "[HTTP 429]") == is_stream_error("[HTTP 429]")
