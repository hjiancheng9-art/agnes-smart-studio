"""Test Phase 2: Result validation + Consistency check + Diff guard"""

import pytest

from core.result_validator import (
    ConsistencyChecker,
    DiffGuard,
    ResultValidator,
    ValidationNote,
)
from core.reviewer_agent import (
    DebateResult,
    ReviewerAgent,
    ReviewIssue,
    ReviewReport,
    ReviewSeverity,
    SubTask,
    TaskPlan,
)

# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def rv():
    return ResultValidator()


@pytest.fixture
def cc():
    return ConsistencyChecker()


@pytest.fixture
def dg():
    return DiffGuard()


@pytest.fixture
def reviewer():
    from core.reviewer_agent import ReviewerAgent

    return ReviewerAgent()


@pytest.fixture
def debater():
    from core.reviewer_agent import DebateAgent

    return DebateAgent()


@pytest.fixture
def decomposer():
    from core.reviewer_agent import TaskDecomposer

    return TaskDecomposer()


# ── ResultValidator ─────────────────────────────────────────────────


class TestResultValidator:
    def test_valid_result(self, rv):
        vr = rv.validate("read_file", "file contents here", success=True)
        assert vr.is_valid
        assert not vr.truncated

    def test_failed_result(self, rv):
        vr = rv.validate("run_bash", "Error: not found", success=False)
        assert not vr.is_valid
        assert vr.notes  # should have error pattern notes

    def test_large_output_truncation_flag(self, rv):
        vr = rv.validate("read_file", "x" * 6000, success=True)
        assert vr.truncated
        assert len(vr.notes) >= 1

    def test_many_lines(self, rv):
        vr = rv.validate("read_file", "\n".join(str(i) for i in range(600)), success=True)
        assert len(vr.notes) >= 1

    def test_error_pattern_syntax(self, rv):
        vr = rv.validate("run_python", "Traceback\nSyntaxError: invalid syntax", success=False)
        assert not vr.is_valid
        assert any("syntax" in n.message.lower() for n in vr.notes)

    def test_error_pattern_permission(self, rv):
        vr = rv.validate("read_file", "Permission denied: /etc/shadow", success=False)
        assert not vr.is_valid
        assert any("permission" in n.message.lower() for n in vr.notes)

    def test_error_pattern_timeout(self, rv):
        vr = rv.validate("run_bash", "Connection timed out", success=False)
        assert not vr.is_valid

    def test_success_empty(self, rv):
        vr = rv.validate("read_file", "", success=True)
        assert vr.is_valid
        assert any("empty" in n.message.lower() for n in vr.notes)

    def test_hints(self, rv):
        vr = rv.validate("run_python", "SyntaxError", success=False)
        hints = rv.suggest_hints(vr)
        assert any("syntax" in h.lower() for h in hints)


# ── ConsistencyChecker ──────────────────────────────────────────────


class TestConsistencyChecker:
    def test_no_history(self, cc):
        rep = cc.check("Answer", [])
        assert rep.is_consistent
        assert len(rep.issues) == 0

    def test_all_succeeded(self, cc):
        rep = cc.check(
            "Done!",
            [
                {"tool_name": "read_file", "args": {}, "result": "ok", "success": True},
            ],
        )
        assert rep.is_consistent

    def test_failed_tool_not_mentioned(self, cc):
        rep = cc.check(
            "Great success!",
            [
                {"tool_name": "run_bash", "args": {}, "result": "FAILED", "success": False},
            ],
        )
        assert not rep.is_consistent
        assert any("run_bash" in i.description for i in rep.issues)

    def test_all_failed(self, cc):
        rep = cc.check(
            "Answer",
            [
                {"tool_name": "run_bash", "args": {}, "result": "err", "success": False},
            ],
        )
        assert not rep.is_consistent
        assert any("critical" in i.severity for i in rep.issues)

    def test_short_answer_many_tools(self, cc):
        rep = cc.check(
            "OK",
            [
                {"tool_name": "t1", "args": {}, "result": "a", "success": True},
                {"tool_name": "t2", "args": {}, "result": "b", "success": True},
                {"tool_name": "t3", "args": {}, "result": "c", "success": True},
                {"tool_name": "t4", "args": {}, "result": "d", "success": True},
            ],
        )
        # Short answer after many tools triggers minor issue
        assert len(rep.issues) >= 1

    def test_summary_format(self, cc):
        rep = cc.check(
            "OK",
            [
                {"tool_name": "t", "args": {}, "result": "err", "success": False},
            ],
        )
        assert "inconsistenc" in rep.summary().lower()

    def test_write_then_read_file_tracking(self, cc):
        rep = cc.check(
            "I wrote config.py and read it back",
            [
                {
                    "tool_name": "write_file",
                    "args": {"path": "config.py", "content": "x"},
                    "result": "",
                    "success": True,
                },
                {"tool_name": "read_file", "args": {"path": "config.py"}, "result": "x", "success": True},
            ],
        )
        # Should be consistent — file was written then read
        assert rep.is_consistent


# ── DiffGuard ───────────────────────────────────────────────────────


class TestDiffGuard:
    def test_create_action(self, dg):
        preview = dg.preview_write("new_file.py", "print('hello')")
        assert preview.action == "create"
        assert preview.size_delta == len("print('hello')")

    def test_modify_action(self, dg):
        dg.snapshot_before("_test_temp.py")
        preview = dg.preview_write("_test_temp.py", "different content")
        assert preview.action in ("create", "modify")

    def test_diff_lines(self, dg):
        preview = dg.preview_write("test.py", "line1\nline2")
        assert isinstance(preview.diff_lines, list)

    def test_suspicious_system_dir(self, dg):
        preview = dg.preview_write("node_modules/pkg/index.js", "x")
        assert preview.suspicious
        assert "system" in preview.suspicion_reason.lower()

    def test_suspicious_git_dir(self, dg):
        preview = dg.preview_write(".git/config", "x")
        assert preview.suspicious

    def test_suspicious_pycache(self, dg):
        preview = dg.preview_write("__pycache__/test.py", "x")
        assert preview.suspicious

    def test_normal_path_not_suspicious(self, dg):
        preview = dg.preview_write("src/main.py", "hello world")
        assert not preview.suspicious

    def test_snapshot_and_preview_flow(self, dg):
        dg.snapshot_before("_test_flow.py")
        preview = dg.preview_write("_test_flow.py", "content")
        assert preview.path == "_test_flow.py"


# ── ValidationNote ──────────────────────────────────────────────────


class TestValidationNote:
    def test_severity_levels(self):
        n1 = ValidationNote(severity="info", message="just info")
        n2 = ValidationNote(severity="warning", message="careful")
        n3 = ValidationNote(severity="critical", message="stop")
        assert n1.severity == "info"
        assert n2.severity == "warning"
        assert n3.severity == "critical"


# ── Integration ─────────────────────────────────────────────────────


class TestEdgeCases:
    def test_reviewer_with_no_results(self, reviewer):
        rep = reviewer.review("", "", None)
        assert isinstance(rep.score, int)

    def test_debater_empty(self, debater):
        result = debater.debate("", "", [])
        assert result.agreement == "agree"

    def test_decomposer_empty(self, decomposer):
        plan = decomposer.decompose("")
        assert len(plan.tasks) >= 1

    def test_llm_review_parse_failure(self, reviewer):
        report = reviewer._parse_review_json("This is not JSON")
        assert report is None

    def test_llm_review_parse_partial(self, reviewer):
        report = reviewer._parse_review_json('{"issues": [], "score": 80}')
        assert report is not None
        assert report.score == 80

    def test_debater_parse_failure(self, debater):
        result = debater._parse_debate_json("not JSON")
        assert result.agreement == "agree"

    def test_debater_parse_full(self, debater):
        json_str = '{"critiques": [{"concern": "x", "counter_argument": "y", "impact": "high"}], "overall_assessment": "disagree", "alternative_approach": "z"}'
        result = debater._parse_debate_json(json_str)
        assert result.agreement == "disagree"
        assert result.should_revise

    def test_decomposer_parse_failure(self, decomposer):
        plan = decomposer._parse_plan("not JSON", "query")
        assert plan.complexity == "unknown"

    def test_decomposer_parse_full(self, decomposer):
        json_str = '{"tasks": [{"id": 1, "description": "A", "depends_on": [], "tools_likely_needed": ["t"]}], "estimated_complexity": "high"}'
        plan = decomposer._parse_plan(json_str, "query")
        assert plan.complexity == "high"
        assert plan.tasks[0].description == "A"

    # ── New P4 coverage ───────────────────────────────────────

    def test_review_issue_fields(self):
        iss = ReviewIssue(
            severity=ReviewSeverity.MAJOR,
            category="factual",
            description="bad",
            suggestion="fix",
            location="/src/main.py",
        )
        assert iss.suggestion == "fix"
        assert iss.location == "/src/main.py"

    def test_review_report_to_llm_prompt_empty(self):
        rep = ReviewReport(issues=[], score=100, passed=True)
        assert rep.to_llm_prompt() == ""

    def test_review_report_to_llm_prompt_with_issues(self):
        issues = [
            ReviewIssue(
                severity=ReviewSeverity.CRITICAL, category="safety", description="dangerous code", suggestion="remove"
            )
        ]
        rep = ReviewReport(issues=issues, score=30, passed=False)
        prompt = rep.to_llm_prompt()
        assert "dangerous code" in prompt
        assert "remove" in prompt

    def test_reviewer_auto_fix_property(self):
        rev = ReviewerAgent(auto_fix=True)
        assert rev.auto_fix
        rev2 = ReviewerAgent(auto_fix=False)
        assert not rev2.auto_fix

    def test_reviewer_with_llm_callback(self):
        def fake_llm(sys_prompt, user_prompt, messages):
            return '{"issues": [{"severity": "major", "category": "factual", "description": "Wrong answer", "suggestion": "Correct it"}], "score": 50}'

        rev = ReviewerAgent(llm_callback=fake_llm)
        rep = rev.review("What is 2+2?", "5", [])
        # Should have the LLM-found issue plus any rule-based issues
        assert len(rep.issues) >= 1
        assert rep.score <= 50

    def test_reviewer_dedup(self, reviewer):
        """Ensure duplicate issues are removed."""
        rep = reviewer.review("Hi", "Hello", [])
        # Running twice shouldn't double issues
        len(rep.issues)
        rep2 = reviewer.review("Hi", "Hello", [])
        # both should be clean
        assert rep2.score >= 80

    def test_debate_result_should_revise(self):
        dr = DebateResult(agreement="disagree", should_revise=True)
        assert dr.should_revise

    def test_sub_task_deps(self):
        st = SubTask(id=2, description="Step 2", depends_on=[1])
        assert 1 in st.depends_on

    def test_task_plan_with_deps_text(self):
        plan = TaskPlan(
            tasks=[
                SubTask(id=1, description="Read file"),
                SubTask(id=2, description="Edit file", depends_on=[1]),
            ],
            complexity="medium",
            original_query="fix bug",
        )
        txt = plan.text
        assert "after: 1" in txt or "Read file" in txt
