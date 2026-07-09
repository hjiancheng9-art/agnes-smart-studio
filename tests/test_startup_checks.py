"""Tests for core/startup_checks.py — 启动检查"""

from core.startup_checks import critical_failures, print_report, run_all


class TestStartupChecks:
    def test_run_all_returns_list(self):
        results = run_all()
        assert isinstance(results, list)

    def test_run_all_items_are_tuples(self):
        results = run_all()
        for item in results:
            assert isinstance(item, tuple)
            assert len(item) == 3

    def test_run_all_has_results(self):
        results = run_all()
        assert len(results) > 0

    def test_critical_failures(self):
        results = run_all()
        failures = critical_failures(results)
        assert isinstance(failures, list)

    def test_print_report(self, capsys):
        results = run_all()
        print_report(results)
        capsys.readouterr()
        assert True
