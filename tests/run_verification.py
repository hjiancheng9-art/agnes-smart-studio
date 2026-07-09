"""
ComfyFlow Compiler v0.8 — 真实 ComfyUI 执行验证

遍历所有蓝图 → 编译 → 提交 /prompt → 检查执行结果
"""

from __future__ import annotations
import sys
import os
import json
import time
import urllib.request
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from comfyflow_compiler import ComfyFlowCompiler, BlueprintMiner, BlueprintPacker
from comfyflow_compiler.blueprint_registry import BlueprintRequirement
from comfyflow_compiler.api_client import ComfyAPIClient


def check_comfyui_health(url="http://127.0.0.1:8188") -> bool:
    """检查 ComfyUI 是否存活"""
    try:
        resp = urllib.request.urlopen(f"{url}/", timeout=5)
        return resp.status == 200
    except Exception:
        return False


def get_object_info(url="http://127.0.0.1:8188") -> dict:
    """获取 ComfyUI 所有可用节点定义"""
    try:
        resp = urllib.request.urlopen(f"{url}/object_info", timeout=15)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ❌ 获取 object_info 失败: {e}")
        return {}


def get_models(url="http://127.0.0.1:8188") -> list:
    """获取 ComfyUI 可用模型"""
    try:
        resp = urllib.request.urlopen(f"{url}/models/checkpoints", timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []


def compile_and_submit(compiler, prompt_text: str, api_url: str, timeout: int = 60) -> dict:
    """编译需求 → 提交 /prompt → 等待完成 → 返回结果"""
    # 编译
    r = compiler.compile_with_fallback(prompt_text)
    if not r.success or not r.workflow_json:
        return {"status": "compile_failed", "error": r.error, "blueprint": r.blueprint_used}
    
    # 提取 workflow
    workflow = r.workflow_json.get("prompt", r.workflow_json)
    
    # 提交
    client = ComfyAPIClient(api_url)
    prompt_id = str(uuid.uuid4())
    
    try:
        actual_id = client.queue_prompt(workflow, prompt_id=prompt_id)
    except Exception as e:
        return {"status": "submit_failed", "error": str(e), "blueprint": r.blueprint_used, "workflow": workflow}
    
    # 等待执行
    try:
        progress = client.wait_for_completion(actual_id, timeout=timeout)
        return {
            "status": "done" if progress.status == "done" else progress.status,
            "prompt_id": actual_id,
            "node_count": len(workflow),
            "blueprint": r.blueprint_used,
            "executed_nodes": len(progress.executed_nodes),
            "output_images": progress.output_images,
            "error": progress.error,
        }
    except Exception as e:
        return {"status": "execution_error", "error": str(e), "blueprint": r.blueprint_used, "prompt_id": actual_id}


def main():
    api_url = "http://127.0.0.1:8188"
    
    print("╔══════════════════════════════════════════════════╗")
    print("║  ComfyFlow Compiler v0.8 — 真实执行验证         ║")
    print("╚══════════════════════════════════════════════════╝")
    
    # 1. 健康检查
    print(f"\n🔍 1. ComfyUI 健康检查...")
    if not check_comfyui_health(api_url):
        print("   ❌ ComfyUI 未运行")
        return
    print("   ✅ ComfyUI 运行中")
    
    # 2. 获取节点信息
    print(f"\n🔍 2. 获取运行时节点信息...")
    obj_info = get_object_info(api_url)
    available_nodes = set(obj_info.keys())
    print(f"   ComfyUI 可用节点数: {len(available_nodes)}")
    
    # 3. 获取模型列表
    print(f"\n🔍 3. 获取可用模型...")
    models = get_models(api_url)
    print(f"   可用检查点: {len(models)}")
    for m in models[:5]:
        print(f"     - {m}")
    
    # 4. 初始化 Compiler
    print(f"\n🔍 4. 初始化 Compiler...")
    comfyui_path = r"D:\ComfyUI_windows_portable\ComfyUI"
    compiler = ComfyFlowCompiler(comfyui_path=comfyui_path)
    
    # 加载生产蓝图
    paths = [
        r"C:\Users\huangjiancheng\Desktop\【B站：黎黎原上咩】工作流集",
        r"C:\Users\huangjiancheng\Desktop\高尚工作流",
        r"C:\Users\huangjiancheng\Desktop\手搓工作流(1)",
    ]
    miner = BlueprintMiner()
    miner.scan(paths)
    mined = miner.mine_blueprints(min_workflows=1, min_confidence=0.1)
    packer = BlueprintPacker()
    packed = packer.pack_all(mined, min_confidence=0.15)
    for bp in packed:
        if bp.name not in compiler.registry.blueprints:
            compiler.registry.blueprints[bp.name] = bp
            compiler.registry.requirements[bp.name] = BlueprintRequirement(
                blueprint_name=bp.name, min_vram_gb=6.0, min_budget_score=3.0,
                quality_weight=max(0.5, bp.quality_score),
            )
    
    print(f"   Compiler 蓝图: {len(compiler.registry.blueprints)} 个")
    
    # 5. 编译 + 执行测试
    print(f"\n🔍 5. 执行验证...")
    
    test_cases = [
        ("基础文生图", "生成一张猫的照片"),
        ("高清文生图", "生成一张猫的照片，高清"),
        ("快速文生图", "生成一张猫的照片，快速"),
        ("电影感图", "生成一张电影感赛博朋克猫，霓虹雨夜，9:16"),
        ("二次元", "画一个二次元少女，清新风格，竖屏"),
        ("图生图", "重绘这张图，变成油画风格"),
    ]
    
    results = []
    
    for label, prompt in test_cases:
        print(f"\n   📝 [{label}] {prompt[:30]}...")
        
        # 先只编译检查拓扑
        r = compiler.compile_with_fallback(prompt)
        if r.success and r.workflow_json:
            workflow = r.workflow_json.get("prompt", r.workflow_json)
            
            # 检查所有节点是否在 ComfyUI 中可用
            workflow_types = {n["class_type"] for n in workflow.values()}
            missing = workflow_types - available_nodes
            node_count = len(workflow)
            
            if missing:
                print(f"     ❌ 缺少 {len(missing)} 个节点: {', '.join(list(missing)[:5])}")
                results.append({"label": label, "status": "missing_nodes", "missing": list(missing)})
            else:
                # 提交执行
                result = compile_and_submit(compiler, prompt, api_url, timeout=45)
                results.append({"label": label, **result})
                
                if result["status"] == "done":
                    imgs = result.get("output_images", [])
                    print(f"     ✅ 执行成功! {result['node_count']}节点, {len(imgs)}张输出")
                    for img in imgs[:2]:
                        print(f"       🖼️  {img}")
                elif result["status"] == "compile_failed":
                    print(f"     ❌ 编译失败: {result.get('error', '')[:60]}")
                elif result["status"] == "submit_failed":
                    print(f"     ❌ 提交失败: {result.get('error', '')[:60]}")
                elif result["status"] == "execution_error":
                    print(f"     ❌ 执行异常: {result.get('error', '')[:60]}")
                else:
                    print(f"     ⏳ 状态: {result['status']}")
        else:
            print(f"     ❌ 编译失败: {r.error[:60] if r.error else '?'}")
            results.append({"label": label, "status": "compile_failed", "error": r.error})
    
    # 6. 报告
    print(f"\n{'='*50}")
    print(f"📊 验证报告")
    print(f"{'='*50}")
    
    passed = sum(1 for r in results if r.get("status") == "done")
    failed_compile = sum(1 for r in results if r.get("status") == "compile_failed")
    failed_submit = sum(1 for r in results if r.get("status") == "submit_failed")
    failed_exec = sum(1 for r in results if r.get("status") == "execution_error")
    missing_nodes = sum(1 for r in results if r.get("status") == "missing_nodes")
    
    print(f"   总测试: {len(results)}")
    print(f"   执行成功: {passed} ✅")
    print(f"   编译失败: {failed_compile} ❌")
    print(f"   提交失败: {failed_submit} ❌")
    print(f"   执行异常: {failed_exec} ❌")
    print(f"   节点缺失: {missing_nodes} ⚠️")
    
    print(f"\n📋 逐项结果:")
    for r in results:
        status_icon = {"done": "✅", "compile_failed": "❌", "submit_failed": "❌", 
                       "execution_error": "❌", "missing_nodes": "⚠️"}.get(r.get("status", ""), "❓")
        print(f"   {status_icon} {r['label']:12s} | {r.get('blueprint','')[:25]:25s} | {r.get('status','')}")


if __name__ == "__main__":
    main()
