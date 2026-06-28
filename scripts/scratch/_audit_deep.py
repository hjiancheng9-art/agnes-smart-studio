#!/usr/bin/env python3
"""Deep audit: import all modules, check tools.json, check models.json, check garbage files."""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

print("=" * 60)
print("AUDIT REPORT")
print("=" * 60)

errors = []
warnings = []

# ── 1. Import all core modules ──
print("\n── 1. Module Imports ──")
modules = [
    "core.config", "core.tools", "core.agent", "core.brain", "core.chat",
    "core.client", "core.pipeline_tools", "core.file_tools", "core.image_tools",
    "core.git_tools", "core.browser_tools", "core.audio_tools", "core.comfyui_tools",
    "core.hooks", "core.provider", "core.scheduler", "core.task_manager",
    "core.test_loop", "core.observability", "core.cost_tracker", "core.resilience",
    "core.mcp_client", "core.lsp", "core.code_intel", "core.notebook",
    "core.self_tool", "core.startup_checks", "core.version", "core.tool_cache",
    "core.marketplace", "core.orchestra", "core.prompt_bypass", "core.project",
    "core.rules", "core.skills", "core.validator", "core.video_editor",
    "core.video_models", "core.web_browser", "core.brain_data",
    "ui.cli", "ui.display", "ui.self_commands",
    "utils.history", "utils.image_input", "utils.memory", "utils.gallery",
    "engines.text_to_image", "engines.video", "engines.batch_grid",
]
for mod in modules:
    try:
        __import__(mod)
        print(f"  OK  {mod}")
    except Exception as e:
        errors.append(f"Import {mod}: {e}")
        print(f"  FAIL {mod}: {e}")

# ── 2. Tools.json format string audit ──
print("\n── 2. Tools.json Format Strings ──")
try:
    tools_cfg = json.loads(open("tools.json", encoding="utf-8").read())
    for t in tools_cfg.get("tools", []):
        name = t.get("name", "?")
        cmd = t.get("command", "")
        params = set(t.get("parameters", {}).keys())
        placeholders = set(re.findall(r"\{([a-zA-Z_]\w*)\}", cmd))
        unexpected = placeholders - params
        if unexpected:
            warnings.append(f"tools.json: {name} has unknown placeholders: {unexpected}")
            print(f"  WARN {name}: unknowns={unexpected}")
        else:
            print(f"  OK  {name}")
except Exception as e:
    errors.append(f"tools.json: {e}")
    print(f"  FAIL: {e}")

# ── 3. Models.json consistency ──
print("\n── 3. Models.json Consistency ──")
try:
    cfg = json.loads(open("models.json", encoding="utf-8").read())
    providers = cfg.get("providers", {})
    active = cfg.get("active", "")
    fallback = cfg.get("fallback", {}).get("priority", [])
    if active not in providers:
        warnings.append(f"Active provider '{active}' not in providers: {list(providers.keys())}")
        print(f"  WARN active='{active}' not in providers")
    else:
        print(f"  OK  active={active}")
    for p in fallback:
        if p not in providers:
            warnings.append(f"Fallback provider '{p}' not in providers")
            print(f"  WARN fallback '{p}' not in providers")
    print(f"  OK  {len(providers)} providers, fallback={fallback}")
except Exception as e:
    errors.append(f"models.json: {e}")
    print(f"  FAIL: {e}")

# ── 4. Garbage / orphaned files ──
print("\n── 4. Suspicious Files ──")
suspicious_patterns = [
    r"\{is_prime\(n\)\}",  # garbage file from bash history
    r"test123\.txt",
    r"_test_write\.txt",
    r"AGENTS_INSTALL_GUIDE\.md",
    r"README_AGNES_AGENTS\.md",
    r"deepseek-skill-code-review\.md",
    r"query\.bat",
    r"query\.sh",
    r"\.bat$",
]
for f in os.listdir(ROOT):
    full = os.path.join(ROOT, f)
    if not os.path.isfile(full):
        continue
    for pat in suspicious_patterns:
        if re.search(pat, f, re.IGNORECASE):
            warnings.append(f"Suspicious file: {f}")
            print(f"  WARN suspicious: {f}")
            break

# ── 5. Git deleted files that might be important ──
print("\n── 5. Git Deleted Files ──")
result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT)
for line in result.stdout.splitlines():
    if line.startswith(" D"):
        fname = line[3:].strip()
        # Check if it looks like a temp/test file vs real file
        if not any(x in fname.lower() for x in ["test123", "_test", ".bat", ".sh", "query."]):
            warnings.append(f"Deleted important file: {fname}")
            print(f"  WARN deleted: {fname}")
        else:
            print(f"  OK  deleted temp: {fname}")

# ── Summary ──
print("\n" + "=" * 60)
print(f"SUMMARY: {len(errors)} errors, {len(warnings)} warnings")
if errors:
    for e in errors:
        print(f"  ERROR: {e}")
if warnings:
    for w in warnings:
        print(f"  WARNING: {w}")
if not errors and not warnings:
    print("  ALL CLEAN ✓")
print("=" * 60)
sys.exit(1 if errors else 0)
