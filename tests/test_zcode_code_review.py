"""
ZCode TDD: core/code_review.py tests.
Tests CodeReviewer, SecurityReviewer, ReviewIssue, ReviewReport, and main entry points.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 1. CodeReviewer instantiation
# ---------------------------------------------------------------------------

class TestCodeReviewerInstantiation:
    def test_default_constructor(self):
        from core.code_review import CodeReviewer
        reviewer = CodeReviewer()
        assert reviewer is not None
        assert len(reviewer.rules) >= 2

    def test_custom_rules(self):
        from core.code_review import CodeReviewer, TextPatternChecker
        reviewer = CodeReviewer(rules=[TextPatternChecker()])
        assert len(reviewer.rules) == 1

    def test_security_reviewer_constructor(self):
        from core.code_review import SecurityReviewer
        reviewer = SecurityReviewer()
        assert reviewer is not None
        assert len(reviewer.rules) == 3  # PythonAST + TextPattern + Security


# ---------------------------------------------------------------------------
# 2. ReviewIssue dataclass
# ---------------------------------------------------------------------------

class TestReviewIssue:
    def test_review_issue_creation(self):
        from core.code_review import ReviewIssue
        issue = ReviewIssue(
            file="test.py",
            line=10,
            severity="error",
            category="security",
            message="Hardcoded password",
            suggestion="Use env vars",
            rule="hardcoded-password",
        )
        assert issue.file == "test.py"
        assert issue.line == 10
        assert issue.severity == "error"
        assert issue.category == "security"
        assert issue.message == "Hardcoded password"
        assert issue.suggestion == "Use env vars"
        assert issue.rule == "hardcoded-password"

    def test_review_issue_defaults(self):
        from core.code_review import ReviewIssue
        issue = ReviewIssue(
            file="test.py",
            line=1,
            severity="info",
            category="style",
            message="ok",
        )
        assert issue.suggestion == ""
        assert issue.rule == ""


# ---------------------------------------------------------------------------
# 3. ReviewReport dataclass
# ---------------------------------------------------------------------------

class TestReviewReport:
    def test_empty_report(self):
        from core.code_review import ReviewReport
        report = ReviewReport()
        assert report.issues == []
        assert report.stats == {}

    def test_report_to_dict(self):
        from core.code_review import ReviewIssue, ReviewReport
        issue = ReviewIssue(
            file="a.py", line=1, severity="error",
            category="security", message="bad",
        )
        report = ReviewReport(issues=[issue], stats={"files": 1})
        d = report.to_dict()
        assert d["stats"] == {"files": 1}
        assert len(d["issues"]) == 1
        assert d["issues"][0]["file"] == "a.py"

    def test_report_summary(self):
        from core.code_review import ReviewIssue, ReviewReport
        issue = ReviewIssue(
            file="a.py", line=1, severity="error",
            category="security", message="bad",
        )
        report = ReviewReport(
            issues=[issue],
            stats={"files": 1, "lines": 10, "total_issues": 1,
                   "errors": 1, "warnings": 0, "info": 0},
        )
        s = report.summary()
        assert "Code Review Report" in s
        assert "Files: 1" in s

    def test_summary_truncates_at_20(self):
        from core.code_review import ReviewIssue, ReviewReport
        issues = [
            ReviewIssue(file=f"f{i}.py", line=i, severity="info",
                        category="style", message=f"msg{i}")
            for i in range(25)
        ]
        report = ReviewReport(issues=issues, stats={"total_issues": 25})
        s = report.summary()
        assert "and 5 more" in s


# ---------------------------------------------------------------------------
# 4. run_review / run_security_review importable
# ---------------------------------------------------------------------------

class TestRunReviewImportable:
    def test_run_review_importable(self):
        from core.code_review import run_review
        assert callable(run_review)

    def test_run_security_review_importable(self):
        from core.code_review import run_security_review
        assert callable(run_security_review)

    def test_run_review_with_files(self):
        from core.code_review import run_review
        result = run_review(files=["nonexistent.py"])
        assert result["success"] is True
        assert "report" in result

    def test_run_review_security_mode(self):
        from core.code_review import run_review
        result = run_review(files=["nonexistent.py"], mode="security")
        assert result["success"] is True
        assert result["mode"] == "security"

    def test_run_security_review_with_files(self):
        from core.code_review import run_security_review
        result = run_security_review(files=["nonexistent.py"])
        assert result["success"] is True


# ---------------------------------------------------------------------------
# 5. _exec_code_review / _exec_security_review importable
# ---------------------------------------------------------------------------

class TestExecFunctionsImportable:
    def test_exec_code_review_importable(self):
        from core.code_review import _exec_code_review
        assert callable(_exec_code_review)

    def test_exec_security_review_importable(self):
        from core.code_review import _exec_security_review
        assert callable(_exec_security_review)

    def test_exec_code_review_returns_json_string(self):
        import json
        from core.code_review import _exec_code_review
        result = _exec_code_review(files=["nonexistent.py"])
        assert isinstance(result, str)
        d = json.loads(result)
        assert d["success"] is True

    def test_exec_security_review_returns_json_string(self):
        import json
        from core.code_review import _exec_security_review
        result = _exec_security_review(files=["nonexistent.py"])
        assert isinstance(result, str)
        d = json.loads(result)
        assert d["success"] is True


# ---------------------------------------------------------------------------
# 6. Rule checkers
# ---------------------------------------------------------------------------

class TestRuleCheckers:
    def test_python_ast_checker_syntax_error(self):
        from core.code_review import PythonASTChecker
        checker = PythonASTChecker()
        issues = checker.check_file("bad.py", "def broken(:")
        assert len(issues) >= 1
        assert issues[0].severity == "error"

    def test_python_ast_checker_clean_file(self):
        from core.code_review import PythonASTChecker
        checker = PythonASTChecker()
        issues = checker.check_file("clean.py", "x = 1\ny = 2\n")
        assert len(issues) == 0

    def test_text_pattern_checker_hardcoded_password(self):
        from core.code_review import TextPatternChecker
        checker = TextPatternChecker()
        issues = checker.check_file("cfg.py", 'password = "secret123"')
        assert len(issues) >= 1
        assert any(i.rule == "hardcoded-password" for i in issues)

    def test_text_pattern_checker_todo_comment(self):
        from core.code_review import TextPatternChecker
        checker = TextPatternChecker()
        issues = checker.check_file("todo.py", "# TODO: fix this later")
        assert any(i.rule == "todo-comment" for i in issues)

    def test_security_rule_checker_unsafe_yaml(self):
        from core.code_review import SecurityRuleChecker
        checker = SecurityRuleChecker()
        issues = checker.check_file("load.py", "data = yaml.load(f)")
        assert any(i.rule == "unsafe-yaml" for i in issues)

    def test_security_rule_checker_debug_true(self):
        from core.code_review import SecurityRuleChecker
        checker = SecurityRuleChecker()
        issues = checker.check_file("settings.py", "DEBUG = True")
        assert any(i.rule == "debug-enabled" for i in issues)


# ---------------------------------------------------------------------------
# 7. CodeReviewer review_files with real content
# ---------------------------------------------------------------------------

class TestCodeReviewerReviewFiles:
    def test_review_files_empty_list(self):
        from core.code_review import CodeReviewer
        reviewer = CodeReviewer()
        report = reviewer.review_files([])
        assert report.stats["files"] == 0
        assert report.stats["total_issues"] == 0

    def test_review_files_with_issues(self):
        from core.code_review import CodeReviewer
        reviewer = CodeReviewer()
        report = reviewer.review_files([__file__])
        assert report.stats["files"] >= 1
        assert isinstance(report.stats["total_issues"], int)
        assert isinstance(report.stats["errors"], int)
        assert isinstance(report.stats["warnings"], int)
        assert isinstance(report.stats["info"], int)

    def test_code_review_tool_defs_structure(self):
        from core.code_review import CODE_REVIEW_TOOL_DEFS
        assert isinstance(CODE_REVIEW_TOOL_DEFS, list)
        names = {td["function"]["name"] for td in CODE_REVIEW_TOOL_DEFS}
        assert names == {"code_review", "security_review"}

    def test_code_review_executor_map(self):
        from core.code_review import CODE_REVIEW_EXECUTOR_MAP
        assert "code_review" in CODE_REVIEW_EXECUTOR_MAP
        assert "security_review" in CODE_REVIEW_EXECUTOR_MAP
        assert callable(CODE_REVIEW_EXECUTOR_MAP["code_review"])
        assert callable(CODE_REVIEW_EXECUTOR_MAP["security_review"])
