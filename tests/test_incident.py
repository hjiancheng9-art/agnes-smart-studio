"""Tests for core/incident.py — classifier, store, playbooks."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.incident import (
    FAILURE_TAXONOMY,
    PLAYBOOKS,
    classify_failure,
    classify_run,
    get_incident_trends,
    load_incidents,
    save_incident,
    should_alert,
)


class TestClassifyFailure:
    def test_classify_timeout(self):
        result = classify_failure("Request timed out after 30s")
        assert result["category"] == "timeout"
        assert result["severity"] == "medium"

    def test_classify_auth_error(self):
        result = classify_failure("HTTP 403 Forbidden — access denied")
        assert result["category"] in ("auth_error", "provider_unavailable")
        assert result["severity"] in ("high", "medium")

    def test_classify_rate_limit(self):
        result = classify_failure("429 TooManyRequests — quota exceeded")
        assert result["category"] == "rate_limit"

    def test_classify_unknown(self):
        result = classify_failure("some random error message never seen before")
        assert result["category"] == "unknown"

    def test_classify_run_returns_dict(self):
        result = classify_run({"ok": False, "errors": ["timeout"]}, [{"event": "task_timeout", "error": "timeout"}])
        assert isinstance(result, dict)
        assert "primary_category" in result


class TestPlaybooks:
    def test_all_categories_have_playbook(self):
        for cat in FAILURE_TAXONOMY:
            assert cat in PLAYBOOKS, f"Missing playbook for: {cat}"

    def test_playbooks_have_title_and_steps(self):
        for cat, pb in PLAYBOOKS.items():
            assert "title" in pb
            assert "steps" in pb
            assert isinstance(pb["steps"], list)

    def test_format_playbook(self):
        from core.incident import format_playbook

        text = format_playbook("timeout", "trace123")
        assert "trace123" in text or "timeout" in text.lower()


class TestIncidentStore:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.orig_file = None
        try:
            from core.incident import INCIDENT_FILE

            self.orig_file = INCIDENT_FILE
        except ImportError:
            pass

    def teardown_method(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_load(self):
        # Use a temp file
        tmp_file = os.path.join(self.tmp, "incidents.jsonl")
        with patch("core.incident.INCIDENT_FILE", tmp_file):
            save_incident({"primary_category": "timeout", "severities": {"medium": 1}, "total_incidents": 1, "summary": "test", "recommendation": "retry"})
            save_incident({"primary_category": "auth_error", "severities": {"high": 1}, "total_incidents": 1, "summary": "test2", "recommendation": "check key"})
            incidents = load_incidents(limit=10)
            assert len(incidents) >= 2

    def test_load_empty(self):
        tmp_file = os.path.join(self.tmp, "nonexistent.jsonl")
        with patch("core.incident.INCIDENT_FILE", tmp_file):
            incidents = load_incidents()
            assert incidents == []

    def test_load_with_filter(self):
        tmp_file = os.path.join(self.tmp, "incidents.jsonl")
        with patch("core.incident.INCIDENT_FILE", tmp_file):
            save_incident({"primary_category": "test", "severities": {"low": 1}, "total_incidents": 1, "summary": "open", "recommendation": ""})
            # Add status field manually
            with open(tmp_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"timestamp": 0, "category": "test", "status": "resolved"}) + "\n")
            open_incs = load_incidents(status_filter="open")
            assert len(open_incs) >= 1

    def test_should_alert(self):
        tmp_file = os.path.join(self.tmp, "incidents.jsonl")
        with patch("core.incident.INCIDENT_FILE", tmp_file):
            for _ in range(5):
                save_incident({"primary_category": "timeout", "severities": {"medium": 1}, "total_incidents": 1, "summary": "test", "recommendation": "retry"})
            result = should_alert({"primary_category": "timeout"}, threshold=3)
            assert result["alert"] is True

    def test_trends(self):
        tmp_file = os.path.join(self.tmp, "incidents.jsonl")
        with patch("core.incident.INCIDENT_FILE", tmp_file):
            save_incident({"primary_category": "timeout", "severities": {"medium": 1}, "total_incidents": 1, "summary": "test", "recommendation": "retry"})
            trends = get_incident_trends(hours=24)
            assert isinstance(trends, dict)
