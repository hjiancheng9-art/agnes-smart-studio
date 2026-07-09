"""
batch_pack.py — 批量从真实 workflow 挖掘并打包蓝图

三步走：
1. 从 output/workflows/*.json 提取真实 workfkow（去重）
2. 用 compiler 从意图生成多样 workflow（补充覆盖面）
3. 全部 pack → 校验 → 出报告
"""

from __future__ import annotations

import json, os, sys, hashlib, datetime
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

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


def extract_workflow_from_file(path: str) -> dict | None:
    """从文件提取干净的工作流 prompt"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        return None

    if not isinstance(data, dict):
        return None

    # {"prompt": {...}} 格式
    prompt = data.get("prompt", data)
    if not isinstance(prompt, dict):
        return None

    # 检查是否有 class_type
    has_ct = any(isinstance(v, dict) and "class_type" in v for v in prompt.values())
    if not has_ct:
        return None

    return prompt


def classify_workflow(prompt: dict) -> dict:
    """分类工作流：task_type, 节点数, 特征"""
    nodes = []
    cts = []
    for nid, nd in prompt.items():
        if isinstance(nd, dict) and "class_type" in nd:
            nodes.append({"id": nid, "class_type": nd["class_type"]})
            cts.append(nd["class_type"])

    ct_set = set(cts)
    has_video = "VHS_VideoCombine" in ct_set
    has_save_img = "SaveImage" in ct_set
    has_load_img = "LoadImage" in ct_set
    has_load_vid = "LoadVideo" in ct_set
    has_flux = "DualCLIPLoader" in ct_set or "UNETLoader" in ct_set
    has_ltx = any("LTX" in ct for ct in ct_set)
    has_ksampler = "KSampler" in ct_set or "SamplerCustomAdvanced" in ct_set

    if has_video or has_ltx:
        task_type = "i2v" if (has_load_img or has_load_vid) else "t2v"
    elif has_load_img and has_save_img:
        task_type = "img2img"
    elif has_save_img:
        task_type = "txt2img"
    elif has_load_img:
        task_type = "img2img"
    else:
        task_type = "general"

    return {
        "task_type": task_type,
        "node_count": len(nodes),
        "class_types": ct_set,
        "has_flux": has_flux,
        "has_ltx": has_ltx,
    }


def generate_workflow_from_intent(compiler: ComfyFlowCompiler, intent: str) -> dict | None:
    """用 compiler 从意图生成工作流"""
    try:
        result = compiler.compile(intent)
        if result.success and result.workflow_json:
            prompt = result.workflow_json.get("prompt", result.workflow_json)
            if isinstance(prompt, dict) and any(
                isinstance(v, dict) and "class_type" in v for v in prompt.values()
            ):
                return prompt
    except Exception:
        pass
    return None


# ── 意图列表（覆盖 tx2img / img2img / i2v / t2v）──

INTENTS = [
    # txt2img
    ("txt2img_cat", "a cat astronaut in space"),
    ("txt2img_portrait", "cinematic portrait of a warrior"),
    ("txt2img_cyberpunk", "cyberpunk city at night, neon lights"),
    ("txt2img_anime", "anime girl with blue hair"),
    ("txt2img_landscape", "mountain landscape at sunset, photorealistic"),
    ("txt2img_product", "product shot of a perfume bottle"),
    ("txt2img_fantasy", "fantasy dragon flying over castle"),
    # img2img
    ("img2img_style", "turn this photo into anime style"),
    ("img2img_cyberpunk", "transform into cyberpunk style"),
    # flux
    ("flux_cat", "a photorealistic tiger in the snow, detailed fur, flux"),
    ("flux_portrait", "cinematic portrait of an elderly man, flux"),
    # video
    ("i2v_dog", "a dog running on the beach, make it a video"),
    ("t2v_ocean", "waves crashing on rocks, video"),
]


def run(output_dir: str = "comfyflow_compiler/blueprints") -> dict:
    """批量打包主流程"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    packer = BlueprintPacker()
    validator = BlueprintValidator()
    compiler = ComfyFlowCompiler()

    report = {
        "generated_at": _now(),
        "sources": {"real_workflows": [], "compiler_generated": [], "existing": []},
        "results": [],
        "summary": {},
    }

    # ── Step 1: 从真实 workfkow 文件提取 ──
    print("\n🟦 Step 1: 挖掘真实 workflow 文件...")
    seen_ct_signatures = set()
    real_counter = 0

    import glob as g
    for f in sorted(g.glob("output/workflows/*.json")):
        prompt = extract_workflow_from_file(f)
        if prompt is None:
            continue

        cls = classify_workflow(prompt)
        sig = "+".join(sorted(cls["class_types"]))
        if sig in seen_ct_signatures:
            continue
        seen_ct_signatures.add(sig)

        # 生成唯一 ID
        bp_id = f"mined_{cls['task_type']}_{cls['node_count']}nodes_{_file_hash(f)}"
        name = f"Mined {cls['task_type']} ({cls['node_count']} nodes)"

        bp = packer.pack(prompt, bp_id, name=name, tags=[cls["task_type"], "mined"])

        # 标记来源
        bp["source"]["origin"] = "mined"
        bp["source"]["workflow_id"] = os.path.basename(f)
        bp["source"]["author"] = "ComfyFlow Batch Packer"
        bp["metadata"]["changelog"] = [f"v1.0.0: Batch packed from {os.path.basename(f)}"]

        packer.save(bp, str(out))
        real_counter += 1
        print(f"   ✅ [{cls['task_type']}] {bp_id} ({cls['node_count']} nodes)")

        report["sources"]["real_workflows"].append({
            "file": f, "blueprint_id": bp_id, "task_type": cls["task_type"],
            "nodes": cls["node_count"],
        })

    # ── Step 2: 用 compiler 生成多样化工作流 ──
    print(f"\n🟦 Step 2: 用 compiler 生成 {len(INTENTS)} 个多样化工作流...")
    gen_counter = 0
    for bp_id_suffix, intent in INTENTS:
        prompt = generate_workflow_from_intent(compiler, intent)
        if prompt is None:
            print(f"   ⏭️  {bp_id_suffix}: compiler 未能生成有效 workflow")
            continue

        cls = classify_workflow(prompt)
        bp_id = f"compiled_{bp_id_suffix}"

        bp = packer.pack(prompt, bp_id, name=intent[:50], tags=[cls["task_type"], "compiled"])
        bp["source"]["origin"] = "generated"
        bp["source"]["workflow_id"] = intent[:60]
        bp["source"]["author"] = "ComfyFlow Compiler"
        bp["metadata"]["changelog"] = [f"v1.0.0: Generated from intent: {intent[:60]}"]

        packer.save(bp, str(out))
        gen_counter += 1
        print(f"   ✅ [{cls['task_type']}] {bp_id} ({cls['node_count']} nodes)")

        report["sources"]["compiler_generated"].append({
            "intent": intent[:60], "blueprint_id": bp_id,
            "task_type": cls["task_type"], "nodes": cls["node_count"],
        })

    # ── Step 3: 验证所有蓝图 ──
    print(f"\n🟦 Step 3: 校验所有蓝图...")
    loader = BlueprintLoader(str(out))
    all_bp = loader.load_all()
    valid_count = 0
    invalid_details = []

    for bp in all_bp:
        issues = validator.validate(bp)
        if len(issues) == 0:
            valid_count += 1
            report["results"].append({
                "id": bp.get("id", "?"),
                "valid": True,
                "task_type": bp.get("capability", {}).get("task_type", "?"),
                "nodes": bp.get("metadata", {}).get("total_nodes", 0),
                "source": bp.get("source", {}).get("origin", "?"),
            })
        else:
            invalid_details.append({"id": bp.get("id", "?"), "issues": issues})
            report["results"].append({
                "id": bp.get("id", "?"),
                "valid": False,
                "issues": issues,
            })

    # ── 统计 ──
    by_task = defaultdict(list)
    by_origin = defaultdict(int)
    for r in report["results"]:
        if r["valid"]:
            by_task[r.get("task_type", "unknown")].append(r["id"])
            by_origin[r.get("source", "?")] += 1

    report["summary"] = {
        "total_blueprints": len(all_bp),
        "valid": valid_count,
        "invalid": len(all_bp) - valid_count,
        "real_workflow_mined": real_counter,
        "compiler_generated": gen_counter,
        "by_task": {k: len(v) for k, v in sorted(by_task.items())},
        "by_origin": dict(by_origin),
        # 缺失分析
        "coverage_gaps": [],
    }

    # 缺失分析
    expected_tasks = {"txt2img", "img2img", "i2v", "t2v", "general"}
    covered_tasks = set(by_task.keys())
    missing_tasks = expected_tasks - covered_tasks
    if missing_tasks:
        report["summary"]["coverage_gaps"] = [f"缺少 {t}" for t in sorted(missing_tasks)]

    # ── 输出报告 ──
    report_path = out / "pack_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"  📊 批量打包完成")
    print(f"  {'='*50}")
    print(f"  总蓝图数:     {report['summary']['total_blueprints']}")
    print(f"  校验通过:     {report['summary']['valid']}")
    print(f"  校验失败:     {report['summary']['invalid']}")
    print(f"  ──────────────")
    print(f"  真实工作流:   {report['summary']['real_workflow_mined']}")
    print(f"  编译器生成:   {report['summary']['compiler_generated']}")
    print(f"  ──────────────")
    for task, count in sorted(report["summary"]["by_task"].items()):
        print(f"  {task:12s}: {count}")
    if report["summary"]["coverage_gaps"]:
        print(f"  ⚠️  缺失: {', '.join(report['summary']['coverage_gaps'])}")
    print(f"\n  报告: {report_path}")

    return report


if __name__ == "__main__":
    run()
