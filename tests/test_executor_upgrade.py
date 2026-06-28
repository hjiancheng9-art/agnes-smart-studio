"""Tests for executor upgrades: SmartPlanner, SemanticVerifier, SelfReflection."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.executor import (
    AdjustResult,
    SelfReflection,
    SemanticVerifier,
    SmartPlanner,
    Step,
    Task,
    TaskExecutor,
    quick_plan,
    smart_plan,
)


class TestSmartPlanner:
    """SmartPlanner: LLM planning + fallback to quick_plan."""

    def test_llm_plan_success(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '[{"id":"s1","description":"Read code","tool":"read_file","args":{"path":"x.py"},"depends_on":[],"verify":null}]'
                    }
                }
            ]
        }
        planner = SmartPlanner(client=mock_client)
        task = planner.plan("refactor x.py")
        assert task.goal == "refactor x.py"
        assert len(task.steps) == 1
        assert task.steps[0].tool == "read_file"
        assert task.reflection_enabled is True

    def test_llm_plan_fallback_on_empty(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {"choices": [{"message": {"content": ""}}]}
        planner = SmartPlanner(client=mock_client)
        task = planner.plan("fix bug")
        assert len(task.steps) == 4
        assert task.steps[0].tool == "read_file"

    def test_llm_plan_fallback_on_exception(self):
        mock_client = MagicMock()
        mock_client.chat.side_effect = OSError("connection refused")
        planner = SmartPlanner(client=mock_client)
        task = planner.plan("fix bug")
        assert len(task.steps) == 4

    def test_extract_json_direct(self):
        raw = '[{"id":"s1","tool":"read"}]'
        assert SmartPlanner._extract_json(raw) == raw

    def test_extract_json_from_code_block(self):
        raw = 'Sure, here is the plan:\n```json\n[{"id":"s1","tool":"read"}]\n```\nDone.'
        result = SmartPlanner._extract_json(raw)
        assert '[{"id":"s1","tool":"read"}]' in result

    def test_extract_json_truncated(self):
        raw = 'Here: [{"id":"s1"}] and some trailing text'
        result = SmartPlanner._extract_json(raw)
        assert result == '[{"id":"s1"}]'


class TestSemanticVerifier:
    """SemanticVerifier: goal-mode semantic validation."""

    def test_verify_goal_achieved(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": '{"achieved": true, "gap": ""}'}}]
        }
        verifier = SemanticVerifier(client=mock_client)
        step = Step("s1", "Fix auth", "edit_file", {"path": "core/auth.py"}, verify="goal", status="done", result="Fixed")
        task = Task(id="t", goal="Fix auth bug", steps=[step])
        achieved, gap = verifier.verify("Fix auth bug", task)
        assert achieved is True
        assert gap == ""

    def test_verify_goal_not_achieved(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": '{"achieved": false, "gap": "Missing error handling"}'}}]
        }
        verifier = SemanticVerifier(client=mock_client)
        step = Step("s1", "Fix auth", "edit_file", {"path": "core/auth.py"}, verify="goal", status="done", result="Partial fix")
        task = Task(id="t", goal="Fix auth bug", steps=[step])
        achieved, gap = verifier.verify("Fix auth bug", task)
        assert achieved is False
        assert "Missing error handling" in gap

    def test_verify_llm_unavailable_passes(self):
        mock_client = MagicMock()
        mock_client.chat.side_effect = OSError("connection refused")
        verifier = SemanticVerifier(client=mock_client)
        step = Step("s1", "Fix", "edit_file", {}, verify="goal", status="done", result="ok")
        task = Task(id="t", goal="Fix something", steps=[step])
        achieved, gap = verifier.verify("Fix something", task)
        assert achieved is True

    def test_verify_no_goal_steps_passes(self):
        verifier = SemanticVerifier()
        step = Step("s1", "Test", "run_test", {}, status="done")
        task = Task(id="t", goal="Test", steps=[step])
        achieved, gap = verifier.verify("Test", task)
        assert achieved is True

    def test_parse_verify_json_safe_default(self):
        assert SemanticVerifier._parse_verify_json("garbage") == {"achieved": True, "gap": ""}


class TestSelfReflection:
    """SelfReflection: failure analysis + retry/replan/skip."""

    def test_auto_retry_for_network_error(self):
        step = Step("s1", "Fetch data", "web_fetch", {"url": "http://example.com"})
        reflector = SelfReflection()
        result = reflector.analyze_and_adjust("Fetch data", step, "Connection timeout")
        assert result.action == "retry"

    def test_auto_retry_for_rate_limit(self):
        step = Step("s1", "API call", "http_api", {})
        reflector = SelfReflection()
        result = reflector.analyze_and_adjust("Call API", step, "429 rate limit exceeded")
        assert result.action == "retry"

    def test_llm_reflect_for_unknown_error(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"action": "replan", "tool": "search_files", "args": {"pattern": "auth"}, "reason": "Wrong tool"}'
                    }
                }
            ]
        }
        reflector = SelfReflection(client=mock_client)
        step = Step("s1", "Fix auth", "edit_file", {"path": "auth.py"})
        result = reflector.analyze_and_adjust("Fix auth bug", step, "Unknown error: file not found")
        assert result.action == "replan"
        assert result.tool == "search_files"

    def test_reflect_fallback_skip_on_parse_failure(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {"choices": [{"message": {"content": "garbage"}}]}
        reflector = SelfReflection(client=mock_client)
        step = Step("s1", "Test", "edit_file", {})
        result = reflector.analyze_and_adjust("Test", step, "some error")
        assert result.action == "skip"

    def test_parse_reflect_json_safe_default(self):
        fallback = Step("s1", "Fallback", "read_file", {"path": "x.py"})
        result = SelfReflection._parse_reflect_json("not json at all", fallback)
        assert result.action == "skip"
        assert result.tool == "read_file"


class TestReflectionIntegration:
    """TaskExecutor.run() self-repair when reflection_enabled=True."""

    def test_reflection_retry_on_transient_error(self, monkeypatch):
        """Network error auto-retry: first call fails, second succeeds."""
        call_count = [0]

        def tool_fn(name, args):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("Connection timeout")
            return "success"

        # Ensure ErrorClassifier classifies this as network_error (auto-retry)
        # OSError with "timeout" should match the NETWORK_ERROR pattern already
        task = Task(
            id="t_reflect",
            goal="fetch data",
            steps=[Step("s1", "Fetch", "web_fetch", {"url": "http://x.com"})],
            errors_allowed=0,
            reflection_enabled=True,
            max_retries_per_step=2,
        )

        report = TaskExecutor(tool_fn, root=ROOT).run(task)
        # Network error → auto-retry → second call succeeds
        assert call_count[0] == 2
        assert task.steps[0].status == "done"

    def test_reflection_skip_on_max_retries(self, monkeypatch):
        # Mock ErrorClassifier to return non-retryable type so it goes to LLM,
        # then mock LLM to return "skip" action
        def tool_fn(name, args):
            raise OSError("always fails")

        # Mock the ErrorClassifier to return "validation_error" (not auto-retry)
        class FakeErrorClassifier:
            @classmethod
            def classify(cls, error):
                from core.resilience import ErrorType
                return ErrorType.VALIDATION_ERROR
            @classmethod
            def get_recovery_hint(cls, error):
                return "Check parameters"

        monkeypatch.setattr("core.resilience.ErrorClassifier", FakeErrorClassifier)

        # Mock LLM to return skip
        from core.client import CruxClient
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [{"message": {"content": '{"action": "skip", "reason": "unrecoverable"}'}}]
        }

        from core.executor import SelfReflection
        orig_init = SelfReflection.__init__
        def patched_init(self, client=None, model=""):
            orig_init(self, client=mock_client, model=model)
        monkeypatch.setattr(SelfReflection, "__init__", patched_init)

        task = Task(
            id="t_reflect_max",
            goal="impossible",
            steps=[Step("s1", "Fail", "web_fetch", {})],
            errors_allowed=0,
            reflection_enabled=True,
            max_retries_per_step=1,
        )

        report = TaskExecutor(tool_fn, root=ROOT).run(task)
        assert task.steps[0].status in ("failed", "skipped")

    def test_reflection_disabled_by_default(self):
        call_count = [0]

        def tool_fn(name, args):
            call_count[0] += 1
            raise ValueError("boom")

        task = Task(
            id="t_no_reflect",
            goal="test",
            steps=[Step("s1", "Fail", "env_check", {}), Step("s2", "Next", "read_file", {})],
            errors_allowed=1,
            reflection_enabled=False,
        )

        report = TaskExecutor(tool_fn, root=ROOT).run(task)
        assert call_count[0] == 2
        assert task.steps[0].status == "failed"


class TestSmartPlanFunction:
    """smart_plan() convenience function."""

    def test_smart_plan_returns_task(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '[{"id":"s1","description":"Read","tool":"read_file","args":{"path":"x.py"},"depends_on":[],"verify":null}]'
                    }
                }
            ]
        }
        task = smart_plan("refactor x.py", client=mock_client)
        assert task.goal == "refactor x.py"
        assert len(task.steps) == 1

    def test_smart_plan_fallback_quick_plan(self):
        mock_client = MagicMock()
        mock_client.chat.side_effect = OSError("no connection")
        task = smart_plan("fix bug", client=mock_client)
        quick = quick_plan("fix bug")
        assert len(task.steps) == len(quick.steps)
