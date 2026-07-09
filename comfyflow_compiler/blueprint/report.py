"""Blueprint Coverage Report — 蓝图覆盖度检测"""

from __future__ import annotations

import json
from pathlib import Path
from collections import defaultdict
from typing import Optional


# 期望的覆盖矩阵
TARGET_COVERAGE = {
    "txt2img": 5,
    "img2img": 4,
    "i2v": 2,
    "t2v": 1,
    "general": 2,
}

TARGET_TOTAL = 24

# 已知缺失 — 有计划但在后续版本实现
KNOWN_GAPS = {}

# 认可的来源类型
VALID_ORIGINS = {"mined", "generated", "handcrafted", "community"}


def scan_blueprints(blueprints_dir: str | Path = "comfyflow_compiler/blueprints") -> dict:
    """扫描蓝图目录，生成覆盖报告"""
    bp_dir = Path(blueprints_dir)
    if not bp_dir.exists():
        return {"error": f"目录不存在: {bp_dir}"}

    blueprints = []
    by_task = defaultdict(list)
    by_origin = defaultdict(int)
    validation_issues = []

    for f in sorted(bp_dir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                bp = json.load(fp)
        except Exception as e:
            validation_issues.append({"file": f.name, "issue": f"无法解析: {e}"})
            continue

        if not isinstance(bp, dict) or "id" not in bp:
            validation_issues.append({"file": f.name, "issue": "缺少 id 字段"})
            continue

        bid = bp.get("id", f.stem)
        task = bp.get("capability", {}).get("task_type", "unknown")
        origin = bp.get("source", {}).get("origin", "unknown")
        status = bp.get("status", "unknown")
        nodes = bp.get("metadata", {}).get("total_nodes", 0)
        slots = len(bp.get("slots", {}))
        source_wf = bp.get("source", {}).get("workflow_id", "")

        entry = {
            "id": bid,
            "file": f.name,
            "task_type": task,
            "origin": origin,
            "status": status,
            "nodes": nodes,
            "slots": slots,
            "source_workflow": source_wf,
        }
        blueprints.append(entry)
        by_task[task].append(entry)
        by_origin[origin] += 1

    # 计算覆盖缺口
    coverage_gaps = []
    for task, target in TARGET_COVERAGE.items():
        actual = len(by_task.get(task, []))
        if actual < target:
            coverage_gaps.append({
                "task_type": task,
                "current": actual,
                "target": target,
                "gap": target - actual,
            })

    # 缺失类型
    covered_tasks = set(by_task.keys())
    all_expected = set(TARGET_COVERAGE.keys())
    missing_tasks = sorted(all_expected - covered_tasks)

    report = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "total_blueprints": len(blueprints),
        "target_total": TARGET_TOTAL,
        "valid": len(blueprints),
        "invalid": len(validation_issues),
        "by_task": {k: len(v) for k, v in sorted(by_task.items())},
        "by_origin": dict(by_origin),
        "coverage": {
            "targets": TARGET_COVERAGE,
            "gaps": coverage_gaps,
            "missing_tasks": missing_tasks,
            "met_target": len(coverage_gaps) == 0 and len(missing_tasks) == 0,
        },
        "validation_issues": validation_issues,
        "blueprints": sorted(blueprints, key=lambda x: (x["task_type"], x["id"])),
    }

    return report


def print_report(report: dict) -> None:
    """打印可读的报告"""
    print("=" * 60)
    print("  Blueprint Coverage Report")
    print("=" * 60)

    if "error" in report:
        print(f"  ❌ {report['error']}")
        return

    print(f"\n  Total: {report['total_blueprints']} blueprints (target: {report.get('target_total', 22)})")
    print(f"  Valid: {report['valid']} / Invalid: {report['invalid']}")

    print(f"\n  --- By Task ---")
    for task, count in sorted(report["by_task"].items()):
        target = TARGET_COVERAGE.get(task, "-")
        status = "✅" if count >= (TARGET_COVERAGE.get(task, 0)) else "⚠️"
        print(f"    {task:12s}: {count:2d} (target: {target}) {status}")

    if report["coverage"]["missing_tasks"]:
        print(f"\n  ❌ Missing task types: {', '.join(report['coverage']['missing_tasks'])}")
        for t in report["coverage"]["missing_tasks"]:
            note = KNOWN_GAPS.get(t, "未知")
            if note:
                print(f"       {t}: {note}")

    if report["coverage"]["gaps"]:
        print(f"\n  ⚠️  Coverage gaps:")
        for g in report["coverage"]["gaps"]:
            print(f"    {g['task_type']:12s}: {g['current']}/{g['target']} (-{g['gap']})")

    print(f"\n  --- By Origin ---")
    for origin, count in sorted(report["by_origin"].items()):
        print(f"    {origin:12s}: {count}")

    if report["coverage"]["met_target"]:
        print(f"\n  ✅ All coverage targets met!")
    else:
        print(f"\n  ❌ Coverage targets NOT met")

    print(f"\n  --- Blueprint Detail ---")
    for bp in report["blueprints"][:25]:  # limit display
        flag = "✅" if bp["status"] != "deprecated" else "⚠️"
        print(f"    {flag} {bp['id']:40s} {bp['task_type']:8s} {bp['origin']:12s} {bp['nodes']:2d}n {bp['slots']}s")
    if len(report["blueprints"]) > 25:
        print(f"    ... and {len(report['blueprints']) - 25} more")

    print("=" * 60)


if __name__ == "__main__":
    report = scan_blueprints()
    print_report(report)
