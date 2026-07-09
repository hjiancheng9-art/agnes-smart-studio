#!/usr/bin/env python3
"""ComfyFlow Compiler — CLI 入口

用法:
  comfyflow probe                   探测 ComfyUI 环境
  comfyflow list-blueprints         列出可用蓝图
  comfyflow match "prompt"          匹配最佳蓝图
  comfyflow compile "prompt"        编译为 workflow JSON
  comfyflow run "prompt"            编译 + 执行
  comfyflow pack input.json         打包 workflow 为蓝图
  comfyflow report                  覆盖报告
  comfyflow version                 版本信息
"""

import sys
import json
import os
from pathlib import Path

# 确保能加载项目模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comfyflow_compiler import __version__ as VERSION
from comfyflow_compiler.compiler import ComfyFlowCompiler
from comfyflow_compiler.blueprint.report import scan_blueprints, print_report
from comfyflow_compiler.blueprint.loader import BlueprintLoader
from comfyflow_compiler.capability.snapshot import probe_comfyui
from comfyflow_compiler.capability.compatibility import BlueprintCompatibilityMatcher


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "probe": cmd_probe,
        "list-blueprints": cmd_list_blueprints,
        "match": cmd_match,
        "compile": cmd_compile,
        "run": cmd_run,
        "pack": cmd_pack,
        "report": cmd_report,
        "version": cmd_version,
    }

    if cmd in commands:
        commands[cmd](args)
    else:
        print(f"未知命令: {cmd}\n")
        print(__doc__.strip())
        sys.exit(1)


def cmd_probe(args):
    """探测 ComfyUI 环境"""
    url = args[0] if args else "http://127.0.0.1:8188"
    print(f"🔍 探测 ComfyUI: {url}")
    snap = probe_comfyui(url)
    s = snap.summary
    print(f"\n  在线:     {'✅' if s['comfyui_online'] else '❌'}")
    print(f"  版本:     {s['version']}")
    print(f"  节点:     {s['nodes']}")
    print(f"  模型:     {s['models']}")
    print(f"  采集时间: {s['generated_at']}")
    print(f"  兼容问题: {s['issues']}")


def cmd_list_blueprints(args):
    """列出蓝图"""
    loader = BlueprintLoader()
    all_bp = loader.load_all()
    print(f"📋 共 {len(all_bp)} 个蓝图:\n")
    for bp in sorted(all_bp, key=lambda x: x.get("capability", {}).get("task_type", "")):
        cap = bp.get("capability", {})
        task = cap.get("task_type", "?")
        name = bp.get("id", "?")
        nodes = bp.get("metadata", {}).get("total_nodes", 0)
        status = bp.get("status", "?")
        icon = {"stable": "✅", "beta": "🔶", "deprecated": "⚠️"}.get(status, "🔷")
        print(f"  {icon} {name:40s} {task:8s} {nodes:2d} nodes  [{status}]")


def cmd_match(args):
    """匹配蓝图"""
    if not args:
        print("用法: comfyflow match <prompt>")
        return
    prompt = " ".join(args)
    print(f"🎯 匹配: {prompt}\n")

    snap = probe_comfyui()
    if not snap.comfyui_online:
        print("  ⚠️ ComfyUI 离线，仅做蓝图匹配（无环境校验）")

    compiler = ComfyFlowCompiler()
    from comfyflow_compiler.intent_parser import parse_intent
    task = parse_intent(prompt)
    print(f"  意图: task_type={task.task_type}, style={task.style}")

    recipes = compiler.registry.match_recipe(task.task_type, task.style, task.subject)
    if recipes:
        for r in recipes[:3]:
            print(f"  配方: {r.name} → {r.preferred_blueprints[:3]}")
    else:
        print("  配方: 无匹配")

    if snap.comfyui_online:
        matcher = BlueprintCompatibilityMatcher(snap)
        loader = BlueprintLoader()
        all_bp = loader.load_all()
        scored = matcher.rank(all_bp)
        compatible = [s for s in scored if s.compatible and s.task_type == task.task_type]
        if compatible:
            print(f"\n  最佳兼容: {compatible[0].blueprint_id} (score={compatible[0].overall:.2f})")
        else:
            print(f"\n  无兼容蓝图")


def cmd_compile(args):
    """编译"""
    if not args:
        print("用法: comfyflow compile <prompt>")
        return
    prompt = " ".join(args)
    compiler = ComfyFlowCompiler()
    result = compiler.compile(prompt)
    if result.success:
        print(f"✅ 编译成功")
        print(f"  蓝图: {result.blueprint_used}")
        print(f"  硬件: {result.hardware_used}")
        print(f"  摘要: {result.user_summary}")
        if result.workflow_json:
            wf = result.workflow_json.get("prompt", result.workflow_json)
            cts = [v.get("class_type","") for v in wf.values() if isinstance(v, dict)]
            print(f"  节点: {len(cts)} ({', '.join(cts[:6])}{'...' if len(cts)>6 else ''})")
    else:
        print(f"❌ 编译失败: {result.error}")


def cmd_run(args):
    """编译 + 执行"""
    if not args:
        print("用法: comfyflow run <prompt>")
        return
    prompt = " ".join(args)

    # 编译
    compiler = ComfyFlowCompiler()
    comp_result = compiler.compile(prompt)
    if not comp_result.success:
        print(f"❌ 编译失败: {comp_result.error}")
        return

    print(f"✅ 编译成功: {comp_result.blueprint_used}")

    # 执行
    from comfyflow_compiler.execution import ExecutionOrchestrator
    orch = ExecutionOrchestrator()
    print(f"🚀 提交到 ComfyUI...")
    exec_result = orch.execute(
        comp_result.workflow_json or {},
        task_type="",
        blueprint_used=comp_result.blueprint_used,
    )
    print(f"\n{exec_result.summary}")
    if exec_result.output:
        for f in exec_result.output.files:
            print(f"  📁 {f.full_path or f.filename} ({f.type})")


def cmd_pack(args):
    """打包 workflow"""
    if not args:
        print("用法: comfyflow pack <workflow.json> [blueprint_id]")
        return
    path = args[0]
    bp_id = args[1] if len(args) > 1 else Path(path).stem
    from comfyflow_compiler.blueprint.packer import BlueprintPacker
    packer = BlueprintPacker()
    bp = packer.pack_from_file(path, bp_id)
    output = Path("comfyflow_compiler/blueprints") / f"{bp_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(bp, f, indent=2, ensure_ascii=False)
    print(f"✅ 已打包: {output}")
    print(f"  ID: {bp['id']}")
    print(f"  节点: {len(bp['graph_template']['nodes'])}")
    print(f"  槽位: {len(bp.get('slots', {}))}")


def cmd_report(args):
    """覆盖报告"""
    bp_dir = args[0] if args else "comfyflow_compiler/blueprints"
    report = scan_blueprints(bp_dir)
    if "--json" in args:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_report(report)


def cmd_version(args):
    """版本"""
    print(f"ComfyFlow Compiler v{VERSION}")


if __name__ == "__main__":
    main()
