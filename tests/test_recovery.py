"""Tests for core.recovery — automated failure recovery playbooks."""

import json


class TestRecoveryEngineInit:
    """RecoveryEngine construction and dispatch."""

    def test_default_root(self):
        from core.recovery import ROOT, RecoveryEngine

        eng = RecoveryEngine()
        assert eng.root == ROOT

    def test_custom_root(self, tmp_path):
        from core.recovery import RecoveryEngine

        eng = RecoveryEngine(root=tmp_path)
        assert eng.root == tmp_path

    def test_log_starts_empty(self):
        from core.recovery import RecoveryEngine

        eng = RecoveryEngine()
        assert eng.log == []


class TestUnknownScenario:
    """run() with an unrecognized scenario fails cleanly."""

    def test_unknown_scenario_returns_failure(self):
        from core.recovery import RecoveryEngine

        eng = RecoveryEngine()
        result = eng.run("nonexistent_scenario")
        assert result["success"] is False
        assert "Unknown scenario" in result["message"]

    def test_unknown_scenario_not_logged(self):
        # The unknown-scenario early-return path does not append to the log
        from core.recovery import RecoveryEngine

        eng = RecoveryEngine()
        eng.run("nonexistent_scenario")
        assert eng.log == []


class TestModelError:
    """_model_error playbook maps error strings to hints."""

    def test_503_hint(self):
        from core.recovery import recover

        result = recover("model_error", error_msg="HTTP 503 service unavailable")
        assert result["success"] is True
        assert "unavailable" in result["message"].lower() or "switching" in result["message"].lower()

    def test_401_hint(self):
        from core.recovery import recover

        result = recover("model_error", error_msg="401 unauthorized")
        assert result["success"] is True
        assert "auth" in result["message"].lower()

    def test_timeout_hint(self):
        from core.recovery import recover

        result = recover("model_error", error_msg="request timeout after 30s")
        assert result["success"] is True
        assert "timeout" in result["message"].lower()

    def test_rate_limit_hint(self):
        from core.recovery import recover

        result = recover("model_error", error_msg="rate limit exceeded")
        assert result["success"] is True
        assert "rate" in result["message"].lower()

    def test_unknown_error_no_hints(self):
        from core.recovery import recover

        result = recover("model_error", error_msg="zzz mysterious failure")
        assert result["success"] is False
        assert "Unknown" in result["message"]

    def test_empty_error_message(self):
        from core.recovery import recover

        result = recover("model_error", error_msg="")
        assert result["success"] is False


class TestDiskLow:
    """_disk_low playbook cleans up output files."""

    def test_disk_low_reports_cleaned_items(self, tmp_path):
        from core.recovery import RecoveryEngine

        eng = RecoveryEngine(root=tmp_path)
        result = eng.run("disk_low")
        assert result["success"] is True
        assert "Cleaned" in result["message"]

    def test_disk_low_cleans_browser_sessions(self, tmp_path):
        from core.recovery import RecoveryEngine

        bs = tmp_path / "output" / "browser_sessions"
        bs.mkdir(parents=True)
        (bs / "session.json").write_text("{}", encoding="utf-8")
        eng = RecoveryEngine(root=tmp_path)
        result = eng.run("disk_low")
        assert result["success"] is True
        assert not bs.exists()

    def test_disk_low_removes_old_backups(self, tmp_path):
        import time

        from core.recovery import RecoveryEngine

        bak = tmp_path / "config.bak"
        bak.write_text("backup", encoding="utf-8")
        old_ts = time.time() - 86400 * 30  # 30 days ago
        import os

        os.utime(bak, (old_ts, old_ts))
        eng = RecoveryEngine(root=tmp_path)
        result = eng.run("disk_low", threshold_mb=0)
        assert result["success"] is True


class TestConfigCorrupt:
    """_config_corrupt playbook restores from backup."""

    def test_no_backup_returns_failure(self, tmp_path):
        from core.recovery import RecoveryEngine

        eng = RecoveryEngine(root=tmp_path)
        result = eng.run("config_corrupt", file="models.json")
        assert result["success"] is False
        assert "No backup" in result["message"]

    def test_restore_from_backup(self, tmp_path):
        from core.recovery import RecoveryEngine

        target = tmp_path / "config.json"
        backup = tmp_path / "config.json.bak"
        backup.write_text(json.dumps({"valid": True}), encoding="utf-8")
        eng = RecoveryEngine(root=tmp_path)
        result = eng.run("config_corrupt", file="config.json")
        assert result["success"] is True
        assert "Restored" in result["message"]
        assert target.exists()
        assert json.loads(target.read_text(encoding="utf-8")) == {"valid": True}

    def test_restore_invalid_backup_fails(self, tmp_path):
        from core.recovery import RecoveryEngine

        backup = tmp_path / "config.json.bak"
        backup.write_text("not valid json {{{", encoding="utf-8")
        eng = RecoveryEngine(root=tmp_path)
        result = eng.run("config_corrupt", file="config.json")
        assert result["success"] is False


class TestRecoverFunction:
    """Module-level recover() convenience wrapper."""

    def test_recover_creates_fresh_engine(self):
        from core.recovery import recover

        # recover() should not require pre-existing engine; returns dict
        result = recover("model_error", error_msg="503 error")
        assert isinstance(result, dict)
        assert "success" in result

    def test_each_call_independent(self):
        from core.recovery import recover

        r1 = recover("model_error", error_msg="401")
        r2 = recover("model_error", error_msg="unknown zzz")
        # The two calls must not share log state (each creates new engine)
        assert r1["success"] is True
        assert r2["success"] is False


class TestRunLogAppends:
    """Every successful run() appends to the engine log."""

    def test_log_appends_on_success(self):
        from core.recovery import RecoveryEngine

        eng = RecoveryEngine()
        eng.run("model_error", error_msg="503")
        assert len(eng.log) == 1
        assert eng.log[0]["scenario"] == "model_error"
        assert eng.log[0]["success"] is True

    def test_multiple_runs_accumulate(self):
        from core.recovery import RecoveryEngine

        eng = RecoveryEngine()
        eng.run("model_error", error_msg="503")
        eng.run("model_error", error_msg="401")
        assert len(eng.log) == 2
