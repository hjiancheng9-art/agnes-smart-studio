"""Tests for core/tool_call_log.py — JSONL call logging, rotation, querying."""

import json
import time
import tempfile
from pathlib import Path

import pytest
from core.tool_call_log import (
    MAX_BYTES,
    MAX_LINES,
    clear_log,
    group_by_tool,
    load_recent,
    log_call,
)


@pytest.fixture
def temp_log():
    """Redirect LOG_FILE to a temp file."""
    import core.tool_call_log as tcl

    original = tcl.LOG_FILE
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp = Path(f.name)
    tcl.LOG_FILE = tmp
    yield tmp
    tcl.LOG_FILE = original
    tmp.unlink(missing_ok=True)


class TestLogCall:
    def test_writes_record(self, temp_log):
        log_call("read_file", "ok", 3.2, {"path": "/tmp/x"})
        records = load_recent()
        assert len(records) == 1
        r = records[0]
        assert r["tool"] == "read_file"
        assert r["status"] == "ok"
        assert r["duration_ms"] == 3.2

    def test_args_keys_stored_not_values(self, temp_log):
        log_call("write_file", "ok", 0.5, {"path": "/tmp/secret", "content": "secret data"})
        records = load_recent()
        assert "args_keys" in records[0]
        # Keys sorted, values NOT stored
        assert records[0]["args_keys"] == sorted(["path", "content"])
        r_json = json.dumps(records[0])
        assert "secret" not in r_json

    def test_status_exception(self, temp_log):
        log_call("run_bash", "exception", 0.0)
        records = load_recent()
        assert records[0]["status"] == "exception"
        assert records[0]["duration_ms"] == 0.0

    def test_none_args_becomes_empty_list(self, temp_log):
        log_call("web_fetch", "ok", 0.1, None)
        records = load_recent()
        assert records[0]["args_keys"] == []

    def test_multiple_calls_ordered(self, temp_log):
        log_call("a", "ok", 0.1)
        log_call("b", "ok", 0.2)
        log_call("c", "ok", 0.3)
        records = load_recent()
        assert len(records) >= 3
        tools = [r["tool"] for r in records[:3]]
        assert "c" in tools
        assert "b" in tools
        assert "a" in tools

    def test_duration_rounded_to_2_decimal(self, temp_log):
        log_call("x", "ok", 3.216789)
        records = load_recent()
        assert records[0]["duration_ms"] == 3.22

    def test_ts_is_float(self, temp_log):
        log_call("x", "ok", 0.0)
        records = load_recent()
        assert isinstance(records[0]["ts"], float)

    def test_line_is_valid_jsonl(self, temp_log):
        log_call("x", "ok", 0.0)
        assert temp_log.exists()
        with open(temp_log, encoding="utf-8") as fh:
            line = fh.readline()
        rec = json.loads(line)
        assert rec["tool"] == "x"


class TestLoadRecent:
    def test_empty_file_returns_empty(self, temp_log):
        records = load_recent()
        assert records == []

    def test_limit_respected(self, temp_log):
        for i in range(10):
            log_call(f"tool_{i}", "ok", 0.0)
        records = load_recent(limit=3)
        assert len(records) == 3

    def test_tool_name_filter(self, temp_log):
        log_call("read_file", "ok", 0.0)
        log_call("write_file", "ok", 0.0)
        log_call("read_file", "ok", 0.0)
        records = load_recent(tool_name="read_file")
        assert len(records) == 2
        for r in records:
            assert r["tool"] == "read_file"

    def test_large_limit(self, temp_log):
        log_call("a", "ok", 0.0)
        records = load_recent(limit=99999)
        assert len(records) <= 1


class TestGroupByTool:
    def test_groups_by_tool_name(self, temp_log):
        log_call("read_file", "ok", 0.0)
        log_call("read_file", "ok", 0.0)
        log_call("write_file", "ok", 0.0)
        grouped = group_by_tool()
        assert "read_file" in grouped
        assert "write_file" in grouped
        assert len(grouped["read_file"]) == 2
        assert len(grouped["write_file"]) == 1

    def test_empty_returns_empty(self, temp_log):
        grouped = group_by_tool()
        assert grouped == {}


class TestClearLog:
    def test_returns_cleared_count(self, temp_log):
        log_call("a", "ok", 0.0)
        log_call("b", "ok", 0.0)
        cleared = clear_log()
        assert cleared == 2

    def test_clears_file(self, temp_log):
        log_call("a", "ok", 0.0)
        clear_log()
        records = load_recent()
        assert records == []

    def test_empty_file_returns_zero(self, temp_log):
        cleared = clear_log()
        assert cleared == 0


class TestConstants:
    def test_max_bytes(self):
        assert MAX_BYTES == 5 * 1024 * 1024

    def test_max_lines(self):
        assert MAX_LINES == 5000


class TestNoExceptionOnBadData:
    def test_corrupt_json_line_skipped(self, temp_log):
        log_call("good", "ok", 0.0)
        with open(temp_log, "a", encoding="utf-8") as fh:
            fh.write("this is not json\n")
        log_call("good2", "ok", 0.0)
        records = load_recent()
        tools = [r["tool"] for r in records]
        assert "good" in tools or "good2" in tools
