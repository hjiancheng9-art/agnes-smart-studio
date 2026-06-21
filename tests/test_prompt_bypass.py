"""Tests for core.prompt_bypass — content-policy auto-bypass engine."""

import pytest
from unittest.mock import MagicMock


class TestPolicyDetection:
    def test_is_policy_error_english(self):
        from core.prompt_bypass import is_policy_error
        assert is_policy_error(Exception("content_policy violation")) is True
        assert is_policy_error(Exception("blocked by safety filter")) is True

    def test_is_policy_error_chinese(self):
        from core.prompt_bypass import is_policy_error
        assert is_policy_error(Exception("无法生成该内容")) is True
        assert is_policy_error(Exception("请调整提示词")) is True

    def test_is_not_policy_error(self):
        from core.prompt_bypass import is_policy_error
        assert is_policy_error(Exception("connection timeout")) is False
        assert is_policy_error(Exception("500 internal server error")) is False

    def test_detect_trigger_words(self):
        from core.prompt_bypass import _detect_trigger_words
        triggers = _detect_trigger_words("a battle with blood and weapons")
        assert "blood" in triggers
        # weapon is in the list
        assert any(t == "blood" for t in triggers)

    def test_detect_trigger_words_none(self):
        from core.prompt_bypass import _detect_trigger_words
        assert _detect_trigger_words("a peaceful sunset") == []


class TestStrategies:
    def test_strategies_have_required_fields(self):
        from core.prompt_bypass import STRATEGIES
        assert len(STRATEGIES) >= 3
        for s in STRATEGIES:
            assert "name" in s
            assert "system" in s
            assert "instruction" in s
            assert "temperature" in s

    def test_strategy_names_escalate(self):
        from core.prompt_bypass import STRATEGIES
        names = [s["name"] for s in STRATEGIES]
        # First strategy should be the gentlest
        assert names[0] == "gentle"

    def test_figure_strategies_present(self):
        from core.prompt_bypass import FIGURE_STRATEGIES
        assert len(FIGURE_STRATEGIES) >= 2
        names = [s["name"] for s in FIGURE_STRATEGIES]
        assert "classical" in names


class TestCache:
    def test_load_cache_missing_file(self, tmp_path, monkeypatch):
        from core import prompt_bypass as pb
        monkeypatch.setattr(pb, "CACHE_FILE", tmp_path / "noexist.json")
        cache = pb._load_cache()
        assert cache == {"patterns": {}, "rewrites": {}}

    def test_save_then_load_cache(self, tmp_path, monkeypatch):
        from core import prompt_bypass as pb
        cache_file = tmp_path / "cache.json"
        monkeypatch.setattr(pb, "CACHE_FILE", cache_file)
        data = {"patterns": {"gentle": 2}, "rewrites": {"x": {"rewritten": "y"}}}
        pb._save_cache(data)
        assert cache_file.exists()
        loaded = pb._load_cache()
        assert loaded == data

    def test_load_cache_handles_corrupt_json(self, tmp_path, monkeypatch):
        from core import prompt_bypass as pb
        cache_file = tmp_path / "corrupt.json"
        cache_file.write_text("not valid json {{{", encoding="utf-8")
        monkeypatch.setattr(pb, "CACHE_FILE", cache_file)
        cache = pb._load_cache()
        assert cache == {"patterns": {}, "rewrites": {}}


class TestRewritePrompt:
    def _mock_client(self, content="a safe rewritten prompt about nature"):
        client = MagicMock()
        client.chat.return_value = {
            "choices": [{"message": {"content": content}}]
        }
        return client

    def test_rewrite_returns_content(self):
        from core.prompt_bypass import rewrite_prompt
        client = self._mock_client()
        result = rewrite_prompt(client, "a violent battle scene", strategy_index=0)
        assert result is not None
        assert isinstance(result, str)

    def test_rewrite_strips_prefix(self):
        from core.prompt_bypass import rewrite_prompt
        client = self._mock_client(content="Here is the rewritten prompt: a calm scene")
        result = rewrite_prompt(client, "fight", strategy_index=0)
        assert result is not None
        assert not result.lower().startswith("here")

    def test_rewrite_returns_none_on_short_output(self):
        from core.prompt_bypass import rewrite_prompt
        client = self._mock_client(content="short")  # <= 10 chars
        result = rewrite_prompt(client, "battle", strategy_index=0)
        assert result is None

    def test_rewrite_returns_none_for_invalid_index(self):
        from core.prompt_bypass import rewrite_prompt
        client = self._mock_client()
        result = rewrite_prompt(client, "x", strategy_index=999)
        assert result is None

    def test_rewrite_caches_result(self, tmp_path, monkeypatch):
        from core import prompt_bypass as pb
        monkeypatch.setattr(pb, "CACHE_FILE", tmp_path / "c.json")
        client = self._mock_client()
        cache = pb._load_cache()
        pb.rewrite_prompt(client, "a gory fight scene", strategy_index=0, cache=cache)
        assert len(cache["rewrites"]) >= 1

    def test_rewrite_handles_client_error(self):
        from core.prompt_bypass import rewrite_prompt
        client = MagicMock()
        client.chat.side_effect = RuntimeError("api down")
        result = rewrite_prompt(client, "battle", strategy_index=0)
        assert result is None


class TestGenerateWithBypass:
    def test_success_first_try_no_rewrite(self):
        from core.prompt_bypass import generate_with_bypass
        engine = MagicMock()
        engine.return_value = {"url": "ok.png"}
        result, rewritten = generate_with_bypass(engine, MagicMock(), "peaceful landscape")
        assert result == {"url": "ok.png"}
        assert rewritten is None

    def test_disabled_raises_policy_error_directly(self, monkeypatch):
        from core import prompt_bypass as pb
        monkeypatch.setattr(pb, "BYPASS_ENABLED", False)

        def engine(prompt, **kw):
            raise RuntimeError("content_policy violation")
        with pytest.raises(RuntimeError):
            pb.generate_with_bypass(engine, MagicMock(), "something")

    def test_non_policy_error_propagates(self):
        from core.prompt_bypass import generate_with_bypass
        call_count = [0]

        def engine(prompt, **kw):
            call_count[0] += 1
            raise OSError("disk full")  # not a policy error
        with pytest.raises(OSError):
            generate_with_bypass(engine, MagicMock(), "x")
        assert call_count[0] == 1  # no retries

    def test_get_bypass_stats(self, tmp_path, monkeypatch):
        from core import prompt_bypass as pb
        monkeypatch.setattr(pb, "CACHE_FILE", tmp_path / "c.json")
        stats = pb.get_bypass_stats()
        assert "cached_rewrites" in stats
        assert "strategy_usage" in stats
