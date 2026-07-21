"""Lightweight runtime inspector — traceback + frame locals without debugpy.

Captures full traceback with per-frame local variable values when a test
or script fails. This gives LLMs the equivalent of a breakpoint inspection
without needing a real debugger (debugpy/DAP) attached.

Design:
    Uses Python's built-in traceback.TracebackException with frame locals
    captured via a custom excepthook. Works with any Python script or test.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

_MAX_VAR_REPR_LEN = 200  # truncate long reprs
_MAX_FRAMES = 30  # max traceback frames
_MAX_VARS_PER_FRAME = 20  # max locals per frame


def _safe_repr(obj: Any) -> str:
    """repr() with length limit and exception safety."""
    try:
        s = repr(obj)
        if len(s) > _MAX_VAR_REPR_LEN:
            s = s[:_MAX_VAR_REPR_LEN] + "..."
        return s
    except Exception:
        return f"<{type(obj).__name__}: repr failed>"


def _filter_locals(loc: dict[str, Any]) -> dict[str, str]:
    """Filter and serialize frame locals, skipping internals."""
    result = {}
    count = 0
    for k, v in sorted(loc.items()):
        if k.startswith("__") and k.endswith("__"):
            continue  # skip dunders
        if count >= _MAX_VARS_PER_FRAME:
            break
        result[k] = _safe_repr(v)
        count += 1
    return result


def _format_exception(exc_type, exc_value, exc_tb) -> str:
    """Format a traceback with frame locals as JSON string."""
    frames = []
    tb_list = traceback.extract_tb(exc_tb, limit=_MAX_FRAMES)
    tb_obj = exc_tb

    for _i, frame_summary in enumerate(tb_list):
        frame_info = {
            "file": frame_summary.filename,
            "line": frame_summary.lineno,
            "function": frame_summary.name,
            "code": frame_summary.line or "",
        }
        # Get locals from the traceback object
        if tb_obj is not None:
            try:
                frame_info["locals"] = _filter_locals(tb_obj.tb_frame.f_locals)
            except Exception:
                frame_info["locals"] = {}
            tb_obj = tb_obj.tb_next
        frames.append(frame_info)

    error_info = {
        "exception": f"{exc_type.__name__}: {exc_value}" if exc_type else str(exc_value),
        "type": exc_type.__name__ if exc_type else "Unknown",
        "message": str(exc_value)[:1000],
        "frames": frames,
        "frame_count": len(frames),
    }

    # Add traceback string for readability
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb, limit=_MAX_FRAMES)
    error_info["traceback"] = "".join(tb_lines)[:4000]

    return json.dumps(error_info, ensure_ascii=False, indent=2)


def inspect_script(script_path: str, args: str = "") -> str:
    """Run a Python script and capture traceback + frame locals on failure.

    Args:
        script_path: Path to .py script
        args: Optional space-separated arguments

    Returns JSON with {ok, exception, frames, traceback}.
    """
    return _run_with_inspect(
        [sys.executable, script_path] + (args.split() if args.strip() else []),
        cwd=str(ROOT),
    )


def inspect_test(test_target: str = "tests/", extra_args: str = "") -> str:
    """Run pytest target and capture traceback + frame locals for each failure.

    Args:
        test_target: pytest path (e.g. 'tests/' or 'tests/test_foo.py::test_bar')
        extra_args: extra pytest flags (e.g. '-x -k test_name')

    Returns JSON with {ok, failures, summary}.
    """
    cmd = [sys.executable, "-m", "pytest", test_target, "-q", "--tb=long"]
    if extra_args.strip():
        cmd.extend(extra_args.split())
    return _run_with_inspect(cmd, cwd=str(ROOT))


def _run_with_inspect(cmd: list[str], cwd: str) -> str:
    """Run command and capture output. Wraps with inspect hook for failures."""
    # Write a wrapper script that installs the capture hook
    wrapper = (
        "import sys, json, traceback as _tb\n"
        "_orig_excepthook = sys.excepthook\n"
        "def _capture_hook(typ, val, tb):\n"
        "    frames = []\n"
        "    tb_obj = tb\n"
        "    for fs in _tb.extract_tb(tb, limit=30):\n"
        "        fi = {'file': fs.filename, 'line': fs.lineno, "
        "'function': fs.name, 'code': fs.line or ''}\n"
        "        locs = {}\n"
        "        if tb_obj:\n"
        "            try:\n"
        "                for k, v in sorted(tb_obj.tb_frame.f_locals.items()):\n"
        "                    if k.startswith('__') and k.endswith('__'): continue\n"
        "                    try: locs[k] = repr(v)[:200]\n"
        "                    except Exception: locs[k] = '<repr failed>'\n"
        "            except Exception: pass\n"
        "            tb_obj = tb_obj.tb_next\n"
        "        fi['locals'] = locs\n"
        "        frames.append(fi)\n"
        "    err = {'type': typ.__name__, 'message': str(val)[:1000], "
        "'traceback': ''.join(_tb.format_exception(typ, val, tb, limit=30))[:4000], "
        "'frames': frames}\n"
        "    print('\\n__CRUX_INSPECT__' + json.dumps(err, ensure_ascii=False) + '__CRUX_INSPECT_END__')\n"
        "    _orig_excepthook(typ, val, tb)\n"
        "sys.excepthook = _capture_hook\n"
        "# SECURITY: exec() runs only on CRUX-owned test/script files, not untrusted input\n"
        "exec(open(sys.argv[1], 'rb').read(), {'__name__': '__main__', '__file__': sys.argv[1]})\n"
    )
    wrapper_path = Path(cwd) / "output" / "_inspect_wrapper.py"
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text(wrapper, encoding="utf-8")

    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cwd,
            env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"},
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "error": "timeout after 120s"}, ensure_ascii=False)
    finally:
        with contextlib.suppress(OSError):
            wrapper_path.unlink()

    output = (r.stdout or "") + "\n" + (r.stderr or "")
    ok = r.returncode == 0

    # Extract __CRUX_INSPECT__ blocks from output
    failures = []
    marker_start = "__CRUX_INSPECT__"
    marker_end = "__CRUX_INSPECT_END__"
    pos = 0
    while True:
        start = output.find(marker_start, pos)
        if start == -1:
            break
        end = output.find(marker_end, start)
        if end == -1:
            break
        try:
            data = json.loads(output[start + len(marker_start) : end])
            failures.append(data)
        except json.JSONDecodeError:
            pass
        pos = end + len(marker_end)

    return json.dumps(
        {
            "ok": ok,
            "returncode": r.returncode,
            "failures": failures,
            "failure_count": len(failures),
            "summary": output.replace(marker_start, "").replace(marker_end, "")[:3000],
        },
        ensure_ascii=False,
        indent=2,
    )


# For direct use: run and capture synchronously
def inspect_last_error() -> str:
    """Inspect the most recent error from output/last_error.txt if it exists."""
    err_path = ROOT / "output" / "last_error.txt"
    if not err_path.exists():
        return json.dumps({"ok": True, "message": "No recent error file found."}, ensure_ascii=False)
    raw = err_path.read_text(encoding="utf-8")[:10000]
    # Parse out traceback
    try:
        lines = raw.splitlines()
        tb_lines = []
        for line in lines:
            if "Traceback" in line or "  File " in line or line.strip().startswith("    "):
                tb_lines.append(line)
        return json.dumps(
            {
                "ok": False,
                "source": str(err_path),
                "traceback": "\n".join(tb_lines)[:4000],
                "raw": raw[:3000],
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception:
        return json.dumps({"ok": False, "raw": raw[:3000]}, ensure_ascii=False)


# ── Tool definitions ────────────────────────────────────────

INSPECT_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "debug_inspect",
            "description": "Run a test or script and capture full traceback with per-frame local variable values on failure. Use this to debug test failures or script errors — see exactly what variables were at each stack frame when the error occurred.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Test target or script path. e.g. 'tests/' or 'tests/test_foo.py::test_bar' or 'core/agent.py'",
                    },
                    "extra_args": {
                        "type": "string",
                        "description": "Extra pytest flags (e.g. '-x -k test_name') or script arguments",
                    },
                },
                "required": ["target"],
            },
        },
    },
]

INSPECT_EXECUTOR_MAP = {
    "debug_inspect": lambda **kw: inspect_test(
        test_target=str(kw.get("target", "tests/")),
        extra_args=str(kw.get("extra_args", "")),
    ),
}
