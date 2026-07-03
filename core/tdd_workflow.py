"""TDD 工作流 — Red-Green-Refactor 深度集成

方法论第10章: 测试先行、Red-Green-Refactor 循环、覆盖率追踪。
在 run_test 基础上提供完整的 TDD 工作流引导。
"""

import json
import subprocess
from pathlib import Path

TDD_DIR = Path("output/tdd")
TDD_DIR.mkdir(parents=True, exist_ok=True)


def tdd_start(feature: str, test_files: list[str] | None = None) -> dict:
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
        "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "cycles": [],
    }
    (TDD_DIR / f"{session['id']}.json").write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    return session


def tdd_run_tests(test_path: str = "tests/", verbose: bool = False) -> dict:
    """Run tests and return structured results for RED/GREEN check."""
    cmd = ["python", "-m", "pytest", test_path, "--tb=short", "-q"]
    if verbose:
        cmd.append("-v")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        passed = r.returncode == 0

        # Parse test count
        lines = r.stdout.strip().split("\n")
        summary = lines[-1] if lines else ""

        return {
            "passed": passed,
            "output": r.stdout[-500:],
            "summary": summary,
            "returncode": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "Timed out", "summary": "timeout"}
    except Exception as e:
        return {"passed": False, "output": str(e), "summary": "error"}


def tdd_cycle(session_id: str, phase: str, test_result: dict, notes: str = "") -> dict:
    """Record a TDD cycle step.

    Phase: red | green | refactor
    """
    path = TDD_DIR / f"{session_id}.json"
    if not path.exists():
        return {"error": f"TDD session {session_id} not found"}

    session = json.loads(path.read_text(encoding="utf-8"))
    session["phase"] = phase
    session["cycles"].append(
        {
            "phase": phase,
            "test_passed": test_result.get("passed"),
            "summary": test_result.get("summary", ""),
            "notes": notes,
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
    )
    session["updated_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

    path.write_text(json.dumps(session, indent=2, ensure_ascii=False), encoding="utf-8")
    return session


def tdd_status(session_id: str | None = None) -> dict:
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
            {"id": s["id"], "feature": s["feature"], "phase": s["phase"], "cycles": len(s.get("cycles", []))}
        )
    return {"sessions": sessions}


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
]

TDD_EXECUTOR_MAP = {
    "tdd_start": lambda **kw: json.dumps(tdd_start(**kw), ensure_ascii=False),
    "tdd_run_tests": lambda **kw: json.dumps(
        tdd_run_tests(kw.get("test_path", "tests/"), kw.get("verbose", False)), ensure_ascii=False
    ),
    "tdd_cycle": lambda **kw: json.dumps(tdd_cycle(**kw), ensure_ascii=False),
    "tdd_status": lambda **kw: json.dumps(tdd_status(**kw.get("session_id")), ensure_ascii=False),
}
