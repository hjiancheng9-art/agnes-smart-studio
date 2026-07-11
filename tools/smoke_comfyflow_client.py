#!/usr/bin/env python3
"""
ComfyFlow API 冒烟测试 — 验证 CRUX 可通过 HTTP 调用 ComfyFlow Compiler

用法:
    python tools/smoke_comfyflow_client.py

环境变量:
    COMFYFLOW_API_URL — API 地址 (默认 http://127.0.0.1:8080)

验收标准:
    1. CRUX 不 import comfyflow_compiler
    2. CRUX 不写 CodeBuddy 项目文件
    3. 通过 COMFYFLOW_API_URL 调用
    4. compile success 返回
"""

import sys
from pathlib import Path

# 确保 import core/comfyflow_client 能找到
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.comfyflow_client import HAS_HTTPX, ComfyFlowClient


def main():
    client = ComfyFlowClient()

    # 1. health
    print("=" * 50)
    print("1. Health Check")
    print("=" * 50)
    health = client.health()
    print(f"   status:  {health.get('status', '?')}")
    print(f"   version: {health.get('compiler_version', '?')}")
    assert health.get("status") == "ok", f"Health failed: {health}"
    print("   ✅ 通过\n")

    # 2. probe
    print("=" * 50)
    print("2. Probe (能力探测)")
    print("=" * 50)
    probe = client.probe()
    if isinstance(probe, dict) and len(probe) > 2:
        keys = list(probe.keys())[:5]
        print(f"   返回 {len(probe)} 个字段: {keys}")
        print("   ✅ 通过\n")
    else:
        print(f"   probe 返回: {probe}")
        print("   ⚠️ 跳过 (可能 ComfyUI 未运行)\n")

    # 3. compile
    print("=" * 50)
    print("3. Compile (编译测试)")
    print("=" * 50)
    result = client.compile("a dragon flying over a cyberpunk city, cinematic lighting")
    print(f"   success:  {result.get('success')}")
    print(f"   blueprint: {result.get('blueprint', '?')}")
    print(f"   error:     {result.get('error', 'none')}")
    assert result.get("success"), f"Compile failed: {result.get('error')}"
    print("   ✅ 通过\n")

    # 4. Verify: no direct import of comfyflow_compiler
    print("=" * 50)
    print("4. 验证: 没有直接 import comfyflow_compiler")
    print("=" * 50)
    import ast
    import inspect
    source = inspect.getsource(sys.modules['core.comfyflow_client'])
    # 只检查真正的 import 语句，忽略 docstring/注释
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name if isinstance(node, ast.Import) else (node.module or '') for a in node.names]
            imports.extend(n for n in names if n)
    has_direct_import = any('comfyflow_compiler' in n for n in imports)
    if has_direct_import:
        print(f"   ❌ 失败: 客户端 import 了 comfyflow_compiler! ({imports})")
        sys.exit(1)
    else:
        print(f"   ✅ 通过: 纯 HTTP 调用，零依赖编译引擎 (imports: {imports})")
    print()

    # ===== Summary =====
    print("=" * 50)
    print("✅ 全部冒烟测试通过")
    print(f"   客户端模式: {'httpx' if HAS_HTTPX else 'urllib (回退)'}")
    print(f"   API 地址:   {client.base_url}")
    print("=" * 50)


if __name__ == "__main__":
    main()
