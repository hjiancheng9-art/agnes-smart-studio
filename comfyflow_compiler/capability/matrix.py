"""Blueprint × Capability Matrix — 蓝图在真实环境中的可运行性矩阵

检查每个蓝图在当前 ComfyUI 环境下的节点和模型可用性。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comfyflow_compiler.blueprint.loader import BlueprintLoader
from comfyflow_compiler.capability.snapshot import probe_comfyui
from comfyflow_compiler.capability.compatibility import BlueprintCompatibilityMatcher


@dataclass
class MatrixEntry:
    blueprint_id: str
    task_type: str
    status: str
    compatible: bool
    score: float
    missing_nodes: list[str] = field(default_factory=list)
    missing_models: list[str] = field(default_factory=list)
    vram_issue: str = ""


def build_matrix(blueprints_dir: str = "comfyflow_compiler/blueprints",
                 comfyui_url: str = "http://127.0.0.1:8188") -> dict:
    """构建蓝图 × 能力矩阵"""
    loader = BlueprintLoader(blueprints_dir)
    all_bp = loader.load_all()

    snap = probe_comfyui(comfyui_url)
    online = snap.comfyui_online

    if not online:
        return {
            "comfyui_online": False,
            "message": "ComfyUI 离线 — 无法构建真实矩阵",
            "total_blueprints": len(all_bp),
        }

    matcher = BlueprintCompatibilityMatcher(snap)
    scored = matcher.rank(all_bp)

    entries = []
    by_task = {}
    compatible_count = 0

    for s in scored:
        entry = {
            "blueprint_id": s.blueprint_id,
            "task_type": s.task_type,
            "compatible": s.compatible,
            "score": round(s.overall, 2),
            "node_score": round(s.node_score, 2),
            "model_score": round(s.model_score, 2),
            "vram_score": round(s.vram_score, 2),
            "missing_nodes": s.missing_nodes,
            "missing_models": s.missing_models,
            "vram_issue": s.vram_issue,
        }
        entries.append(entry)

        if s.compatible:
            compatible_count += 1

        task = s.task_type or "unknown"
        if task not in by_task:
            by_task[task] = {"total": 0, "compatible": 0}
        by_task[task]["total"] += 1
        if s.compatible:
            by_task[task]["compatible"] += 1

    return {
        "comfyui_online": True,
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "total_blueprints": len(entries),
        "compatible_count": compatible_count,
        "compatibility_rate": f"{compatible_count}/{len(entries)}",
        "compatibility_pct": round(compatible_count / max(len(entries), 1) * 100, 1),
        "by_task": by_task,
        "matrix": entries,
    }


def print_matrix(matrix: dict):
    """打印矩阵报告"""
    print(f"\n{'='*60}")
    print(f"  Blueprint × Capability Matrix")
    print(f"{'='*60}")

    if not matrix.get("comfyui_online"):
        print(f"\n  ⚠️  {matrix.get('message', 'ComfyUI 离线')}")
        return

    print(f"\n  ComfyUI: ✅ online")
    print(f"  Timestamp: {matrix['timestamp']}")
    print(f"\n  Summary:")
    print(f"    Total blueprints:  {matrix['total_blueprints']}")
    print(f"    Compatible:        {matrix['compatible_count']} ({matrix['compatibility_pct']}%)")
    print(f"    Incompatible:      {matrix['total_blueprints'] - matrix['compatible_count']}")

    print(f"\n  {'─'*60}")
    print(f"  {'Status':^8} {'Score':>6}  {'Blueprint':<40}")
    print(f"  {'─'*60}")

    for entry in matrix["matrix"]:
        icon = "✅" if entry["compatible"] else "⚠️"
        issues = []
        if entry["missing_nodes"]:
            issues.append(f"missing {len(entry['missing_nodes'])} nodes")
        if entry["missing_models"]:
            issues.append(f"missing {len(entry['missing_models'])} models")
        detail = f" — {', '.join(issues)}" if issues else ""
        print(f"  {icon:^8} {entry['score']:>5.2f}  {entry['blueprint_id']:<40}{detail}")

    print(f"\n  By Task:")
    for task, stats in sorted(matrix["by_task"].items()):
        pct = round(stats["compatible"] / max(stats["total"], 1) * 100)
        print(f"    {task:12s}: {stats['compatible']}/{stats['total']} compatible ({pct}%)")

    print(f"{'='*60}")


if __name__ == "__main__":
    matrix = build_matrix()
    print_matrix(matrix)

    if "--json" in sys.argv:
        with open("output/capability_matrix.json", "w", encoding="utf-8") as f:
            json.dump(matrix, f, indent=2, ensure_ascii=False)
        print(f"\n  Matrix saved: output/capability_matrix.json")
