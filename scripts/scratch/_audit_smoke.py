"""Quick audit smoke test"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []

# 1. Import core modules
for mod in ['core.tools', 'core.chat', 'core.client', 'core.config',
            'core.comfyui_tools', 'core.file_tools', 'core.git_tools',
            'core.task_manager', 'core.scheduler', 'core.provider',
            'core.prompt_bypass', 'core.image_tools', 'core.video_editor']:
    try:
        __import__(mod)
        results.append(f"  OK  import {mod}")
    except Exception as e:
        results.append(f"  FAIL import {mod}: {e}")

# 2. Check tools.json
import json

with open('tools.json', encoding='utf-8') as f:
    tools_data = json.load(f)
tools_list = tools_data.get('tools', tools_data)
results.append(f"\n  tools.json: {len(tools_list)} tools defined")

comfy_tools = [t['name'] for t in tools_list if 'comfyui' in t.get('name','').lower()]
results.append(f"  ComfyUI tools in json: {comfy_tools}")

# 3. Check for broken tool references
broken = []
for t in tools_list:
    func = t.get('function', '')
    if func.startswith('core.comfyui_tools.'):
        fn_name = func.split('.')[-1]
        mod = __import__('core.comfyui_tools', fromlist=[fn_name])
        if not hasattr(mod, fn_name):
            broken.append(f"{t['name']} -> {func} (missing)")
if broken:
    results.append(f"\n  BROKEN tool refs: {broken}")
else:
    results.append("\n  All ComfyUI tool refs OK")

# 4. Check .env
env_vars = {}
if os.path.exists('.env'):
    for line in open('.env', encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env_vars[k] = v[:20] + '...' if len(v) > 20 else v
results.append(f"\n  .env keys: {list(env_vars.keys())}")

# 5. Syntax check key files
import ast

for fname in ['query.py', 'crux_studio.py']:
    if os.path.exists(fname):
        try:
            ast.parse(open(fname, encoding='utf-8').read())
            results.append(f"  OK  syntax {fname}")
        except SyntaxError as e:
            results.append(f"  FAIL syntax {fname}: {e}")

print('\n'.join(results))
print("\n=== AUDIT SMOKE COMPLETE ===")
