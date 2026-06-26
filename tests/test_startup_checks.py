"""Tests for core.startup_checks — pre-flight health checks."""

import json


class TestReportHelpers:
    """print_report / critical_failures operate on result lists."""

    def test_critical_failures_filters_blocking(self):
        from core.startup_checks import critical_failures

        results = [
            ("env", False, "missing key"),  # blocking
            ("deps", True, "ok"),
            ("tools.json", False, "bad json"),  # blocking
            ("api", False, "unreachable"),  # not blocking (api category)
        ]
        failures = critical_failures(results)
        assert "missing key" in failures
        assert "bad json" in failures
        assert "unreachable" not in failures  # api is not a blocking category

    def test_critical_failures_empty_on_all_pass(self):
        from core.startup_checks import critical_failures

        results = [("env", True, "ok"), ("deps", True, "ok")]
        assert critical_failures(results) == []

    def test_print_report_outputs(self, capsys):
        from core.startup_checks import print_report

        results = [("env", False, "broken"), ("deps", True, "ok")]
        print_report(results, show_ok=False)
        captured = capsys.readouterr()
        assert "broken" in captured.out
        # ok results hidden when show_ok=False
        assert "deps" not in captured.out

    def test_print_report_shows_ok_when_requested(self, capsys):
        from core.startup_checks import print_report

        results = [("deps", True, "all good")]
        print_report(results, show_ok=True)
        captured = capsys.readouterr()
        assert "all good" in captured.out


class TestCheckToolsConfig:
    """_check_tools_config validates tools.json structure."""

    def test_missing_tools_json(self, tmp_path, monkeypatch):
        from core import startup_checks

        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        startup_checks._results.clear()
        startup_checks._check_tools_config()
        assert len(startup_checks._results) == 1
        cat, ok, msg = startup_checks._results[0]
        assert cat == "tools.json"
        assert ok is False
        assert "not found" in msg

    def test_valid_tools_json(self, tmp_path, monkeypatch):
        from core import startup_checks

        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        cfg = {
            "tools": [
                {"name": "echo", "type": "shell", "command": "echo {text}", "parameters": {"text": {"type": "string"}}}
            ]
        }
        (tmp_path / "tools.json").write_text(json.dumps(cfg), encoding="utf-8")
        startup_checks._results.clear()
        startup_checks._check_tools_config()
        cat, ok, msg = startup_checks._results[0]
        assert ok is True

    def test_format_string_conflict_detected(self, tmp_path, monkeypatch):
        from core import startup_checks

        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        # {undefined} placeholder has no matching parameter
        cfg = {
            "tools": [
                {
                    "name": "bad",
                    "type": "shell",
                    "command": "echo {undefined}",
                    "parameters": {"text": {"type": "string"}},
                }
            ]
        }
        (tmp_path / "tools.json").write_text(json.dumps(cfg), encoding="utf-8")
        startup_checks._results.clear()
        startup_checks._check_tools_config()
        cat, ok, msg = startup_checks._results[0]
        assert ok is False
        assert "undefined" in msg

    def test_invalid_json(self, tmp_path, monkeypatch):
        from core import startup_checks

        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        (tmp_path / "tools.json").write_text("not valid {{{", encoding="utf-8")
        startup_checks._results.clear()
        startup_checks._check_tools_config()
        cat, ok, msg = startup_checks._results[0]
        assert ok is False


class TestCheckModelsConfig:
    """_check_models_config validates models.json."""

    def test_missing_models_json(self, tmp_path, monkeypatch):
        from core import startup_checks

        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        startup_checks._results.clear()
        startup_checks._check_models_config()
        cat, ok, msg = startup_checks._results[0]
        assert ok is False
        assert "not found" in msg

    def test_valid_models_json(self, tmp_path, monkeypatch):
        from core import startup_checks

        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        cfg = {"providers": {"crux": {"base_url": "https://api.example.com", "models": ["m1"]}}, "active": "crux"}
        (tmp_path / "models.json").write_text(json.dumps(cfg), encoding="utf-8")
        startup_checks._results.clear()
        startup_checks._check_models_config()
        cat, ok, msg = startup_checks._results[0]
        assert ok is True

    def test_no_providers_fails(self, tmp_path, monkeypatch):
        from core import startup_checks

        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        (tmp_path / "models.json").write_text(json.dumps({"providers": {}}), encoding="utf-8")
        startup_checks._results.clear()
        startup_checks._check_models_config()
        cat, ok, msg = startup_checks._results[0]
        assert ok is False

    def test_invalid_base_url_fails(self, tmp_path, monkeypatch):
        from core import startup_checks

        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        cfg = {"providers": {"x": {"base_url": "not-a-url", "models": []}}, "active": "x"}
        (tmp_path / "models.json").write_text(json.dumps(cfg), encoding="utf-8")
        startup_checks._results.clear()
        startup_checks._check_models_config()
        cat, ok, msg = startup_checks._results[0]
        assert ok is False
        assert "base_url" in msg


class TestCheckDeps:
    """_check_deps verifies essential packages are importable."""

    def test_runs_without_error(self):
        from core import startup_checks

        startup_checks._results.clear()
        startup_checks._check_deps()
        # Should produce one result entry (ok or fail depending on env)
        assert len(startup_checks._results) == 1


class TestRunAll:
    """run_all() executes the full check suite."""

    def test_returns_results_list(self, monkeypatch, tmp_path):
        from core import startup_checks

        # Point ROOT at empty tmp_path so file-based checks don't hit real config
        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        results = startup_checks.run_all()
        assert isinstance(results, list)
        # Multiple categories should have run
        categories = {r[0] for r in results}
        assert len(categories) >= 4

    def test_clears_previous_results(self, monkeypatch, tmp_path):
        from core import startup_checks

        monkeypatch.setattr(startup_checks, "ROOT", tmp_path)
        startup_checks._results.append(("stale", True, "old"))
        results = startup_checks.run_all()
        assert all(r[0] != "stale" for r in results)
