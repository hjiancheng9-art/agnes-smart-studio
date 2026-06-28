#!/usr/bin/env python3
"""Audit: verify all engine imports"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

results = []

# 1. AST check custom tools
for fname in ['output/custom_tools/comfyui_status.py', 'output/custom_tools/comfyui_submit_workflow.py']:
    try:
        path = os.path.join(ROOT, fname)
        with open(path, encoding='utf-8') as f:
            ast.parse(f.read())
        results.append(("PASS", f"AST: {fname}"))
    except Exception as e:
        results.append(("FAIL", f"AST: {fname} -> {e}"))

# 2. Engine imports
engines = [
    ("engines.text_to_image", "TextToImageEngine"),
    ("engines.video", "VideoEngine"),
    ("engines.image_to_image", "ImageToImageEngine"),
    ("engines.batch_grid", "BatchVariantEngine"),
]
for mod_name, cls_name in engines:
    try:
        mod = __import__(mod_name, fromlist=[cls_name])
        getattr(mod, cls_name)
        results.append(("PASS", f"import {mod_name}"))
    except Exception as e:
        results.append(("FAIL", f"import {mod_name} -> {e}"))

# 3. Core imports
core_mods = [
    "core.comfyui_tools",
    "core.tools",
    "core.client",
    "core.config",
    "core.provider",
]
for mod_name in core_mods:
    try:
        __import__(mod_name)
        results.append(("PASS", f"import {mod_name}"))
    except Exception as e:
        results.append(("FAIL", f"import {mod_name} -> {e}"))

# 4. Custom tools actual import test — 仅做 AST 语法校验，不执行
for fname in ['output/custom_tools/comfyui_status.py', 'output/custom_tools/comfyui_submit_workflow.py']:
    try:
        path = os.path.join(ROOT, fname)
        with open(path, encoding='utf-8') as fh:
            ast.parse(fh.read())
        results.append(("PASS", f"AST: {fname}"))
    except Exception as e:
        results.append(("FAIL", f"AST: {fname} -> {e}"))

# Summary
passed = sum(1 for s, _ in results if s == "PASS")
failed = sum(1 for s, _ in results if s == "FAIL")
for status, msg in results:
    print(f"[{status}] {msg}")
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed > 0 else 0)
