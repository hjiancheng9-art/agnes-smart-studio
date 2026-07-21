"""Tests for tools/crux_bridge.py -- VS Code extension protocol bridge.

Test split:
  - TestPureFunctions (no API, no subprocess): pure logic units
  - TestProtocolContract (subprocess, no API): structural protocol checks
  - TestLiveChat (subprocess + API): marked @slow, skipped in CI by default
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
BRIDGE = PROJECT_ROOT / "tools" / "crux_bridge.py"


# ── Helpers ───────────────────────────────────────────────────────


def _run_bridge(stdin_text: str, timeout: float = 5.0) -> tuple[int, list[dict], str]:
    """Run bridge with stdin, return (exit_code, parsed_messages, stderr)."""
    proc = subprocess.run(
        [sys.executable, "-u", str(BRIDGE)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(PROJECT_ROOT),
    )
    msgs: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msgs.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return proc.returncode, msgs, proc.stderr


def _send(*calls: dict, timeout: float = 5.0) -> tuple[int, list[dict], str]:
    """Serialize call dicts as stdin lines and run bridge."""
    raw = "\n".join(json.dumps(c, ensure_ascii=False) for c in calls) + "\n"
    return _run_bridge(raw, timeout=timeout)


# ── Pure function tests (no subprocess, no API) ───────────────────


class TestPureFunctions:
    def test_build_context_empty(self):
        from tools.crux_bridge import build_context_prefix

        assert build_context_prefix(None) == ""
        assert build_context_prefix([]) == ""

    def test_build_context_single_file(self):
        from tools.crux_bridge import build_context_prefix

        result = build_context_prefix([{"path": "foo.py", "content": "x = 1"}])
        assert "foo.py" in result
        assert "x = 1" in result
        assert result.endswith("User: ")

    def test_build_context_truncates_large_file(self):
        from tools.crux_bridge import build_context_prefix

        big = "x" * 20000
        result = build_context_prefix([{"path": "big.py", "content": big}])
        assert "truncated" in result
        assert len(result) < 25000

    def test_parse_tool_activity_read(self):
        from tools.crux_bridge import _parse_tool_activity

        result = _parse_tool_activity("reading core/chat.py")
        assert result is not None
        assert result[0] == "read_file"

    def test_parse_tool_activity_search(self):
        from tools.crux_bridge import _parse_tool_activity

        result = _parse_tool_activity("searching for TODO")
        assert result is not None
        assert result[0] == "search_files"

    def test_parse_tool_activity_no_match(self):
        from tools.crux_bridge import _parse_tool_activity

        assert _parse_tool_activity("hello world") is None

    def test_handle_reset_none_session_emits_error(self):
        """handle_reset(None) must not crash — emits error + done."""
        from tools import crux_bridge as mod

        captured: list[dict] = []
        original = mod.emit
        mod.emit = lambda mid, t, c="", **kw: captured.append({"id": mid, "type": t, "content": c})
        try:
            mod.handle_reset(None, "r1")
        finally:
            mod.emit = original
        types = [m["type"] for m in captured]
        assert "error" in types
        assert "done" in types

    def test_handle_reset_delegates_to_session(self):
        from tools import crux_bridge as mod

        class FakeSession:
            def __init__(self):
                self.called = False

            def reset(self):
                self.called = True

        session = FakeSession()
        mod.emit = lambda *a, **kw: None
        try:
            mod.handle_reset(session, "r2")
            assert session.called
        finally:
            # restore real emit
            from tools.crux_bridge import emit as real_emit

            mod.emit = real_emit


# ── Protocol contract tests (subprocess, no API needed) ───────────


class TestProtocolContract:
    def test_bridge_file_exists(self):
        assert BRIDGE.exists(), f"Bridge not found: {BRIDGE}"

    def test_quit_terminates_cleanly(self):
        _rc, msgs, _ = _send({"id": "q", "method": "quit"})
        assert _rc == 0
        assert any(m["type"] == "done" and m["id"] == "q" for m in msgs)

    def test_unknown_method_emits_error(self):
        rc, msgs, _ = _send({"id": "u", "method": "frobnicate", "params": {}})
        assert rc == 0
        assert any(m["type"] == "error" and m["id"] == "u" for m in msgs)
        assert any(m["type"] == "done" and m["id"] == "u" for m in msgs)

    def test_missing_prompt_emits_error(self):
        rc, msgs, _ = _send({"id": "p", "method": "chat", "params": {}})
        assert rc == 0
        assert any(m["type"] == "error" and m["id"] == "p" for m in msgs)
        assert any(m["type"] == "done" and m["id"] == "p" for m in msgs)

    def test_every_message_has_required_keys(self):
        _rc, msgs, _ = _send({"id": "s", "method": "quit"})
        for m in msgs:
            assert "id" in m, f"Missing 'id' in {m}"
            assert "type" in m, f"Missing 'type' in {m}"
            assert "content" in m, f"Missing 'content' in {m}"

    def test_invalid_json_skipped_not_crash(self):
        """Malformed JSON line should be skipped; subsequent valid lines still work."""
        rc, msgs, _ = _run_bridge('{not valid json}\n{"id":"q","method":"quit"}\n')
        assert rc == 0
        assert any(m["id"] == "q" and m["type"] == "done" for m in msgs)

    def test_empty_lines_skipped(self):
        """Blank stdin lines should not crash the bridge."""
        rc, msgs, _ = _run_bridge('\n\n  \n{"id":"q","method":"quit"}\n')
        assert rc == 0
        assert any(m["id"] == "q" for m in msgs)


# ── Live chat tests (require real API, marked slow) ───────────────


@pytest.mark.slow
class TestLiveChat:
    def test_chat_emits_text_and_done(self):
        rc, msgs, _ = _send(
            {"id": "1", "method": "chat", "params": {"prompt": "say hi in one word"}},
            timeout=60,
        )
        assert rc == 0
        types = [m["type"] for m in msgs if m["id"] == "1"]
        assert "text" in types
        assert "done" in types
        text_msgs = [m for m in msgs if m["id"] == "1" and m["type"] == "text"]
        assert any(m["content"] for m in text_msgs)

    def test_chat_with_files_context(self):
        rc, msgs, _ = _send(
            {
                "id": "2",
                "method": "chat",
                "params": {
                    "prompt": "what language? one word answer",
                    "files": [{"path": "test.py", "content": "print('hi')"}],
                },
            },
            timeout=60,
        )
        assert rc == 0
        assert any(m["id"] == "2" and m["type"] == "done" for m in msgs)

    def test_multi_turn_preserves_history(self):
        _rc, msgs, _ = _send(
            {"id": "t1", "method": "chat", "params": {"prompt": "remember secret word 'pineapple'. reply ok."}},
            {"id": "t2", "method": "chat", "params": {"prompt": "what was the secret word?"}},
            timeout=120,
        )
        t2 = "".join(m["content"] for m in msgs if m["id"] == "t2" and m["type"] == "text")
        assert "pineapple" in t2.lower()
