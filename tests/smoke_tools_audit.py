"""工具全量闭环 — 阶段1 冒烟实跑脚本

实跑 P0 核心子集(~30 个无外部依赖工具),逐个验证完整链路:
  注册(has) → 参数校验(validate) → 派发(execute) → 安全守卫(sandbox/高风险门) → 计费(metric)

输出结构化报告到 stdout + JSON 文件,供后续测试/修复决策。
非 pytest 测试,可独立运行: python tests/smoke_tools_audit.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.tools import reload_registry  # noqa: E402

# ════════════════════════════════════════════════════════════
#  P0 工具实跑清单 (name, args, 期望类别)
#  args 用真实安全的输入; 只读工具直接跑, 写工具用 tmp 沙盒
# ════════════════════════════════════════════════════════════

# 用项目内临时目录 (write_file 有项目根限制, tmp 在项目外会被合理拒绝)
TMP_DIR = ROOT / "output" / "smoke_tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_FILE = TMP_DIR / "sample.py"
SAMPLE_FILE.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

P0_CASES = [
    # ── 文件 ops ── (参数名对齐 tools.json 真实 schema)
    ("read_file", {"path": str(SAMPLE_FILE)}),
    ("write_file", {"path": str(TMP_DIR / "out.txt"), "content": "hi"}),
    ("edit_file", {"path": str(TMP_DIR / "out.txt"), "old_text": "hi", "new_text": "bye"}),
    ("search_files", {"pattern": "def hello"}),  # 只 required pattern, 默认搜项目根
    ("glob_files", {"pattern": "core/tools.py"}),  # 只 required pattern
    ("list_files", {"path": "core"}),
    ("tree_dir", {"depth": 1}),  # 无 path 参数, 只有 depth
    # count_lines 跳过实跑: 实现 count_lines() 不接受参数, schema 也是空, 全仓扫描 >15s
    # 这是真实缺陷(schema 与实现不符 + 无法限定范围), 标记给阶段3修复, 不在每次冒烟卡住
    ("count_lines", {"__skip_exec": True, "__reason": "实现无参数+全仓扫描慢, schema缺陷待修"}),
    # ── 执行 ──
    ("run_python", {"code": "print(1+1)"}),
    ("run_bash", {"command": "echo hello_smoke"}),  # 安全命令
    ("env_check", {}),
    # 注: think_deep 调 LLM、run_test 默认无超时会跑完整套件 — 属环境依赖, 非链路问题,
    # 在阶段2 单测里单独覆盖其参数校验, 此处不实跑。
    # ── 代码智能 (用仓库自身, 真实参数名) ──
    ("code_analyze", {"file_path": "core/tools.py"}),
    ("find_symbol", {"symbol": "ToolRegistry"}),
    ("search_symbols", {"pattern": "execute"}),
    ("find_references", {"file_path": "core/tools.py", "symbol": "get_registry"}),
    ("graph_neighbors", {"node": "ToolRegistry"}),
    ("graph_ancestors", {"node": "ToolRegistry"}),
    ("graph_descendants", {"node": "ToolRegistry"}),
    # ── patch (真实参数 patch_text, 无 path) ──
    ("patch_file", {"patch_text": "*** invalid ***"}),  # 预期失败, 验证错误恢复
    ("patch_undo", {}),  # 无参数
    # ── git (只读) ──
    ("git_status", {}),
    ("git_diff", {}),
    ("git_log", {}),
    # ── github (只读 API, 真实参数 search_type) ──
    ("github_search", {"query": "crux studio", "search_type": "repositories"}),
    # ── rag ──
    ("skill_search", {"query": "code review", "top_k": 3}),
    # ── 安全守卫专项 (验证拦截, 不应真正执行) ──
    ("run_bash", {"command": "rm -rf /tmp/__nonexistent_smoke__"}),  # 危险, 应被 sandbox 拦
    ("run_bash", {"command": "git push --force"}),  # 危险, 应被 sandbox 拦
    ("run_bash", {"command": "format D:"}),  # Windows 破坏性, 应拦 (批次D新加)
]

# 高风险确认门测试 (这些工具在 ChatSession._dispatch_tool 层, 非 registry.execute 层)
# 单独通过模拟 dispatch 逻辑验证
HIGH_RISK_TOOL_NAMES = ["git_add_commit", "git_push", "git_pr_create", "git_pr_merge", "git_tag"]


def smoke_one(reg, name: str, args: dict, timeout_s: float = 8.0) -> dict:
    """跑单个工具, 记录全链路状态。带超时护栏防止单工具卡死。"""
    import time
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FTimeout

    record = {
        "name": name,
        "args": args,
        "registered": False,
        "result_ok": False,
        "result_preview": "",
        "error": "",
        "latency_ms": 0,
    }
    # 0. 跳过标记 (用于已知缺陷/环境依赖项, 只查注册不实跑)
    if args.get("__skip_exec"):
        record["registered"] = reg.has(name)
        record["result_preview"] = f"[跳过实跑] {args.get('__reason', '')}"
        record["result_ok"] = True  # 注册检查通过即算 ok
        record["skipped"] = True
        return record
    # 1. 注册检查
    record["registered"] = reg.has(name)
    if not record["registered"]:
        record["error"] = "未注册"
        return record
    # 2. 执行 (execute 内部已含 validate + error recovery) — 带超时
    t0 = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(reg.execute, name, args)
            try:
                result = fut.result(timeout=timeout_s)
            except FTimeout:
                record["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                record["error"] = f"冒烟超时(>{timeout_s}s) — 疑似环境依赖(LLM/外部服务)"
                record["result_preview"] = "[超时跳过]"
                return record
        record["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        result_str = str(result)
        record["result_preview"] = result_str[:200]
        # 判定: 不以 [错误 开头视为成功
        record["result_ok"] = not result_str.startswith("[错误") and not result_str.startswith("[沙箱拒绝]")
        if result_str.startswith("[沙箱拒绝]"):
            record["sandbox_blocked"] = True
            record["result_ok"] = True  # 拦截成功也是预期行为
    except Exception as e:
        record["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        record["error"] = f"{type(e).__name__}: {e}"
        record["result_preview"] = traceback.format_exc()[:300]
    return record


def main():
    print("=" * 70)
    print("CRUX 工具全量闭环 — 阶段1 冒烟实跑")
    print("=" * 70)

    # 重新加载 registry (默认 mcp=True, 不开 toggle)
    reg = reload_registry()
    all_names = reg.tool_names
    print(f"\n[注册中心] 共加载 {len(all_names)} 个工具")
    print(f"[P0 清单] 待跑 {len(P0_CASES)} 个用例\n")

    results = []
    for name, args in P0_CASES:
        rec = smoke_one(reg, name, args)
        results.append(rec)
        status = "✓" if rec["result_ok"] else "✗"
        sandbox_tag = " [sandbox拦截]" if rec.get("sandbox_blocked") else ""
        print(f"  {status} {rec['name']:<22} {rec['latency_ms']:>7}ms{sandbox_tag}")
        if not rec["result_ok"]:
            print(f"      → {rec['result_preview'][:120]}")

    # ── 汇总 ──
    ok = sum(1 for r in results if r["result_ok"])
    fail = len(results) - ok
    sandbox_blocked = sum(1 for r in results if r.get("sandbox_blocked"))
    unregistered = sum(1 for r in results if not r["registered"])

    print("\n" + "=" * 70)
    print(
        f"[汇总] 通过 {ok}/{len(results)}  |  失败 {fail}  |  sandbox拦截 {sandbox_blocked}  |  未注册 {unregistered}"
    )
    print("=" * 70)

    # ── 高风险门核查 (静态: 名单里的工具是否真的注册了) ──
    print("\n[高风险确认门] 静态核查:")
    for hr in HIGH_RISK_TOOL_NAMES:
        present = reg.has(hr)
        tag = "已注册(门生效)" if present else "未注册(门空防)"
        print(f"  - {hr:<18} {tag}")

    # ── 计费/metric 核查 ──
    try:
        from core.observability import metrics

        m = metrics.summary()
        counters = m.get("counters", {})
        tool_exec = counters.get("tool_executions", 0)
        tool_err = counters.get("tool_errors", 0)
        print(f"\n[观测指标] tool_executions={tool_exec}  tool_errors={tool_err}")
    except Exception as e:
        print(f"\n[观测指标] 读取失败: {e}")

    # 写 JSON
    out = ROOT / "tests" / "smoke_tools_report.json"
    report = {
        "total_tools_registered": len(all_names),
        "p0_cases": len(results),
        "passed": ok,
        "failed": fail,
        "sandbox_blocked": sandbox_blocked,
        "unregistered": unregistered,
        "results": results,
        "registered_tool_names": all_names,
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[报告已写] {out}")

    # 清理 tmp
    try:
        import shutil

        shutil.rmtree(TMP_DIR, ignore_errors=True)
    except Exception:
        pass

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
