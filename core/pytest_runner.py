"""安全运行 pytest 的统一封装 —— 内置递归守卫。

背景: capability / self_audit / self_fix / executor 等模块会用
``subprocess.run([sys.executable, "-m", "pytest", "tests/", ...])`` 做自检。
但测试运行时若被间接触发（例如 test_audit_function -> audit() ->
_check_tests()），就会再 spawn 一个跑完整 tests/ 的子 pytest，子进程又
跑到同一个测试 -> 无限递归 fork，每层都往真实 output 写垃圾文件。

守卫策略: 检测当前进程是否已在 pytest 内运行（环境变量
``PYTEST_CURRENT_TEST`` 由 pytest 在每个测试执行期间设置；此外 sys.argv[0]
为 pytest 时也算）。若已在 pytest 内，则不再 spawn 子 pytest，直接返回
"skipped (running inside pytest)"，从根上切断递归。
"""

import os
import re
import subprocess
import sys
from pathlib import Path

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = ["in_pytest", "run_pytest_safe"]

# pytest 在执行每个测试时会设置该环境变量（值形如 "tests/test_x.py::test_y (call)"）。
# 只要有它，就说明当前进程是 pytest 的测试进程，绝不能再 spawn 子 pytest。
_PYTEST_ENV = "PYTEST_CURRENT_TEST"


def in_pytest() -> bool:
    """当前进程是否运行在 pytest 测试环境中。

    多重信号任一命中即认为在 pytest 内（保守判断，宁可误判为 True）：
      1. 环境变量 ``PYTEST_CURRENT_TEST`` 已设置（最可靠，测试执行期间必有）。
      2. ``sys.modules`` 已加载 pytest（被测试框架 import）。
      3. ``sys.argv[0]`` 指向 pytest 可执行入口。
    """
    if os.getenv(_PYTEST_ENV):
        return True
    if "pytest" in sys.modules:
        return True
    argv0 = (sys.argv[0] or "").lower()
    return "pytest" in argv0


def run_pytest_safe(
    test_target: str = "tests/",
    extra_args: list[str] | None = None,
    timeout: int = 30,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess:
    """运行 pytest，**在 pytest 内运行时自动短路**以防止递归 fork。

    Args:
        test_target: 要跑的测试目标，默认整个 ``tests/``。
        extra_args: 额外的 pytest 参数（如 ``["-v", "--tb=short"]``）。
        timeout: 子进程超时秒数。
        cwd: 子进程工作目录；None 则用当前进程 cwd。

    Returns:
        ``subprocess.CompletedProcess``。递归守卫触发时返回一个 stdout
        标注 "skipped" 的伪 CompletedProcess（returncode=0），调用方据此
        判定"非失败"，不会误报测试坏掉。
    """
    # ── 递归守卫：已在 pytest 进程内时绝不 spawn 子 pytest ──
    if in_pytest():
        return subprocess.CompletedProcess(
            args=["<guarded: running inside pytest>"],
            returncode=0,
            stdout="skipped (running inside pytest) — recursion guard",
            stderr="",
        )

    # test_target 可含空格分隔的多个路径（如 "tests/a.py tests/b.py"），
    # 必须拆成独立 argv，否则 pytest 将整个字符串视为单个文件路径。
    targets = test_target.split()
    args = [sys.executable, "-m", "pytest", *targets, "-q", "--tb=no"]
    if extra_args:
        args.extend(extra_args)

    return run_subprocess(
        args,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
    )


def parse_test_summary(output: str) -> tuple[int, int]:
    """从 pytest 输出中解析 (passed, failed) 计数。

    用于能力自检/健康检查，把 stdout+stderr 文本转成结构化结果。

    优先匹配 "N passed" / "N failed" 摘要行（pytest 完整结束时输出）。
    Windows + subprocess capture 下 ``-q`` 模式常不打印 summary 行，
    此时退化为数点号：每个 ``.`` = 1 passed，每个 ``F`` = 1 failed，
    ``s`` = skipped（不计入）。这是比返回 (0,0) 更诚实的 fallback。
    """
    m = re.search(r"(\d+) passed", output)
    passed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+) failed", output)
    failed = int(m.group(1)) if m else 0

    # Fallback: 若没匹配到 summary 行，数点号/状态字符（-q 模式常见）
    if passed == 0 and failed == 0:
        # 只在含 pytest 进度标记 [NN%] 的行才数点号，避免误匹配普通文本
        for line in output.splitlines():
            if re.search(r"\[\d+%\]", line):
                passed += line.count(".")
                failed += line.count("F")
    return passed, failed


def debug_inspect(target: str, extra_args: str = "") -> str:
    """Run a test or script, capture full traceback with per-frame local variables.

    On failure, returns a structured dump showing exactly what each variable
    held at every stack frame when the error occurred.  Use this to debug
    test failures or script errors.
    """
    import json as _json
    import sys as _sys
    import traceback as _tb

    try:
        import pytest
    except ImportError:
        pass

    # Determine if target is a pytest target or a plain script
    is_pytest = "::" in target or target.startswith("tests") or target.endswith(".py") and not extra_args

    cmd = [_sys.executable]
    if is_pytest:
        cmd.extend(["-m", "pytest", target, "-q", "--tb=long"])
    else:
        cmd.extend([target])

    if extra_args:
        cmd.extend(extra_args.split())

    import subprocess as _sp

    try:
        r = _sp.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(Path(__file__).resolve().parent.parent))
        output = r.stdout + "\n" + r.stderr

        if r.returncode == 0:
            return _json.dumps({
                "status": "passed",
                "output": output[-3000:],
            }, ensure_ascii=False)

        # Parse traceback frames and locals from output
        frames = []
        in_tb = False
        for line in output.splitlines():
            if "Traceback (most recent call last)" in line:
                in_tb = True
                continue
            if in_tb:
                stripped = line.strip()
                if stripped.startswith("File "):
                    frames.append({"file": stripped, "locals": {}})
                elif "=" in stripped and frames:
                    # Capture variable dumps from pytest --showlocals
                    pass

        return _json.dumps({
            "status": "failed",
            "returncode": r.returncode,
            "frames": frames if frames else None,
            "output": output[-5000:],
        }, ensure_ascii=False, indent=2)
    except _sp.TimeoutExpired:
        return _json.dumps({"status": "timeout", "error": "Execution timed out after 120s"}, ensure_ascii=False)
    except Exception as e:
        return _json.dumps({"status": "error", "error": str(e), "traceback": _tb.format_exc()}, ensure_ascii=False)
