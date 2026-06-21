#!/usr/bin/env python3
"""Agnes Smart Studio — 冒烟测试（30秒内完成）

运行方式:
    python test_smoke.py          # 完整测试
    python test_smoke.py --quick  # 仅配置验证（无需网络）

覆盖：
- 配置文件完整性
- 工具格式字符串冲突检测
- API 连接性
- 核心工具功能验证
- 供应商可用性
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; X = "\033[0m"

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    global passed, failed
    if condition:
        print(f"  {G}PASS{X} {name} {detail}")
        passed += 1
        return True
    else:
        print(f"  {R}FAIL{X} {name}: {detail}")
        failed += 1
        return False


# ═══════════════════════════════════════════════════════════════════
# 1. 配置文件
# ═══════════════════════════════════════════════════════════════════
print(f"\n{C}── 配置文件 ──{X}")

# .env
env_file = ROOT / ".env"
check(".env exists", env_file.exists())
if env_file.exists():
    content = env_file.read_text(encoding="utf-8")
    has_key = "AGNES_API_KEY=" in content and "sk-your-api-key" not in content
    check(".env has API key", has_key, "placeholder detected" if not has_key else "OK")

# models.json
models_path = ROOT / "models.json"
check("models.json exists", models_path.exists())
if models_path.exists():
    try:
        cfg = json.loads(models_path.read_text(encoding="utf-8"))
        providers = cfg.get("providers", {})
        check("models.json valid JSON", True)
        check("models.json has providers", len(providers) > 0, f"{len(providers)} providers")
        active = cfg.get("active", "")
        check("models.json active valid", active in providers, f"active={active}, available={list(providers.keys())}")
    except json.JSONDecodeError as e:
        check("models.json valid JSON", False, str(e))

# tools.json
tools_path = ROOT / "tools.json"
check("tools.json exists", tools_path.exists())
if tools_path.exists():
    try:
        tools_cfg = json.loads(tools_path.read_text(encoding="utf-8"))
        tools = tools_cfg.get("tools", [])
        check("tools.json valid JSON", True, f"{len(tools)} tools")

        # 格式字符串冲突检测
        import re
        bad = []
        for t in tools:
            name = t.get("name", "?")
            cmd = t.get("command", "")
            params = set(t.get("parameters", {}).keys())
            placeholders = set(re.findall(r"\{([a-zA-Z_]\w*)\}", cmd))
            unexpected = placeholders - params
            if unexpected:
                bad.append(f"{name}: {{{', '.join(sorted(unexpected))}}}")

        check(f"tools.json format strings", len(bad) == 0,
              f"{len(bad)} conflicts: {'; '.join(bad)}" if bad else "all clean")
    except json.JSONDecodeError as e:
        check("tools.json valid JSON", False, str(e))

# ═══════════════════════════════════════════════════════════════════
# 2. 依赖
# ═══════════════════════════════════════════════════════════════════
print(f"\n{C}── 依赖 ──{X}")
for mod, desc in [("httpx", "HTTP"), ("rich", "UI"), ("PIL", "Images"),
                  ("dotenv", "Env"), ("prompt_toolkit", "Input")]:
    try:
        __import__(mod)
        check(f"import {mod}", True, desc)
    except ImportError:
        check(f"import {mod}", False, f"缺失: pip install {mod}")

# ═══════════════════════════════════════════════════════════════════
# 3. 工具加载
# ═══════════════════════════════════════════════════════════════════
print(f"\n{C}── 工具加载 ──{X}")
try:
    from core.tools import get_registry
    reg = get_registry()
    reg.load()
    n = len(reg.definitions)
    check("ToolRegistry.load()", n > 0, f"{n} tools loaded")

    # Quick functional test of 3 core tools
    core_tools = [
        ("read_file", {"path": str(ROOT / "README.md")}),
        ("list_files", {"path": str(ROOT)}),
        ("env_check", {}),
    ]
    for tool_name, tool_args in core_tools:
        result = reg.execute(tool_name, tool_args)
        ok = not result.startswith("[错误]")
        check(f"  execute {tool_name}", ok, result[:60] if not ok else "OK")
except Exception as e:
    check("ToolRegistry.load()", False, str(e))

# ═══════════════════════════════════════════════════════════════════
# 4. API 连接性 (quick mode skips)
# ═══════════════════════════════════════════════════════════════════
if "--quick" not in sys.argv:
    print(f"\n{C}── API 连接性 ──{X}")
    from core.startup_checks import _check_api_connectivity
    _check_api_connectivity()
    # Re-read results
    from core.startup_checks import _results
    for cat, ok, msg in _results:
        if cat == "api":
            check(f"API: {cat}", ok, msg)
else:
    print(f"\n{C}── API 连接性 ── 跳过 (--quick){X}")

# ═══════════════════════════════════════════════════════════════════
print(f"\n{C}{'─' * 50}{X}")
print(f"  {G}{passed} passed{X}, {R}{failed} failed{X}, {passed + failed} total")
if failed > 0:
    print(f"  {R}SMOKE TEST FAILED{X}")
    sys.exit(1)
else:
    print(f"  {G}SMOKE TEST PASSED{X}")
    sys.exit(0)
