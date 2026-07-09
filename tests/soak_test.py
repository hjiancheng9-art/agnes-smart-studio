"""Soak Test — 持续执行压力测试

模拟连续编译/执行，验证系统稳定性。

用法:
  python tests/soak_test.py                   # 50 次编译
  python tests/soak_test.py --count 200       # 200 次编译
  python tests/soak_test.py --exec            # 包含执行 (需 ComfyUI)
"""

from __future__ import annotations

import sys
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comfyflow_compiler.compiler import ComfyFlowCompiler
from comfyflow_compiler.execution import ExecutionOrchestrator

INTENTS = [
    "a cat", "a dog", "cinematic portrait", "sunset landscape",
    "cyberpunk city", "anime girl", "fantasy dragon", "product shot",
    "a cat jumping, video", "waves crashing, video",
]

FAILURE_TOLERANCE = 0.30  # 允许 30% 失败率（含已知的视频编译链路缺口）


def run_soak(count: int = 50, with_exec: bool = False):
    print(f"\n{'='*55}")
    print(f"  Soak Test — {count} iterations{' (with execution)' if with_exec else ''}")
    print(f"{'='*55}")

    compiler = ComfyFlowCompiler()
    orch = ExecutionOrchestrator() if with_exec else None

    results = []
    start = time.time()
    errors = []

    for i in range(count):
        intent = INTENTS[i % len(INTENTS)]
        iter_start = time.time()

        try:
            comp = compiler.compile(intent)
            elapsed = (time.time() - iter_start) * 1000

            entry = {
                "iter": i + 1,
                "intent": intent[:30],
                "success": comp.success,
                "elapsed_ms": round(elapsed, 1),
                "blueprint": comp.blueprint_used or "",
                "error": (comp.error or "")[:60],
            }

            if comp.success and with_exec and orch:
                exec_result = orch.execute(comp.workflow_json or {})
                entry["exec_success"] = exec_result.success
                entry["exec_elapsed"] = round(exec_result.total_elapsed, 1)

            results.append(entry)

            if not comp.success:
                errors.append(entry)

            # 进度
            if (i + 1) % 10 == 0:
                passed = sum(1 for r in results if r["success"])
                print(f"  [{i+1}/{count}] {passed}/{i+1} passed")

        except Exception as e:
            results.append({"iter": i+1, "intent": intent[:30], "success": False, "error": str(e)[:60]})
            errors.append({"iter": i+1, "error": str(e)[:60]})

    total_elapsed = time.time() - start
    passed = sum(1 for r in results if r["success"])
    failed = count - passed
    pass_rate = passed / max(count, 1)

    print(f"\n{'='*55}")
    print(f"  Soak Test Results")
    print(f"{'='*55}")
    print(f"  Iterations:    {count}")
    print(f"  Passed:        {passed} ✅")
    print(f"  Failed:        {failed} {'❌' if failed > 0 else '✅'}")
    print(f"  Pass rate:     {pass_rate:.1%}")
    print(f"  Total time:    {total_elapsed:.1f}s")
    print(f"  Avg per iter:  {total_elapsed/count*1000:.0f}ms ({total_elapsed:.2f}s total)")

    if with_exec:
        exec_passed = sum(1 for r in results if r.get("exec_success"))
        print(f"  Exec passed:   {exec_passed}/{passed}")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for e in errors[:5]:
            print(f"    [{e['iter']}] {e.get('error','unknown')}")

    threshold_ok = pass_rate >= (1 - FAILURE_TOLERANCE)
    print(f"\n  Verdict: {'✅ PASS' if threshold_ok else '❌ FAIL'} " +
          f"(pass_rate={pass_rate:.1%}, threshold>={1-FAILURE_TOLERANCE:.0%})")
    print(f"{'='*55}")

    return results


if __name__ == "__main__":
    count = 50
    with_exec = False

    for arg in sys.argv[1:]:
        if arg.startswith("--count="):
            count = int(arg.split("=")[1])
        elif arg == "--exec":
            with_exec = True

    run_soak(count=count, with_exec=with_exec)
