"""CRUX TUI v3 Launcher — terminal check + graceful fallback.

Usage:
    python tools/crux_launcher.py              # Auto: TUI v3 if possible, else plain
    python tools/crux_launcher.py --tui-v3     # Force TUI v3
    python tools/crux_launcher.py --plain      # Force plain text REPL
    python tools/crux_launcher.py --check      # Just check terminal, don't launch
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_ROWS = 10
MIN_COLS = 80


def check_terminal() -> dict:
    """Check terminal suitability for TUI. Returns dict with status info."""
    result = {
        "ok": False,
        "cols": 80,
        "rows": 24,
        "terminal": "unknown",
        "issues": [],
    }

    # Detect terminal type
    if sys.platform == "win32":
        wt_session = os.environ.get("WT_SESSION", "")
        term = os.environ.get("TERM", "")
        term_program = os.environ.get("TERM_PROGRAM", "")

        if wt_session:
            result["terminal"] = "Windows Terminal"
        elif term_program == "vscode":
            result["terminal"] = "VS Code Terminal"
            result["issues"].append("VS Code 内置终端不支持全屏 TUI")
        elif "xterm" in term.lower() or "screen" in term.lower():
            result["terminal"] = f"PTY ({term})"
        else:
            result["terminal"] = "cmd.exe" if not term else f"cmd.exe (TERM={term})"
    else:
        result["terminal"] = sys.platform

    # Check size
    try:
        ts = shutil.get_terminal_size()
        result["cols"] = ts.columns
        result["rows"] = ts.lines

        if ts.lines < MIN_ROWS:
            result["issues"].append(f"终端高度 {ts.lines} 行 < 最低 {MIN_ROWS} 行")
        if ts.columns < MIN_COLS:
            result["issues"].append(f"终端宽度 {ts.columns} 列 < 最低 {MIN_COLS} 列")
    except (OSError, ValueError):
        result["issues"].append("无法获取终端尺寸")

    # Check stdin for proper console
    if not sys.stdin or not sys.stdin.isatty():
        result["issues"].append("stdin 不是终端 (可能是管道或重定向)")

    result["ok"] = len(result["issues"]) == 0
    return result


def launch_tui() -> int:
    """Launch TUI v3 with pre-flight checks."""
    info = check_terminal()

    if not info["ok"]:
        print("=" * 50)
        print("  CRUX TUI v3 — 终端检查失败")
        print("=" * 50)
        for issue in info["issues"]:
            print(f"  ✗ {issue}")
        print()
        print(f"  当前终端: {info['terminal']}")
        print(f"  尺寸: {info['cols']}x{info['rows']}")
        print()
        print("  解决方案:")
        print("    1. 使用 Windows Terminal 启动")
        print("    2. 或使用 cmd.exe (右键标题栏 → 属性 → 调整窗口大小)")
        print("    3. 或使用纯文本模式: python tools/crux_launcher.py --plain")
        print()
        return 1

    # All checks passed — launch
    print(f"CRUX TUI v3 starting ({info['terminal']}, {info['cols']}x{info['rows']})...")
    sys.stdout.flush()

    try:
        # Set TERM for Git Bash compatibility
        env = os.environ.copy()
        if sys.platform == "win32" and "TERM" not in env:
            env["TERM"] = "xterm-256color"

        result = subprocess.run(
            [sys.executable, str(ROOT / "crux_studio.py"), "--chat", "--tui-v3"],
            env=env,
            cwd=str(ROOT),
        )
        return result.returncode
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"启动失败: {e}", file=sys.stderr)
        return 1


def launch_plain() -> int:
    """Launch plain text REPL."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "crux_studio.py"), "--chat"],
        cwd=str(ROOT),
    )
    return result.returncode


def main() -> int:
    args = sys.argv[1:]

    if "--check" in args:
        info = check_terminal()
        for key, val in info.items():
            print(f"{key}: {val}")
        return 0 if info["ok"] else 1

    if "--plain" in args:
        return launch_plain()

    # Auto-detect: TUI v3 if terminal OK, else plain
    info = check_terminal()
    if info["ok"]:
        return launch_tui()
    else:
        print("终端不满足 TUI 要求，自动切换到纯文本模式...\n")
        sys.stdout.flush()
        return launch_plain()


if __name__ == "__main__":
    sys.exit(main())
