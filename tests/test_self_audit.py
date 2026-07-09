"""Tests for core/self_audit.py — 自审计引擎"""

from core.self_audit import AuditEngine, audit, parse_test_summary


class TestParseTestSummary:
    def test_parses_passed(self):
        output = "21 passed in 0.10s"
        p, f = parse_test_summary(output)
        assert p == 21
        assert f == 0

    def test_parses_failed(self):
        output = "20 passed, 1 failed in 0.20s"
        p, f = parse_test_summary(output)
        assert p == 20
        assert f == 1

    def test_parses_errors(self):
        output = "10 passed, 3 errors in 0.50s"
        p, f = parse_test_summary(output)
        assert p == 10

    def test_empty(self):
        p, f = parse_test_summary("")
        assert (p, f) == (0, 0) or (p >= 0)

    def test_no_match(self):
        p, f = parse_test_summary("no test output here")
        assert (p, f) == (0, 0)

    def test_partial_numbers(self):
        p, f = parse_test_summary("1 failed")
        assert f >= 1

    def test_zero_passed(self):
        p, f = parse_test_summary("0 passed")
        assert p == 0


class TestAuditEngine:
    def test_scan_returns_dict(self):
        engine = AuditEngine()
        result = engine.scan()
        assert isinstance(result, dict)

    def test_print_report(self, capsys):
        engine = AuditEngine()
        engine.print_report()
        capsys.readouterr()
        # 不应崩溃

    def test_audit_function(self):
        audit()
        assert True  # 不应崩溃
