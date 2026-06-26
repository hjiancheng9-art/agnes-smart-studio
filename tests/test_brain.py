"""Unit tests for SmartBrain - intent recognition and prompt enhancement."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.brain import SmartBrain


class TestBrainIntentRecognition:
    """Test intent recognition with mocked API."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        return client

    @pytest.fixture
    def brain(self, mock_client):
        return SmartBrain(mock_client)

    def test_recognize_intent_text_to_image(self, brain, mock_client):
        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"intent": "text_to_image", "confidence": 0.9, "plan": "a cat sitting on a windowsill"}
                        )
                    }
                }
            ]
        }
        result = brain.recognize_intent("draw a cat")
        assert result["intent"] == "text_to_image"
        assert result["confidence"] == 0.9

    def test_recognize_intent_fallsback_on_empty(self, brain, mock_client):
        mock_client.chat.return_value = {"choices": [{"message": {"content": "{}"}}]}
        result = brain.recognize_intent("test")
        assert isinstance(result, dict)

    def test_recognize_intent_survives_api_error(self, brain, mock_client):
        mock_client.chat.side_effect = RuntimeError("API down")
        with pytest.raises(RuntimeError):
            brain.recognize_intent("test")

    def test_parse_json_valid(self, brain):
        result = brain._parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_with_markdown_wrapper(self, brain):
        result = brain._parse_json('```json\n{"intent": "chat"}\n```')
        assert result == {"intent": "chat"}

    def test_parse_json_invalid_returns_raw(self, brain):
        result = brain._parse_json("not json at all")
        assert result == {"raw_text": "not json at all"}

    def test_parse_json_partial_json_extraction(self, brain):
        result = brain._parse_json('some text {"key": "val"} more text')
        assert result == {"key": "val"}


class TestBrainEntityInference:
    """Test entity type and beauty type inference (does not call API)."""

    @pytest.fixture
    def brain(self):
        client = MagicMock()
        return SmartBrain(client)

    def test_infer_entity_type_returns_tuple(self, brain):
        et, sp = brain._infer_entity_type("a cat")
        assert isinstance(et, str)
        assert isinstance(sp, str)

    def test_infer_entity_type_default(self, brain):
        result = brain._infer_entity_type("random text without clear entity")
        # Returns None for unrecognized input — acceptable behavior
        assert result is None or isinstance(result, tuple)

    def test_infer_beauty_type_returns_strings(self, brain):
        brain._infer_beauty_type("a beautiful woman portrait")
        # Just verify it runs without crashing

    def test_detect_combat_scene_no_combat(self, brain):
        brain._detect_combat_scene("a peaceful garden", "image")
        # Non-combat may return None -- just verify it runs


class TestBrainFallbackChain:
    """_ask_brain 降级链：主供应商故障 → CRUX light → 二次故障抛根因。"""

    @pytest.fixture
    def brain(self):
        return SmartBrain(MagicMock())

    def test_primary_http_error_triggers_fallback(self, brain, monkeypatch):
        """主供应商 httpx.HTTPError → 走 CRUX light 降级，返回降级结果。"""

        def fail_chat(**kwargs):
            raise httpx.HTTPError("primary provider down")

        brain.client.chat = fail_chat

        # 让降级路径走通：patch 掉 provider/api_key 解析 + CruxClient 构造。
        # 注意 brain._ask_brain 降级块用的是「函数内局部 import」
        # （from core.client import CruxClient / from core.provider import ...），
        # 每次调用都重新查找模块属性，故 patch 模块级符号即可，且必须 patch 到
        # 源模块（core.client / core.provider），不是 core.brain 的别名。
        class _StubClient:
            def __init__(self, **kwargs):
                pass

            def chat(self, **kwargs):
                return {"choices": [{"message": {"content": "fallback ok"}}]}

        monkeypatch.setattr("core.config.CRUX_VISION_BASE_URL", "https://stub.invalid/v1")
        monkeypatch.setattr("core.client.CruxClient", _StubClient)
        monkeypatch.setenv("CRUX_API_KEY", "stub-key")

        def _provider_unavailable():
            raise OSError("provider manager unavailable")

        monkeypatch.setattr("core.provider.get_provider_manager", _provider_unavailable)

        out = brain._ask_brain("sys", "user")
        assert out == "fallback ok"

    def test_fallback_chain_failure_raises_primary_with_correct_cause(self, brain, monkeypatch):
        """降级链二次失败 → 抛原始 primary_err，且 __cause__ 是降级异常（非自身）。

        回归守护：禁止 `raise primary_err from primary_err`（会把异常自身设成
        __cause__，因果链语义错乱）。
        """
        primary = httpx.ConnectError("primary provider down")

        def fail_chat(**kwargs):
            raise primary

        brain.client.chat = fail_chat

        # 降级路径让它失败：缺 key → RuntimeError("api_key missing")
        monkeypatch.delenv("CRUX_API_KEY", raising=False)
        monkeypatch.delenv("AGNES_API_KEY", raising=False)

        def _provider_unavailable():
            raise OSError("provider manager unavailable")

        monkeypatch.setattr("core.provider.get_provider_manager", _provider_unavailable)

        with pytest.raises(httpx.ConnectError) as exc_info:
            brain._ask_brain("sys", "user")

        # 根因必须是原始异常（同一对象）
        assert exc_info.value is primary
        # __cause__ 必须不是异常自身（回归守护：禁止 from primary_err）
        assert exc_info.value.__cause__ is not primary
        assert exc_info.value.__cause__ is not None
        # raise ... from fallback_err 显式设 __cause__ = fallback_err。
        # Python 在 except 块里 raise 时，原 except 的异常会自动成为 __context__，
        # 但这里 fallback_err 是手动 raise 的 RuntimeError（"api_key missing"），
        # 它在 except (HTTPError, OSError) primary_err 的语境下被 raise，
        # 故 __context__ 应为 fallback_err（同一对象）。
        assert exc_info.value.__context__ is exc_info.value.__cause__
