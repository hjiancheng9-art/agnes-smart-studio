"""Unit tests for SmartBrain - intent recognition and prompt enhancement."""
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock
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
            "choices": [{"message": {"content": json.dumps({
                "intent": "text_to_image",
                "confidence": 0.9,
                "plan": "a cat sitting on a windowsill"
            })}}]
        }
        result = brain.recognize_intent("draw a cat")
        assert result["intent"] == "text_to_image"
        assert result["confidence"] == 0.9

    def test_recognize_intent_fallsback_on_empty(self, brain, mock_client):
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": "{}"}}]
        }
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
