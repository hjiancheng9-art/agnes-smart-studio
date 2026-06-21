"""Tests for core.monitor — runtime health monitoring and data hygiene."""



class TestHealthMonitorInit:
    """HealthMonitor construction."""

    def test_default_deques(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        assert len(hm.api_calls) == 0
        assert len(hm.tool_calls) == 0
        assert hm.alerts == []

    def test_deque_maxlen(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        assert hm.api_calls.maxlen == 100
        assert hm.tool_calls.maxlen == 100


class TestRecordApiCall:
    """record_api_call stores metrics and triggers health check."""

    def test_records_successful_call(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        hm.record_api_call("agnes-2.0-flash", latency=0.5)
        assert len(hm.api_calls) == 1
        entry = hm.api_calls[0]
        assert entry["model"] == "agnes-2.0-flash"
        assert entry["latency"] == 0.5
        assert entry["error"] is None

    def test_records_error_call(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        hm.record_api_call("deepseek-v4-pro", latency=1.0, error="timeout")
        assert hm.api_calls[0]["error"] == "timeout"

    def test_deque_evicts_old_entries(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        for i in range(105):
            hm.record_api_call("m", latency=float(i))
        assert len(hm.api_calls) == 100  # maxlen enforced


class TestRecordToolCall:
    """record_tool_call tracks tool execution success/failure."""

    def test_records_success(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        hm.record_tool_call("generate_image", success=True, latency=2.0)
        assert hm.tool_calls[0]["success"] is True

    def test_records_failure(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        hm.record_tool_call("shell_exec", success=False, latency=0.1, error="denied")
        assert hm.tool_calls[0]["success"] is False
        assert hm.tool_calls[0]["error"] == "denied"


class TestAlertsTrigger:
    """Alerts fire when error rate exceeds 50% threshold."""

    def test_no_alert_below_threshold(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        # 10 calls, 2 errors = 20% rate, below 50% threshold
        for _i in range(8):
            hm.record_api_call("m", latency=0.1)
        for _i in range(2):
            hm.record_api_call("m", latency=0.1, error="x")
        alerts = [a for a in hm.alerts if a["kind"] == "api_error_rate"]
        assert len(alerts) == 0

    def test_alert_at_high_error_rate(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        # 10 calls, 6 errors = 60% rate, exceeds 50%
        for _i in range(4):
            hm.record_api_call("m", latency=0.1)
        for _i in range(6):
            hm.record_api_call("m", latency=0.1, error="x")
        api_alerts = [a for a in hm.alerts if a["kind"] == "api_error_rate"]
        assert len(api_alerts) >= 1

    def test_tool_alert_at_high_failure_rate(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        # 10 calls, 6 failures
        for _i in range(4):
            hm.record_tool_call("t", success=True, latency=0.1)
        for _i in range(6):
            hm.record_tool_call("t", success=False, latency=0.1, error="boom")
        tool_alerts = [a for a in hm.alerts if a["kind"] == "tool_error_rate"]
        assert len(tool_alerts) >= 1


class TestHealthReport:
    """health_report aggregates recent metrics."""

    def test_empty_report(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        report = hm.health_report()
        assert report["api_calls_recent"] == 0
        assert report["tool_calls_recent"] == 0
        assert report["api_error_rate"] == 0
        assert report["tool_error_rate"] == 0
        assert report["alerts"] == []

    def test_report_reflects_calls(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        hm.record_api_call("m", latency=0.5)
        hm.record_tool_call("t", success=True, latency=0.2)
        report = hm.health_report()
        assert report["api_calls_recent"] == 1
        assert report["tool_calls_recent"] == 1


class TestIsHealthy:
    """is_healthy() returns True when error rates are low."""

    def test_healthy_when_clean(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        for _i in range(5):
            hm.record_api_call("m", latency=0.1)
            hm.record_tool_call("t", success=True, latency=0.1)
        assert hm.is_healthy() is True

    def test_unhealthy_when_many_errors(self):
        from core.monitor import HealthMonitor
        hm = HealthMonitor()
        for _i in range(8):
            hm.record_api_call("m", latency=0.1, error="fail")
        assert hm.is_healthy() is False


class TestGetMonitorSingleton:
    """get_monitor() returns a shared singleton."""

    def test_returns_same_instance(self):
        from core.monitor import get_monitor
        m1 = get_monitor()
        m2 = get_monitor()
        assert m1 is m2


class TestDataHygieneRun:
    """DataHygiene.run() executes all rotation/cleanup tasks."""

    def test_run_returns_results_dict(self, tmp_path, monkeypatch):
        from core.monitor import DataHygiene
        dh = DataHygiene(root=tmp_path)
        results = dh.run()
        assert isinstance(results, dict)
        # All four methods should have executed
        for name in ("_rotate_cost_log", "_rotate_history",
                     "_clean_stale_backups", "_clean_trash_files"):
            assert name in results

    def test_rotate_cost_log_missing(self, tmp_path):
        from core.monitor import DataHygiene
        dh = DataHygiene(root=tmp_path)
        result = dh._rotate_cost_log()
        assert result == "not found"

    def test_rotate_history_missing(self, tmp_path):
        from core.monitor import DataHygiene
        dh = DataHygiene(root=tmp_path)
        result = dh._rotate_history()
        assert result == "not found"

    def test_clean_stale_backups_returns_message(self, tmp_path):
        from core.monitor import DataHygiene
        dh = DataHygiene(root=tmp_path)
        result = dh._clean_stale_backups()
        assert "removed" in result
