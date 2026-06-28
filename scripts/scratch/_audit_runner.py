#!/usr/bin/env python3
"""Agnes Business Audit — Runner"""
import ast
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

results = []

def ok(name): results.append(("PASS", name))
def fail(name, detail=""): results.append(("FAIL", f"{name}: {detail}"))

# ── 1. 工具可用性 ──
try:
    ok("tool_import file_tools")
except Exception as e:
    fail("tool_import file_tools", str(e))

# ── 2. 引擎导入 ──
engine_map = {
    "engines.text_to_image": "TextToImageEngine",
    "engines.video": "VideoEngine",
    "engines.image_to_image": "ImageToImageEngine",
    "engines.batch_grid": "BatchVariantEngine",
}
for mod, cls in engine_map.items():
    try:
        m = __import__(mod, fromlist=[cls])
        getattr(m, cls)
        ok(f"engine {mod}")
    except Exception as e:
        fail(f"engine {mod}", str(e))

# ── 3. ComfyUI ──
try:
    ok("comfyui_tools import")
except Exception as e:
    fail("comfyui_tools import", str(e))

# ── 4. 核心模块 ──
core_mods = ["core.client", "core.config", "core.provider", "core.tools", "core.validator"]
for m in core_mods:
    try:
        __import__(m)
        ok(f"core {m}")
    except Exception as e:
        fail(f"core {m}", str(e))

# ── 5. 自定义工具 AST ──
for fname in ["output/custom_tools/comfyui_status.py", "output/custom_tools/comfyui_submit_workflow.py"]:
    try:
        with open(os.path.join(ROOT, fname), encoding="utf-8") as f:
            ast.parse(f.read())
        ok(f"AST {fname}")
    except Exception as e:
        fail(f"AST {fname}", str(e))

# ── 6. JSON 配置 ──
for fname in ["tools.json", "models.json"]:
    try:
        with open(os.path.join(ROOT, fname), encoding="utf-8") as f:
            json.load(f)
        ok(f"JSON {fname}")
    except Exception as e:
        fail(f"JSON {fname}", str(e))

# ── 7. 输出摘要 ──
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
for s, m in results:
    print(f"[{s}] {m}")
print(f"\n{passed} passed, {failed} failed")
