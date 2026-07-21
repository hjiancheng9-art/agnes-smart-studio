"""Feedback Loop — 失败→分析→修正→重试 的自主闭环。

CRUX 的 agent 执行完后直接返回结果，不做事后验证。这个模块补上：
1. 结果质量检查（fake fix detection, success marker validation）
2. 失败分析（分类到可重试 vs 需要上下文 vs 需要模型升级）
3. 自动修正（格式化、lint 修复、import 整理 — 模板化操作）
4. 条件重试（最多 retry_limit 次，每次附加前次失败信息）
5. 最终报告

使用：
    from core.feedback_loop import FeedbackLoop
    loop = FeedbackLoop(client, tools, max_retries=3)
    result = loop.execute_with_feedback(task, agent_name)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import re
from dataclasses import dataclass, field
from enum import Enum


class FailureCategory(Enum):
    RETRY = "retry"  # Auto-fixable, retry with correction
    NEEDS_CONTEXT = "needs_ctx"  # Missing info from user
    NEEDS_HUMAN = "needs_human"  # Beyond auto-fix capability
    FATAL = "fatal"  # Environment/infra issue


@dataclass
class FeedbackResult:
    """Result of a feedback loop execution."""

    success: bool
    final_output: str
    attempts: int
    failures: list[str] = field(default_factory=list)
    corrections_applied: list[str] = field(default_factory=list)
    category: FailureCategory | None = None


class FeedbackLoop:
    """Execute agent tasks with automatic validation, correction, and retry."""

    # Patterns that indicate a fake/uncertain fix
    FAKE_FIX_PATTERNS = [
        r"should\s+(be|work|fix|resolve)",
        r"seems?\s+(to\s+)?(work|fine|ok|fixed)",
        r"probably\s+(fine|works|fixed|ok)",
        r"might\s+(work|help|fix)",
        r"理论上",
        r"应该可以",
        r"看起来",
        r"大概.*好了",
    ]

    # Patterns that indicate a real successful fix
    SUCCESS_PATTERNS = [
        r"(\d+)\s+passed",
        r"(\d+)\s+passed.*(\d+)\s+failed",
        r"All tests passed",
        r"PASS",
        r"OK",
        r"0\s+failed",
        r"build\s+success",
        r"exit\s+code\s+0",
        r"成功",
        r"通过",
    ]

    def __init__(
        self,
        client=None,
        tools=None,
        max_retries: int = 3,
        verify_tests: bool = True,
    ):
        self.client = client
        self.tools = tools
        self.max_retries = max_retries
        self.verify_tests = verify_tests

    def execute_with_feedback(
        self,
        task: str,
        agent_name: str = "",
        system_prompt: str = "",
    ) -> FeedbackResult:
        """Execute a task through an agent with feedback-driven retry.

        The loop:
        1. Run the agent on the task
        2. Validate the result against fake-fix patterns
        3. If invalid: classify failure, apply corrections, retry
        4. Return final result with metadata
        """
        failures: list[str] = []
        corrections: list[str] = []
        current_task = task

        for attempt in range(1, self.max_retries + 1):
            # Run the agent
            output = self._run_agent(current_task, agent_name, system_prompt)

            # Validate result
            is_fake = self._detect_fake_fix(output)
            is_error = self._detect_execution_error(output)

            if not is_fake and not is_error:
                # Success! But run final verification if enabled
                if self.verify_tests and attempt == 1:
                    test_ok = self._run_verification()
                    if not test_ok:
                        failures.append("Verification tests failed")
                        current_task = self._build_retry_task(task, output, "\n".join(failures))
                        continue
                return FeedbackResult(
                    success=True,
                    final_output=output,
                    attempts=attempt,
                    failures=failures,
                    corrections_applied=corrections,
                )

            # Classify failure
            category = self._classify_failure(output, is_fake, is_error)
            failure_msg = f"Attempt {attempt}: fake_fix={is_fake}, error={is_error}, category={category.value}"
            failures.append(failure_msg)

            if category == FailureCategory.FATAL:
                return FeedbackResult(
                    success=False,
                    final_output=output,
                    attempts=attempt,
                    failures=failures,
                    corrections_applied=corrections,
                    category=category,
                )

            if category == FailureCategory.NEEDS_HUMAN:
                return FeedbackResult(
                    success=False,
                    final_output=output,
                    attempts=attempt,
                    failures=failures,
                    corrections_applied=corrections,
                    category=category,
                )

            # Apply corrections for retryable failures
            if category == FailureCategory.RETRY:
                corrected = self._apply_auto_corrections(output)
                if corrected:
                    corrections.extend(corrected)

                # Build enriched retry task with failure context
                current_task = self._build_retry_task(task, output, "\n".join(failures))

        # Exhausted retries
        return FeedbackResult(
            success=False,
            final_output=current_task,
            attempts=self.max_retries,
            failures=failures,
            corrections_applied=corrections,
            category=FailureCategory.NEEDS_HUMAN,
        )

    def _run_agent(self, task: str, agent_name: str, system_prompt: str) -> str:
        """Run the specified agent on the task."""
        if agent_name and self.client:
            from core.agent_loader import spawn_agent_from_spec

            return spawn_agent_from_spec(
                client=self.client,
                task=task,
                agent_name=agent_name,
                tools=self.tools,
            )
        elif self.client:
            from core.agent import SubAgent

            agent = SubAgent(self.client, tools=self.tools)
            return agent.run(task, system_prompt)
        return ""

    def _detect_fake_fix(self, output: str) -> bool:
        """Check if output contains fake-fix markers."""
        return any(re.search(pattern, output, re.IGNORECASE) for pattern in self.FAKE_FIX_PATTERNS)

    def _detect_execution_error(self, output: str) -> bool:
        """Check if output indicates an execution error."""
        error_markers = [
            "Traceback (most recent call last)",
            "Error:",
            "ERROR:",
            "SyntaxError",
            "ImportError",
            "ModuleNotFoundError",
            "[错误]",
            "[FAIL]",
            "[SubAgent error]",
        ]
        return any(marker in output for marker in error_markers)

    def _classify_failure(self, output: str, is_fake: bool, is_error: bool) -> FailureCategory:
        """Classify a failure into a category for decision-making."""
        if "CUDA out of memory" in output or "OOM" in output:
            return FailureCategory.FATAL
        if "permission denied" in output.lower() or "access denied" in output.lower():
            return FailureCategory.FATAL
        if "rate limit" in output.lower() or "429" in output:
            return FailureCategory.RETRY  # Wait and retry
        if "timeout" in output.lower():
            return FailureCategory.RETRY
        if is_fake:
            return FailureCategory.RETRY  # Can auto-correct
        if is_error:
            if "SyntaxError" in output or "ImportError" in output:
                return FailureCategory.RETRY  # Auto-fixable errors
            return FailureCategory.NEEDS_HUMAN
        return FailureCategory.NEEDS_HUMAN

    def _apply_auto_corrections(self, output: str) -> list[str]:
        """Apply auto-fix corrections. Returns list of what was fixed."""
        corrections: list[str] = []

        # Run formatter if output suggests formatting issues
        if "format" in output.lower() or "style" in output.lower():
            try:
                import subprocess

                r = subprocess.run(
                    ["python", "-m", "ruff", "check", "--fix", "."],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if r.returncode == 0:
                    corrections.append("ruff check --fix applied")
            except Exception:
                logger.debug("Exception in feedback_loop", exc_info=True)

        # Run self_heal for known issues
        if "[错误]" in output or "Error:" in output:
            try:
                from core.self_heal import SelfHealer

                healer = SelfHealer()
                healer.scan_all()
                if healer.findings:
                    auto_fixable = [f for f in healer.findings if f.fixable]
                    if auto_fixable:
                        healer.apply_findings(auto_fixable)
                        corrections.append(f"self_heal: {len(auto_fixable)} issues auto-fixed")
            except Exception:
                logger.debug("Exception in feedback_loop", exc_info=True)

        return corrections

    def _run_verification(self) -> bool:
        """Run smoke tests to verify changes didn't break anything."""
        try:
            import subprocess
            import sys

            r = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_smoke.py", "-q"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return r.returncode == 0
        except Exception:
            return False  # Can't verify, but don't block for it

    def _build_retry_task(self, original_task: str, last_output: str, failures: str) -> str:
        """Build an enriched task with previous failure context."""
        return (
            f"PREVIOUS ATTEMPT FAILED. You must fix the issues below.\n\n"
            f"Original task: {original_task}\n\n"
            f"Last output: {last_output[:500]}\n\n"
            f"Failures detected: {failures}\n\n"
            f"Instructions:\n"
            f"1. Identify what went wrong from the last output\n"
            f"2. Fix the root cause, not the symptom\n"
            f"3. Verify with the project's test command\n"
            f"4. If you say 'should work' or 'seems fine', you have FAILED"
        )


# ═══════════════════════════════════════════════════════════
# Quick self-test
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    loop = FeedbackLoop(max_retries=3)

    # Test fake fix detection
    assert loop._detect_fake_fix("This should be working now")
    assert loop._detect_fake_fix("bug修复完成，应该可以了")
    assert not loop._detect_fake_fix("pytest 5 passed 0 failed, all tests green")
    assert not loop._detect_fake_fix("build success, deployed to staging")
    print("Fake fix detection: OK")

    # Test error detection
    assert loop._detect_execution_error("Traceback (most recent call last): ...")
    assert loop._detect_execution_error("[错误] 文件不存在")
    assert not loop._detect_execution_error("All tests passed")
    print("Error detection: OK")

    # Test failure classification
    assert loop._classify_failure("should work", True, False) == FailureCategory.RETRY
    assert loop._classify_failure("CUDA out of memory", False, True) == FailureCategory.FATAL
    assert loop._classify_failure("SyntaxError: invalid syntax", False, True) == FailureCategory.RETRY
    print("Failure classification: OK")

    # Test retry task building
    task = loop._build_retry_task("fix bug", "should work", "fake_fix=True")
    assert "PREVIOUS ATTEMPT FAILED" in task
    assert "should work" in task
    print("Retry task builder: OK")

    print("\nAll feedback loop tests passed.")
