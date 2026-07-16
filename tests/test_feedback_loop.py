"""Tests for core/feedback_loop.py — feedback-driven retry loop."""

from core.feedback_loop import FailureCategory, FeedbackLoop, FeedbackResult


class TestFakeFixDetection:
    def setup_method(self):
        self.loop = FeedbackLoop()

    def test_fake_english_detected(self):
        assert self.loop._detect_fake_fix("This should be working now")
        assert self.loop._detect_fake_fix("The fix seems to work")
        assert self.loop._detect_fake_fix("It probably fixed the issue")
        assert self.loop._detect_fake_fix("The bug might work now")

    def test_fake_chinese_detected(self):
        assert self.loop._detect_fake_fix("修复完成，应该可以了")
        assert self.loop._detect_fake_fix("看起来没问题了")
        assert self.loop._detect_fake_fix("理论上应该修复了")
        assert self.loop._detect_fake_fix("大概已经好了")

    def test_real_success_not_detected(self):
        assert not self.loop._detect_fake_fix("pytest 5 passed 0 failed, all tests green")
        assert not self.loop._detect_fake_fix("build success, deployed to staging")
        assert not self.loop._detect_fake_fix("exit code 0, lint clean")
        assert not self.loop._detect_fake_fix("All tests passed, coverage 85%")

    def test_empty_output(self):
        assert not self.loop._detect_fake_fix("")
        assert not self.loop._detect_fake_fix("OK")


class TestErrorDetection:
    def setup_method(self):
        self.loop = FeedbackLoop()

    def test_traceback_detected(self):
        assert self.loop._detect_execution_error(
            "Traceback (most recent call last):\n  File 'x.py', line 1\nValueError: bad"
        )

    def test_syntax_error(self):
        assert self.loop._detect_execution_error("SyntaxError: invalid syntax at line 42")

    def test_crux_error_tags(self):
        assert self.loop._detect_execution_error("[错误] 文件不存在")
        assert self.loop._detect_execution_error("[FAIL] Test failed")
        assert self.loop._detect_execution_error("[SubAgent error] connection refused")

    def test_clean_output(self):
        assert not self.loop._detect_execution_error("All tests passed")
        assert not self.loop._detect_execution_error("Task completed successfully")


class TestFailureClassification:
    def setup_method(self):
        self.loop = FeedbackLoop()

    def test_fake_fix_is_retry(self):
        assert self.loop._classify_failure("should work", True, False) == FailureCategory.RETRY

    def test_syntax_error_is_retry(self):
        assert self.loop._classify_failure("SyntaxError: invalid syntax", False, True) == FailureCategory.RETRY

    def test_oem_is_fatal(self):
        assert self.loop._classify_failure("CUDA out of memory", False, True) == FailureCategory.FATAL

    def test_permission_denied_is_fatal(self):
        assert self.loop._classify_failure("permission denied: /etc/config", False, True) == FailureCategory.FATAL

    def test_rate_limit_is_retry(self):
        assert self.loop._classify_failure("rate limit exceeded, try again", False, True) == FailureCategory.RETRY

    def test_unknown_error_needs_human(self):
        assert self.loop._classify_failure("something went wrong somewhere", False, True) == FailureCategory.NEEDS_HUMAN


class TestFeedbackLoopBasics:
    def test_initialization(self):
        loop = FeedbackLoop(max_retries=3)
        assert loop.max_retries == 3
        assert loop.verify_tests is True

    def test_custom_retry_limit(self):
        loop = FeedbackLoop(max_retries=5, verify_tests=False)
        assert loop.max_retries == 5
        assert not loop.verify_tests

    def test_retry_task_builder(self):
        loop = FeedbackLoop()
        task = loop._build_retry_task("fix bug", "should work", "fake_fix=True")
        assert "PREVIOUS ATTEMPT FAILED" in task
        assert "fix bug" in task
        assert "should work" in task
        assert "fake_fix=True" in task

    def test_feedback_result_defaults(self):
        result = FeedbackResult(success=True, final_output="done", attempts=1)
        assert result.success
        assert result.final_output == "done"
        assert result.failures == []
        assert result.corrections_applied == []

    def test_feedback_result_with_failures(self):
        result = FeedbackResult(
            success=False,
            final_output="error",
            attempts=3,
            failures=["fake fix", "test fail"],
            corrections_applied=["ruff fix"],
            category=FailureCategory.NEEDS_HUMAN,
        )
        assert not result.success
        assert result.attempts == 3
        assert len(result.failures) == 2
        assert len(result.corrections_applied) == 1
        assert result.category == FailureCategory.NEEDS_HUMAN
