"""
batch_pack.py — 批量从真实 workflow 挖掘并打包蓝图

用法：
  python scripts/batch_pack.py
  python scripts/batch_pack.py --input ./raw_workflows --output ./blueprints --report ./report.json
  python scripts/batch_pack.py --miner-only  # 仅从真实文件挖矿，不用 compiler 生成
"""

from __future__ import annotations

import argparse, json, os, sys, hashlib, datetime
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from comfyflow_compiler.blueprint.packer import BlueprintPacker
from comfyflow_compiler.blueprint.loader import BlueprintLoader
from comfyflow_compiler.blueprint.validator import BlueprintValidator
from comfyflow_compiler.blueprint.normalizer import WorkflowNormalizer
from comfyflow_compiler.compiler import ComfyFlowCompiler


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def extract_workflow(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        return None
    if not isinstance(data, dict):
        return None
    prompt = data.get("prompt", data)
    if not isinstance(prompt, dict):
        return None
    has_ct = any(isinstance(v, dict) and "class_type" in v for v in prompt.values())
    return prompt if has_ct else None


def classify(prompt: dict) -> dict:
    cts = [v["class_type"] for v in prompt.values() if isinstance(v, dict) and "class_type" in v]
    ct_set = set(cts)
    return {
        "task_type": ("i2v" if any("LoadImage" in ct for ct in ct_set) else "t2v") if any(x in ct_set for x in ("VHS_VideoCombine","LTXVideoSampler")) else "img2img" if "LoadImage" in ct_set else "txt2img" if "SaveImage" in ct_set else "general",
        "node_count": len(cts),
        "signature": "+".join(sorted(ct_set)),
    }


# ── 意图（用于 compiler 补充覆盖）──

INTENTS = [
    ("txt2img_cat", "a cat astronaut in space"),
    ("txt2img_portrait", "cinematic portrait of a warrior"),
    ("txt2img_cyberpunk", "cyberpunk city at night, neon lights"),
    ("txt2img_anime", "anime girl with blue hair"),
    ("txt2img_landscape", "mountain landscape at sunset, photorealistic"),
    ("img2img_style", "turn this photo into anime style"),
    ("txt2img_flux", "a photorealistic tiger in the snow, detailed fur, flux"),
    ("t2v_dog", "a dog running on the beach, video"),
    ("t2v_ocean", "waves crashing on rocks, cinematic video"),
    ("i2v_from_image", "turn this picture into a video"),
]


def run(input_dirs: list[str] | None = None,
        output_dir: str = "comfyflow_compiler/blueprints",
        report_path: str = "",
        miner_only: bool = False) -> dict:
    """批量打包主流程"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    packer = BlueprintPacker()
    validator = BlueprintValidator()
    compiler = ComfyFlowCompiler() if not miner_only else None

    report = {
        "generated_at": _now(),
        "sources": {"mined": [], "compiled": []},
        "results": [],
        "summary": {},
        "stats": {},
    }

    seen = set()

    # Step 1: 从真实 workflow 文件挖矿
    if input_dirs:
        import glob as g
        files = []
        for d in input_dirs:
            files.extend(g.glob(f"{d}/**/*.json", recursive=True))
    else:
        import glob as g
        files = sorted(g.glob("output/workflows/*.json"))

    mined_count = 0
    for f in files:
        prompt = extract_workflow(f)
        if prompt is None:
            continue
        cls = classify(prompt)
        if cls["signature"] in seen:
            continue
        seen.add(cls["signature"])

        bp_id = f"mined_{cls['task_type']}_{cls['node_count']}nodes_{_file_hash(f)}"
        bp = packer.pack(prompt, bp_id, name=f"Mined {cls['task_type']}", tags=[cls["task_type"], "mined"])
        bp["source"]["origin"] = "mined"
        bp["source"]["workflow_id"] = os.path.basename(f)
        packer.save(bp, str(out))
        mined_count += 1
        report["sources"]["mined"].append({
            "file": f, "id": bp_id, "task": cls["task_type"], "nodes": cls["node_count"],
        })

    # Step 2: 用 compiler 生成多样化工作流
    compiled_count = 0
    if compiler:
        for bp_suffix, intent in INTENTS:
            try:
                result = compiler.compile(intent)
                if result.success and result.workflow_json:
                    prompt = result.workflow_json.get("prompt", result.workflow_json)
                    if isinstance(prompt, dict) and any(isinstance(v, dict) and "class_type" in v for v in prompt.values()):
                        cls = classify(prompt)
                        if cls["signature"] not in seen:
                            seen.add(cls["signature"])
                            bp_id = f"compiled_{bp_suffix}"
                            bp = packer.pack(prompt, bp_id, name=intent[:50], tags=[cls["task_type"], "compiled"])
                            bp["source"]["origin"] = "generated"
                            packer.save(bp, str(out))
                            compiled_count += 1
                            report["sources"]["compiled"].append({
                                "intent": intent[:60], "id": bp_id, "task": cls["task_type"], "nodes": cls["node_count"],
                            })
            except:
                pass

    # Step 3: 校验
    loader = BlueprintLoader(str(out))
    all_bp = loader.load_all()
    valid = 0
    for bp in all_bp:
        issues = validator.validate(bp)
        if len(issues) == 0:
            valid += 1
            report["results"].append({"id": bp["id"], "valid": True,
                "task": bp.get("capability",{}).get("task_type","?"),
                "nodes": bp.get("metadata",{}).get("total_nodes",0),
                "source": bp.get("source",{}).get("origin","?"),
            })
        else:
            report["results"].append({"id": bp.get("id","?"), "valid": False, "issues": issues})

    by_task = defaultdict(list)
    by_origin = defaultdict(int)
    for r in report["results"]:
        if r["valid"]:
            by_task[r.get("task","unknown")].append(r["id"])
            by_origin[r.get("source","?")] += 1

    report["summary"] = {
        "total": len(all_bp), "valid": valid, "invalid": len(all_bp) - valid,
        "mined_new": mined_count, "compiled_new": compiled_count,
        "by_task": {k: len(v) for k, v in sorted(by_task.items())},
        "by_origin": dict(by_origin),
    }

    # 统计
    report["stats"] = {
        "schema_pass_rate": f"{valid}/{len(all_bp)}" if all_bp else "0/0",
        "unique_task_types": list(by_task.keys()),
        "avg_nodes_per_blueprint": round(sum(r.get("nodes",0) for r in report["results"] if r["valid"]) / max(valid, 1), 1),
    }

    if report_path:
        rp = Path(report_path)
        rp.parent.mkdir(parents=True, exist_ok=True)
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  报告: {rp}")

    # 打印摘要
    s = report["summary"]
    print(f"\n{'='*50}")
    print(f"  Batch Pack Report")
    print(f"{'='*50}")
    print(f"  总蓝图: {s['total']} | 有效: {s['valid']} | 无效: {s['invalid']}")
    print(f"  新增挖掘: {s['mined_new']} | 编译器生成: {s['compiled_new']}")
    print(f"  Schema 通过率: {report['stats']['schema_pass_rate']}")
    print(f"  平均节点数: {report['stats']['avg_nodes_per_blueprint']}")
    for t, c in sorted(s["by_task"].items()):
        print(f"    {t}: {c}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ComfyFlow Blueprint Batch Packer")
    parser.add_argument("--input", nargs="*", default=None, help="工作流文件/目录")
    parser.add_argument("--output", default="comfyflow_compiler/blueprints", help="蓝图输出目录")
    parser.add_argument("--report", default="", help="报告 JSON 路径")
    parser.add_argument("--miner-only", action="store_true", help="仅从文件挖矿，不用 compiler")
    args = parser.parse_args()

    run(
        input_dirs=args.input,
        output_dir=args.output,
        report_path=args.report,
        miner_only=args.miner_only,
    )
