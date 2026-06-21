#!/usr/bin/env python3
"""Agnes Smart Studio — 全方位测试套件

运行:
    python test_comprehensive.py          # 全部测试
    python test_comprehensive.py --quick  # 跳过 AI 对话测试

覆盖:
- 工具测试: read/write/edit/search/list/env/python/web/git
- 对话测试: 多轮、上下文记忆、工具调用
- 边界测试: 特殊字符、大内容、错误恢复
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; D = "\033[2m"; X = "\033[0m"

passed = 0
failed = 0
failures = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    global passed, failed
    if condition:
        print(f"  {G}PASS{X} {name}")
        passed += 1
    else:
        print(f"  {R}FAIL{X} {name}: {detail}")
        failed += 1
        failures.append((name, detail))
    return condition


# ═══════════════════════════════════════════════════════════════════
# 1. 工具基础测试（不经过 AI，直接调工具）
# ═══════════════════════════════════════════════════════════════════
def test_tools_direct():
    print(f"\n{C}═══ 1. 工具基础测试（直接调用）═══{X}")

    from core.tools import reload_registry
    reg = reload_registry()
    reg.load()

    # 1a. read_file
    r = reg.execute("read_file", {"path": str(ROOT / "README.md")})
    check("read_file", r.startswith("---") and not r.startswith("[错误]"), r[:60])

    # 1b. list_files
    r = reg.execute("list_files", {"path": str(ROOT)})
    check("list_files", ".env" in r or "README" in r, r[:60])

    # 1c. write_file (with special chars)
    test_path = str(ROOT / "output" / "_test_special.py")
    content = '#!/usr/bin/env python3\n"""Test module with \'quotes\' and "double quotes" and \\backslash."""\nVERSION = "1.0"\nprint(f"v{VERSION}")\n'
    r = reg.execute("write_file", {"path": test_path, "content": content})
    ok1 = r.startswith("Written:") and Path(test_path).exists()
    check("write_file (special chars)", ok1, r[:60])

    # 1d. read_file verify
    if Path(test_path).exists():
        written = Path(test_path).read_text(encoding="utf-8")
        check("read_file verify", written == content, f"len={len(written)} vs {len(content)}")

    # 1e. edit_file
    r = reg.execute("edit_file", {
        "path": test_path,
        "old_text": 'VERSION = "1.0"',
        "new_text": 'VERSION = "2.0"',
    })
    ok = r.startswith("Edited:")
    check("edit_file", ok, r[:60])

    # 1f. edit_file verify
    if ok:
        new = Path(test_path).read_text(encoding="utf-8")
        check("edit_file verify", 'VERSION = "2.0"' in new)

    # 1g. search_files
    r = reg.execute("search_files", {"pattern": "Agnes"})
    has_results = len(r.strip()) > 0 and not r.startswith("[错误]")
    check("search_files", has_results, r[:60])

    # 1h. env_check
    r = reg.execute("env_check", {})
    ok = "Python" in r or "python" in r.lower() or not r.startswith("[错误]")
    check("env_check", ok, r[:80])

    # 1i. run_python
    r = reg.execute("run_python", {"code": "print(42)"})
    check("run_python", "42" in r, r[:60])

    # 1j. web_fetch (may fail offline - that's ok)
    r = reg.execute("web_fetch", {"url": "https://httpbin.org/get"})
    has_content = len(r) > 20 and not r.startswith("[错误]")
    check("web_fetch", has_content, r[:60] if not has_content else "OK")

    # 1k. git_status
    r = reg.execute("git_status", {})
    is_git = "not a git repo" not in r.lower() if r else False
    check("git_status", not r.startswith("[错误]"), r[:60])

    # 1l. count_lines
    r = reg.execute("count_lines", {})
    has_lines = ".py" in r or "lines" in r.lower() or not r.startswith("[错误]")
    check("count_lines", has_lines, r[:80])

    # 1m. glob_files
    r = reg.execute("glob_files", {"pattern": "**/*.py"})
    has_py = ".py" in r and not r.startswith("[错误]")
    check("glob_files", has_py, r[:60])

    # 1n. download_file (small test)
    r = reg.execute("download_file", {
        "url": "https://httpbin.org/bytes/16",
        "save_path": str(ROOT / "output" / "_test_download.bin"),
    })
    ok_dl = Path(ROOT / "output" / "_test_download.bin").exists()
    check("download_file", ok_dl, r[:60])

    # Cleanup
    for f in ["_test_special.py", "_test_download.bin"]:
        p = ROOT / "output" / f
        if p.exists():
            p.unlink()

    return reg


# ═══════════════════════════════════════════════════════════════════
# 2. 边界测试
# ═══════════════════════════════════════════════════════════════════
def test_edge_cases():
    print(f"\n{C}═══ 2. 边界测试 ═══{X}")

    from core.tools import reload_registry
    reg = reload_registry()
    reg.load()

    # 2a. Unknown tool
    r = reg.execute("nonexistent_tool_xyz", {})
    check("unknown tool", r.startswith("[错误] 未知工具"), r[:60])

    # 2b. Empty content write
    r = reg.execute("write_file", {
        "path": str(ROOT / "output" / "_test_empty.txt"),
        "content": "",
    })
    check("empty file", r.startswith("Written:"), r[:60])
    if Path(ROOT / "output" / "_test_empty.txt").exists():
        Path(ROOT / "output" / "_test_empty.txt").unlink()

    # 2c. Very long content
    long_content = "x" * 5000
    r = reg.execute("write_file", {
        "path": str(ROOT / "output" / "_test_long.txt"),
        "content": long_content,
    })
    ok = r.startswith("Written:") and Path(ROOT / "output" / "_test_long.txt").exists()
    check("long content (5000 chars)", ok, r[:60])
    if Path(ROOT / "output" / "_test_long.txt").exists():
        Path(ROOT / "output" / "_test_long.txt").unlink()

    # 2d. Unicode content
    unicode_content = "Hello 世界 🌍\nこんにちは\n안녕하세요"
    r = reg.execute("write_file", {
        "path": str(ROOT / "output" / "_test_unicode.txt"),
        "content": unicode_content,
    })
    ok = r.startswith("Written:")
    if ok:
        written = Path(ROOT / "output" / "_test_unicode.txt").read_text(encoding="utf-8")
        ok = written == unicode_content
    check("unicode content", ok, r[:60])
    if Path(ROOT / "output" / "_test_unicode.txt").exists():
        Path(ROOT / "output" / "_test_unicode.txt").unlink()

    # 2e. Missing required parameter
    r = reg.execute("read_file", {})
    is_error = r.startswith("[错误]")
    check("missing param (graceful)", is_error, r[:60])

    # 2f. File not found
    r = reg.execute("read_file", {"path": "/nonexistent/file_xyz_123.txt"})
    is_error = r.startswith("[错误]") or "No such file" in r or "not found" in r.lower()
    check("file not found (graceful)", is_error, r[:60])


# ═══════════════════════════════════════════════════════════════════
# 3. AI 对话测试（需网络）
# ═══════════════════════════════════════════════════════════════════
def test_ai_conversation():
    print(f"\n{C}═══ 3. AI 对话测试 ═══{X}")

    from core.client import AgnesClient
    from core.chat import ChatSession

    with open("models.json", encoding="utf-8") as f:
        cfg = json.load(f)
    provider = cfg["providers"][cfg["active"]]
    api_key = os.getenv(cfg["active"].upper() + "_API_KEY") or provider["api_key"]

    client = AgnesClient(api_key=api_key, base_url=provider["base_url"])
    session = ChatSession(client, default_model=provider["models"]["pro"])
    session.model = provider["models"]["pro"]

    # 3a. Basic conversation
    print("  3a. Basic chat...")
    text = ""
    errors = []
    try:
        for event in session.send_stream("Say exactly: OK"):
            if event[0] == "text":
                text += event[1] or ""
            elif event[0] == "error":
                errors.append(str(event[1]))
    except Exception as e:
        errors.append(str(e))
    check("basic chat", "OK" in text and not errors, text[:50] if not ("OK" in text) else "OK")

    # 3b. Multi-turn memory
    print("  3b. Multi-turn memory...")
    text2 = ""
    try:
        for event in session.send_stream("What did I just ask you to say? Answer briefly."):
            if event[0] == "text":
                text2 += event[1] or ""
    except Exception as e:
        errors.append(str(e))
    # Check if response references the previous turn
    has_memory = "OK" in text2 or "ok" in text2.lower()
    check("multi-turn memory", has_memory, text2[:60])

    # 3c. Coding task
    print("  3c. Coding task...")
    text3 = ""
    try:
        for event in session.send_stream("Write a one-line Python function: def add(a,b): return a+b. Just the code."):
            if event[0] == "text":
                text3 += event[1] or ""
    except Exception as e:
        errors.append(str(e))
    has_code = "def add" in text3 or "return a+b" in text3 or "return a + b" in text3
    check("coding response", has_code, text3[:60])

    # 3d. Chinese language capability
    print("  3d. Chinese capability...")
    text4 = ""
    try:
        for event in session.send_stream("用中文回复：你好"):
            if event[0] == "text":
                text4 += event[1] or ""
    except Exception as e:
        errors.append(str(e))
    has_chinese = any('一' <= c <= '鿿' for c in text4)
    check("Chinese language", has_chinese, text4[:60])

    client.close()


# ═══════════════════════════════════════════════════════════════════
# 4. AI 工具调用测试
# ═══════════════════════════════════════════════════════════════════
def test_ai_tool_calling():
    print(f"\n{C}═══ 4. AI 工具调用测试 ═══{X}")

    from core.client import AgnesClient
    from core.chat import ChatSession

    with open("models.json", encoding="utf-8") as f:
        cfg = json.load(f)
    provider = cfg["providers"][cfg["active"]]
    api_key = os.getenv(cfg["active"].upper() + "_API_KEY") or provider["api_key"]

    client = AgnesClient(api_key=api_key, base_url=provider["base_url"])
    session = ChatSession(client, default_model=provider["models"]["pro"])
    session.model = provider["models"]["pro"]

    # 4a. Tool: read_file
    print("  4a. Tool: read_file...")
    task = "Use read_file to read README.md (path: README.md). Tell me what the project is about in one sentence."
    text = ""
    tools_used = []
    try:
        for event in session.send_stream(task):
            if event[0] == "text":
                text += event[1] or ""
            elif event[0] == "info":
                tools_used.append(str(event[1]))
    except Exception as e:
        check("tool: read_file", False, str(e)[:80])
        client.close()
        return
    used_read = any("read_file" in t for t in tools_used)
    check("tool: read_file", used_read and len(text) > 10, text[:80])

    # 4b. Tool: write_file + read_file
    print("  4b. Tool: write_file...")
    task2 = "Use write_file to create output/_test_ai_file.txt with content 'hello from AI test'. Then use read_file to verify it."
    text2 = ""
    tools2 = []
    try:
        for event in session.send_stream(task2):
            if event[0] == "text":
                text2 += event[1] or ""
            elif event[0] == "info":
                tools2.append(str(event[1]))
    except Exception as e:
        check("tool: write_file", False, str(e)[:80])
        client.close()
        return
    wrote = any("write_file" in t for t in tools2)
    verified = Path(ROOT / "output" / "_test_ai_file.txt").exists()
    check("tool: write_file", wrote and verified, str(tools2)[:80])

    # 4c. Tool: list_files
    print("  4c. Tool: list_files...")
    task3 = "Use list_files to list the output directory (path: output). Say how many files you see."
    text3 = ""
    tools3 = []
    try:
        for event in session.send_stream(task3):
            if event[0] == "text":
                text3 += event[1] or ""
            elif event[0] == "info":
                tools3.append(str(event[1]))
    except Exception as e:
        check("tool: list_files", False, str(e)[:80])
        client.close()
        return
    used_list = any("list_files" in t for t in tools3)
    check("tool: list_files", used_list, text3[:80])

    # 4d. Tool: run_python
    print("  4d. Tool: run_python...")
    task4 = "Use run_python to run: print(sum(range(1,101))). Reply with just the result."
    text4 = ""
    tools4 = []
    try:
        for event in session.send_stream(task4):
            if event[0] == "text":
                text4 += event[1] or ""
            elif event[0] == "info":
                tools4.append(str(event[1]))
    except Exception as e:
        check("tool: run_python", False, str(e)[:80])
        client.close()
        return
    used = any("run_python" in t for t in tools4)
    has_result = "5050" in text4
    check("tool: run_python", used and has_result, text4[:80])

    # Cleanup
    test_file = ROOT / "output" / "_test_ai_file.txt"
    if test_file.exists():
        test_file.unlink()

    client.close()


# ═══════════════════════════════════════════════════════════════════
# 5. 配置完整性测试
# ═══════════════════════════════════════════════════════════════════
def test_config_integrity():
    print(f"\n{C}═══ 5. 配置完整性测试 ═══{X}")

    # 5a. tools.json format strings
    with open("tools.json", encoding="utf-8") as f:
        cfg = json.load(f)
    import re
    bad = []
    for t in cfg["tools"]:
        name = t["name"]
        cmd = t.get("command", "")
        params = set(t.get("parameters", {}).keys())
        placeholders = set(re.findall(r"\{([a-zA-Z_]\w*)\}", cmd))
        unexpected = placeholders - params
        if unexpected:
            bad.append(f"{name}: {unexpected}")
    check("tools.json format strings", len(bad) == 0,
          f"{len(bad)} conflicts: {'; '.join(bad)}" if bad else "all clean")

    # 5b. models.json structure
    with open("models.json", encoding="utf-8") as f:
        mcfg = json.load(f)
    active = mcfg.get("active", "")
    providers = mcfg.get("providers", {})
    check("models.json active valid", active in providers,
          f"active={active}, available={list(providers.keys())}")
    for pid, p in providers.items():
        check(f"models.json {pid} base_url", p.get("base_url", "").startswith("http"),
              p.get("base_url", "missing"))
        check(f"models.json {pid} models", len(p.get("models", {})) > 0,
              str(p.get("models", {})))

    # 5c. .env
    from core.config import SETTINGS
    check(".env API key", bool(SETTINGS.api_key) and len(SETTINGS.api_key) > 10)
    check(".env base_url", SETTINGS.base_url.startswith("http"))

    # 5d. No syntax errors in Python files
    import ast, glob
    syntax_errors = []
    for f in glob.glob("**/*.py", recursive=True):
        if ".git" in f or "__pycache__" in f:
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                ast.parse(fh.read(), filename=f)
        except SyntaxError as e:
            syntax_errors.append(f"{f}: {e}")
    check("Python syntax", len(syntax_errors) == 0,
          f"{len(syntax_errors)} errors: {'; '.join(syntax_errors[:3])}" if syntax_errors else "all clean")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════
def main():
    print(f"{C}{'=' * 60}{X}")
    print(f"{C}  Agnes Smart Studio — 全方位测试套件{X}")
    print(f"{C}{'=' * 60}{X}")

    start = time.time()

    # Always run local tests
    test_config_integrity()
    test_tools_direct()
    test_edge_cases()

    # AI tests (skip with --quick)
    if "--quick" not in sys.argv:
        test_ai_conversation()
        test_ai_tool_calling()
    else:
        print(f"\n{C}═══ 3-4. AI 测试跳过 (--quick) ═══{X}")

    elapsed = time.time() - start

    print(f"\n{C}{'=' * 60}{X}")
    print(f"  {G}{passed} passed{X}, {R}{failed} failed{X}, {passed + failed} total")
    print(f"  Time: {elapsed:.1f}s")
    if failed > 0:
        print(f"\n  {R}FAILURES:{X}")
        for name, detail in failures:
            print(f"    {R}{name}{X}: {detail}")
        sys.exit(1)
    else:
        print(f"  {G}ALL TESTS PASSED{X}")
        sys.exit(0)


if __name__ == "__main__":
    main()
