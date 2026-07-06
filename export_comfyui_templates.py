#!/usr/bin/env python3
"""自动扫描V2项目，导出全部ComfyUI工作流模板为JSON数组。

放到 V2 项目根目录运行：
    python export_comfyui_templates.py

输出: clean_templates.json (可直接导入MotifRegistry)
"""

import os, json, glob, re, sys
from pathlib import Path

OUTPUT_FILE = "clean_templates.json"

# 已知的模板/工作流数据目录
SCAN_DIRS = ["data", "knowledge", "schemas", "config", "public"]

# ComfyUI 节点类名特征
NODE_CLASS_PATTERN = re.compile(r'(CheckpointLoader|CLIPTextEncode|KSampler|VAEDecode|VAEEncode|'
                                 r'EmptyLatentImage|SaveImage|LoadImage|LoraLoader|'
                                 r'ControlNetLoader|UpscaleImage|VAELoader|CLIPLoader)')

# 已知的模板格式：包含 workflow_id + inputs + binding
def is_template_file(content: str) -> bool:
    """判断文件是否包含工作流模板。"""
    has_workflow_id = '"workflow_id"' in content or "'workflow_id'" in content or 'workflow_id:' in content
    has_inputs = '"inputs"' in content or "'inputs'" in content
    has_binding = '"binding"' in content or "'binding'" in content
    has_class_type = 'class_type' in content
    has_nodes = NODE_CLASS_PATTERN.search(content) is not None
    
    # 需要满足：有workflow_id + (inputs+binding 或 class_type)
    if has_workflow_id and (has_class_type or (has_inputs and has_binding)):
        return True
    return False


def scan_files(root_dir: str) -> list[str]:
    """扫描目录下所有JSON/YAML文件。"""
    files = []
    for sd in SCAN_DIRS:
        scan_path = os.path.join(root_dir, sd)
        if not os.path.exists(scan_path):
            continue
        for root, dirs, fnames in os.walk(scan_path):
            # 跳过node_modules和__pycache__
            dirs[:] = [d for d in dirs if d not in ('node_modules', '__pycache__', '.git')]
            for fname in fnames:
                if fname.endswith(('.json', '.yaml', '.yml')):
                    fpath = os.path.join(root, fname)
                    files.append(fpath)
    return files


def scan_all_files(root_dir: str) -> list[str]:
    """全量扫描所有JSON文件（兜底）。"""
    files = []
    for root, dirs, fnames in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '__pycache__', '.git', '.codebuddy')]
        for fname in fnames:
            if fname.endswith('.json'):
                fpath = os.path.join(root, fname)
                files.append(fpath)
    return files


def parse_template_json(data: dict) -> dict | None:
    """从JSON dict解析模板。"""
    wf_id = data.get("workflow_id") or data.get("id", "")
    if not wf_id:
        return None
    
    template = {
        "workflow_id": wf_id,
        "name": data.get("name", wf_id),
        "task_type": data.get("task_type", "txt2img"),
        "category": data.get("category", "image"),
        "description": data.get("description", ""),
        "inputs": [],
        "models": [],
        "tags": [],
    }
    
    # Extract models
    models = data.get("models", [])
    if isinstance(models, list):
        for m in models:
            if isinstance(m, dict) and "name" in m:
                template["models"].append(m["name"])
            elif isinstance(m, str):
                template["models"].append(m)
    
    # Extract tags
    rec = data.get("recommendation", {})
    if isinstance(rec, dict):
        template["tags"] = rec.get("tags", [])
    elif isinstance(rec, list):
        template["tags"] = rec
    
    # Extract inputs with bindings
    inputs = data.get("inputs", [])
    for inp in inputs:
        if not isinstance(inp, dict):
            continue
        binding = inp.get("binding", {})
        if not binding or not binding.get("node_id") or not binding.get("class_type"):
            continue
        template["inputs"].append({
            "id": inp.get("id", ""),
            "label": inp.get("label", ""),
            "type": inp.get("type", "string"),
            "required": inp.get("required", False),
            "default": inp.get("default"),
            "min": inp.get("min"),
            "max": inp.get("max"),
            "binding": {
                "node_id": str(binding["node_id"]),
                "class_type": binding["class_type"],
                "input": binding.get("input", ""),
            }
        })
    
    return template


def extract_from_comfyui_workflow(content: str) -> dict | None:
    """从ComfyUI API格式的workflow JSON中提取模板。"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    
    if not isinstance(data, dict):
        return None
    
    # Check if it's ComfyUI API format: {node_id: {class_type, inputs}}
    has_class_type = any(
        isinstance(v, dict) and "class_type" in v
        for v in data.values()
    )
    if not has_class_type:
        return None
    
    # It's a raw ComfyUI workflow - extract unique class_types
    nodes = {}
    for nid, node in data.items():
        if isinstance(node, dict) and "class_type" in node:
            ct = node["class_type"]
            if ct not in nodes:
                nodes[ct] = len(nodes)
                nodes[ct] = node
    
    # Only process if it has enough nodes
    if len(nodes) < 3:
        return None
    
    # Generate a template from the workflow structure
    inputs = []
    node_list = []
    for nid, node in data.items():
        if isinstance(node, dict) and "class_type" in node:
            ct = node["class_type"]
            node_list.append(ct)
            
            # Find text inputs to use as prompt bindings
            inp = node.get("inputs", {})
            if ct == "CLIPTextEncode" and "text" in inp:
                inputs.append({
                    "id": "prompt",
                    "type": "string",
                    "required": True,
                    "default": inp["text"] if isinstance(inp["text"], str) else "",
                    "binding": {"node_id": str(nid), "class_type": ct, "input": "text"},
                })
            elif ct == "EmptyLatentImage":
                for k in ("width", "height", "batch_size"):
                    if k in inp:
                        inputs.append({
                            "id": k,
                            "type": "integer",
                            "default": inp[k] if isinstance(inp[k], (int, float)) else None,
                            "binding": {"node_id": str(nid), "class_type": ct, "input": k},
                        })
            elif ct == "KSampler":
                for k in ("seed", "steps", "cfg", "denoise"):
                    if k in inp:
                        inputs.append({
                            "id": k,
                            "type": "float" if k in ("cfg", "denoise") else "integer",
                            "default": inp[k] if isinstance(inp[k], (int, float)) else None,
                            "binding": {"node_id": str(nid), "class_type": ct, "input": k},
                        })
    
    if not inputs:
        return None
    
    # Generate workflow_id from node types
    wf_id = "_".join(["wf"] + [ct[:8] for ct in node_list[:3]])
    
    return {
        "workflow_id": wf_id,
        "name": "Auto-detected: " + " + ".join(node_list[:4]),
        "task_type": "txt2img" if "KSampler" in node_list else "unknown",
        "category": "image",
        "description": f"从ComfyUI workflow自动提取 ({len(node_list)} nodes)",
        "inputs": inputs,
        "models": [],
        "tags": node_list,
    }


def main():
    root = os.getcwd()
    print(f"扫描根目录: {root}")
    
    # Phase 1: Scan template directories
    files = scan_files(root)
    print(f"找到 {len(files)} 个候选文件")
    
    # Phase 2: Filter template files
    template_files = []
    for fpath in files:
        try:
            with open(fpath, encoding='utf-8', errors='ignore') as f:
                content = f.read(10000)  # Read first 10KB
            if is_template_file(content):
                template_files.append(fpath)
        except Exception:
            pass
    
    print(f"识别出 {len(template_files)} 个模板文件")
    
    # Phase 3: Parse templates
    templates = []
    seen_ids = set()
    
    for fpath in template_files:
        try:
            with open(fpath, encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Try JSON array
            data = json.loads(content)
            
            if isinstance(data, list):
                for item in data:
                    t = parse_template_json(item)
                    if t and t["workflow_id"] not in seen_ids:
                        seen_ids.add(t["workflow_id"])
                        templates.append(t)
            elif isinstance(data, dict):
                t = parse_template_json(data)
                if t and t["workflow_id"] not in seen_ids:
                    seen_ids.add(t["workflow_id"])
                    templates.append(t)
                    
        except (json.JSONDecodeError, Exception) as e:
            # Try raw ComfyUI workflow format
            try:
                t = extract_from_comfyui_workflow(content)
                if t and t["workflow_id"] not in seen_ids:
                    seen_ids.add(t["workflow_id"])
                    templates.append(t)
                    print(f"  [raw workflow] {fpath}")
            except Exception:
                pass
    
    # Phase 4: If still no templates, do full scan
    if len(templates) < 5:
        print("\n模板目录扫描结果较少，进行全量JSON扫描...")
        all_files = scan_all_files(root)
        for fpath in all_files:
            if fpath in template_files:
                continue
            try:
                with open(fpath, encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                t = extract_from_comfyui_workflow(content)
                if t and t["workflow_id"] not in seen_ids:
                    seen_ids.add(t["workflow_id"])
                    templates.append(t)
            except Exception:
                pass
    
    # Phase 5: Dedup and save
    # Dedup by workflow_id
    final_templates = list({t["workflow_id"]: t for t in templates}.values())
    
    # Sort
    final_templates.sort(key=lambda t: t["workflow_id"])
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_templates, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*50}")
    print(f"完成!")
    print(f"  扫描文件: {len(files)}")
    print(f"  模板文件: {len(template_files)}")
    print(f"  提取模板: {len(final_templates)}")
    print(f"  输出文件: {OUTPUT_FILE} ({os.path.getsize(OUTPUT_FILE)} bytes)")
    print(f"{'='*50}")
    
    # Summary by category
    cats = {}
    for t in final_templates:
        c = t.get("category", "unknown")
        cats[c] = cats.get(c, 0) + 1
    print(f"\n按类别:")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n}")
    
    return final_templates


if __name__ == "__main__":
    main()
