"""全兽调用链烟雾测试 —— 验证每条 beast 的桥接是否可初始化并调用。

九兽清单:
  1. Kimi       - kimi_bridge / kimi_mcp_bridge
  2. Copilot    - copilot_bridge  
  3. Codex      - codex_bridge
  4. Claude     - claude_mcp_bridge
  5. CodeBuddy  - codebuddy_bridge
  6. Qoder      - qoder_bridge
  7. CRUX(自身)  - mcp_server (已单独验证)
  8. DeepSeek   - provider
  9. Zhipu      - provider
"""

import importlib
import traceback
import os

def test_module(module_path: str, label: str) -> dict:
    """测试模块能否正常导入且关键符号存在。"""
    result = {"module": module_path, "label": label, "status": "?", "details": ""}
    try:
        mod = importlib.import_module(module_path)
        result["status"] = "OK"
        # 列出模块里的主要类/函数
        symbols = [k for k in dir(mod) if not k.startswith("_") and not k.startswith("__")]
        result["details"] = f"symbols: {', '.join(symbols[:15])}"
    except Exception as e:
        result["status"] = "FAIL"
        result["details"] = f"{type(e).__name__}: {e}"
    return result


def test_brige_cli(label: str, cli_cmd: str) -> dict:
    """测试外部 CLI 是否存在。"""
    import shutil
    result = {"cli": cli_cmd, "label": label, "status": "?", "details": ""}
    found = shutil.which(cli_cmd)
    if found:
        result["status"] = "OK"
        result["details"] = found
    else:
        result["status"] = "SKIP"
        result["details"] = f"CLI '{cli_cmd}' not found in PATH"
    return result


def test_provider(label: str, env_key: str) -> dict:
    """测试 provider 的 API key 是否配置。"""
    result = {"provider": label, "status": "?", "details": ""}
    key = os.environ.get(env_key, "")
    if key and len(key) > 10:
        result["status"] = "OK"
        result["details"] = f"key configured ({key[:8]}...)"
    else:
        result["status"] = "SKIP"
        result["details"] = f"env {env_key} not set or too short"
    return result


def main():
    print("=" * 60)
    print("CRUX 全兽调用链烟雾测试")
    print("=" * 60)
    
    results = []
    
    # 1. Kimi bridges
    print("\n── 1. Kimi ──")
    r = test_module("core.mcp_servers.kimi_bridge", "Kimi Bridge (v1)")
    print(f"  import: {r['status']:5s}  {r['details']}")
    results.append(r)
    
    r = test_brige_cli("Kimi CLI", "kimi")
    print(f"  cli:    {r['status']:5s}  {r['details']}")
    results.append(r)
    
    r = test_module("core.mcp_servers.kimi_mcp_bridge", "Kimi MCP Bridge (v2)")
    print(f"  import: {r['status']:5s}  {r['details']}")
    results.append(r)
    
    # 2. Copilot
    print("\n── 2. Copilot ──")
    r = test_module("core.mcp_servers.copilot_bridge", "Copilot Bridge")
    print(f"  import: {r['status']:5s}  {r['details']}")
    results.append(r)
    
    r = test_brige_cli("Copilot CLI", "copilot")
    print(f"  cli:    {r['status']:5s}  {r['details']}")
    results.append(r)
    
    # 3. Codex
    print("\n── 3. Codex ──")
    r = test_module("core.mcp_servers.codex_bridge", "Codex Bridge")
    print(f"  import: {r['status']:5s}  {r['details']}")
    results.append(r)
    
    r = test_brige_cli("Codex CLI", "codex")
    print(f"  cli:    {r['status']:5s}  {r['details']}")
    results.append(r)
    
    # 4. Claude
    print("\n── 4. Claude ──")
    r = test_module("core.claude_mcp_bridge", "Claude MCP Bridge")
    print(f"  import: {r['status']:5s}  {r['details']}")
    results.append(r)
    
    # Claude bridge 是独立实现，不依赖外部 CLI
    from core.claude_mcp_bridge import _TOOL_HANDLERS
    print(f"  tools:  {len(_TOOL_HANDLERS)} handlers loaded")
    
    # 测试一个轻量 handler
    try:
        from core.claude_mcp_bridge import _handle_find_files
        res = _handle_find_files({"pattern": "*.py", "path": "core"})
        ok = not res.get("isError", True)
        print(f"  call:   {'OK' if ok else 'FAIL'}")
        results.append({"module": "claude_bridge", "label": "Claude _handle_find_files", "status": "OK" if ok else "FAIL", "details": ""})
    except Exception as e:
        print(f"  call:   FAIL - {e}")
        results.append({"module": "claude_bridge", "label": "Claude _handle_find_files", "status": "FAIL", "details": str(e)})
    
    # 5. CodeBuddy
    print("\n── 5. CodeBuddy ──")
    r = test_module("core.mcp_servers.codebuddy_bridge", "CodeBuddy Bridge")
    print(f"  import: {r['status']:5s}  {r['details']}")
    results.append(r)
    
    r = test_brige_cli("CodeBuddy CLI", "codebuddy")
    print(f"  cli:    {r['status']:5s}  {r['details']}")
    results.append(r)
    
    # 6. Qoder
    print("\n── 6. Qoder ──")
    r = test_module("core.mcp_servers.qoder_bridge", "Qoder Bridge")
    print(f"  import: {r['status']:5s}  {r['details']}")
    results.append(r)
    
    r = test_brige_cli("Qoder CLI", "qodercli")
    print(f"  cli:    {r['status']:5s}  {r['details']}")
    results.append(r)
    
    # 7. CRUX 自身 (mcp_server)
    print("\n── 7. CRUX (mcp_server) ──")
    r = test_module("core.mcp_server", "CRUX MCP Server")
    print(f"  import: {r['status']:5s}  {r['details']}")
    results.append(r)
    
    # 测试 _dispatch_tool_impl 是否可用
    from core.chat import ChatSession
    from core.client import CruxClient
    import json
    
    client = CruxClient(
        api_key=os.environ.get("DEEPSEEK_API_KEY", "sk-test"),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    )
    session = ChatSession(client)
    
    has_impl = hasattr(session, "_dispatch_tool_impl")
    print(f"  _dispatch_tool_impl: {'OK' if has_impl else 'FAIL'}")
    
    if has_impl:
        try:
            result, sides = session._dispatch_tool_impl("list_files", json.dumps({"path": "core"}))
            ok = len(result) > 0
            print(f"  dispatch(list_files): {'OK' if ok else 'FAIL'}")
            results.append({"module": "mcp_server", "label": "dispatch chain", "status": "OK" if ok else "FAIL", "details": ""})
        except Exception as e:
            print(f"  dispatch: FAIL - {e}")
            results.append({"module": "mcp_server", "label": "dispatch chain", "status": "FAIL", "details": str(e)})
    
    # 8 & 9. Providers
    print("\n── 8. DeepSeek provider ──")
    r = test_provider("DeepSeek", "DEEPSEEK_API_KEY")
    print(f"  key:    {r['status']:5s}  {r['details']}")
    results.append(r)
    
    print("\n── 9. Zhipu provider ──")
    r = test_provider("Zhipu", "ZHIPU_API_KEY")
    print(f"  key:    {r['status']:5s}  {r['details']}")
    results.append(r)
    
    # 额外: 检查 models.json 里的 provider 配置
    try:
        import json as _json
        with open("models.json", "r") as f:
            cfg = _json.load(f)
        providers = list(cfg.get("providers", {}).keys())
        print(f"  models.json providers: {', '.join(providers)}")
        print(f"  active: {cfg.get('active', '?')}")
    except Exception:
        pass
    
    # ── 汇总 ──
    print("\n" + "=" * 60)
    ok = sum(1 for r in results if r["status"] == "OK")
    skip = sum(1 for r in results if r["status"] == "SKIP")
    fail = sum(1 for r in results if r["status"] == "FAIL")
    total = len(results)
    
    print(f"总计: {total} tests")
    print(f"  PASS: {ok}")
    print(f"  SKIP: {skip}")
    print(f"  FAIL: {fail}")
    
    if fail > 0:
        print("\n失败项:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  [{r['label']}] {r['details']}")
    
    print("=" * 60)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    exit(main())
