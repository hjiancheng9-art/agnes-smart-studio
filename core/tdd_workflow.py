"""TDD 工作流 — Red-Green-Refactor 深度集成

方法论第10章: 测试先行、Red-Green-Refactor 循环、覆盖率追踪。
在 run_test 基础上提供完整的 TDD 工作流引导。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TDD_DIR = Path(__file__).resolve().parent.parent / "output" / "tdd"
TDD_DIR.mkdir(parents=True, exist_ok=True)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def tdd_start(feature: str, test_files: list[str] | None = None) -> dict[str, Any]:
    """Start a TDD cycle for a feature.

    1. RED: Write failing tests first
    2. GREEN: Write minimal code to pass
    3. REFACTOR: Clean up while keeping tests green
    """
    session = {
        "id": feature.lower().replace(" ", "_")[:40],
        "feature": feature,
        "phase": "red",
        "test_files": test_files or [],
        "completed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "cycles": [],
    }
    (TDD_DIR / f"{session['id']}.json").write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    return session


def tdd_run_tests(test_path: str = "tests/", verbose: bool = False) -> dict[str, Any]:
    """Run tests and return structured results for RED/GREEN check."""
    cmd = [sys.executable, "-m", "pytest", test_path, "-p", "no:randomly", "--tb=short", "-q"]
    if verbose:
        cmd.append("-v")

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_PROJECT_ROOT),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        lines = r.stdout.strip().split("\n")
        summary = lines[-1] if lines else ""

        return {
            "passed": r.returncode == 0,
            "output": r.stdout[-500:],
            "summary": summary,
            "returncode": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "Timed out", "summary": "timeout"}
    except Exception as e:
        return {"passed": False, "output": str(e), "summary": "error"}


def tdd_cycle(session_id: str, phase: str, test_result: dict[str, Any], notes: str = "") -> dict[str, Any]:
    """Record a TDD cycle step.

    Phase: red | green | refactor
    """
    path = TDD_DIR / f"{session_id}.json"
    if not path.exists():
        return {"error": f"TDD session {session_id} not found"}

    session = json.loads(path.read_text(encoding="utf-8"))
    if session.get("completed"):
        return {"error": f"TDD session {session_id} already completed — nothing to record"}

    session["phase"] = phase
    session["cycles"].append(
        {
            "phase": phase,
            "test_passed": test_result.get("passed"),
            "summary": test_result.get("summary", ""),
            "notes": notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    session["updated_at"] = datetime.now(timezone.utc).isoformat()

    path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    return session


def tdd_done(session_id: str) -> dict[str, Any]:
    """Mark a TDD session as completed — removes red-phase gate."""
    path = TDD_DIR / f"{session_id}.json"
    if not path.exists():
        return {"error": f"TDD session {session_id} not found"}

    session = json.loads(path.read_text(encoding="utf-8"))
    session["completed"] = True
    session["completed_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"done": True, "session_id": session_id}


def tdd_abort(session_id: str) -> dict[str, Any]:
    """Abort and delete a TDD session — removes the red-phase gate immediately."""
    path = TDD_DIR / f"{session_id}.json"
    if not path.exists():
        return {"error": f"TDD session {session_id} not found"}
    path.unlink()
    return {"aborted": True, "session_id": session_id}


def tdd_status(session_id: str | None = None) -> dict[str, Any]:
    """Get TDD session status or list all sessions."""
    if session_id:
        path = TDD_DIR / f"{session_id}.json"
        if not path.exists():
            return {"error": f"Session {session_id} not found"}
        return json.loads(path.read_text(encoding="utf-8"))

    sessions = []
    for p in sorted(TDD_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        s = json.loads(p.read_text(encoding="utf-8"))
        sessions.append(
            {
                "id": s["id"],
                "feature": s["feature"],
                "phase": s["phase"],
                "completed": s.get("completed", False),
                "cycles": len(s.get("cycles", [])),
            }
        )
    return {"sessions": sessions}


# ── Tool definitions ──────────────────────────────────────────

TDD_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "tdd_start",
            "description": "Start a TDD cycle: RED → GREEN → REFACTOR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature": {"type": "string", "description": "Feature to implement test-first"},
                    "test_files": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["feature"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tdd_run_tests",
            "description": "Run tests and check if they pass (RED/GREEN check).",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_path": {"type": "string", "description": "Test path, default tests/"},
                    "verbose": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tdd_cycle",
            "description": "Record a TDD cycle step (red, green, or refactor).",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "phase": {"type": "string", "enum": ["red", "green", "refactor"]},
                    "test_result": {
                        "type": "object",
                        "properties": {"passed": {"type": "boolean"}, "summary": {"type": "string"}},
                    },
                    "notes": {"type": "string"},
                },
                "required": ["session_id", "phase", "test_result"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tdd_status",
            "description": "Show TDD session status or list all sessions.",
            "parameters": {"type": "object", "properties": {"session_id": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tdd_done",
            "description": "Mark a TDD session as completed — releases the red-phase write gate.",
            "parameters": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tdd_abort",
            "description": "Abort and delete a TDD session — removes the write gate immediately.",
            "parameters": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
        },
    },
]

TDD_EXECUTOR_MAP = {
    "tdd_start": lambda **kw: json.dumps(tdd_start(**kw), ensure_ascii=False),
    "tdd_run_tests": lambda **kw: json.dumps(
        tdd_run_tests(kw.get("test_path", "tests/"), kw.get("verbose", False)),
        ensure_ascii=False,
    ),
    "tdd_cycle": lambda **kw: json.dumps(tdd_cycle(**kw), ensure_ascii=False),
    "tdd_status": lambda **kw: json.dumps(tdd_status(session_id=kw.get("session_id")), ensure_ascii=False),
    "tdd_done": lambda **kw: json.dumps(tdd_done(kw["session_id"]), ensure_ascii=False),
    "tdd_abort": lambda **kw: json.dumps(tdd_abort(kw["session_id"]), ensure_ascii=False),
}
