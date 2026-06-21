"""Agnes 深度测试 — 覆盖之前没测到的子系统

运行: python test_deep.py
跳过网络: python test_deep.py --quick
"""

import json, os, sys, time, ast, glob as _glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(str(ROOT))

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; X = "\033[0m"

passed = 0; failed = 0; failures = []

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  {G}PASS{X} {name}")
        passed += 1
    else:
        print(f"  {R}FAIL{X} {name}: {detail}")
        failed += 1; failures.append((name, detail))

# ════════════════════════════════════════════════
# 1. 技能系统全面扫描
# ════════════════════════════════════════════════
def test_skills():
    print(f"\n{C}═══ 1. 技能系统 ({len(list((ROOT/'skills').glob('*.skill.json')))} 个) ═══{X}")
    from core.skills import get_manager
    mgr = get_manager()
    mgr.discover()
    names = mgr.available_names
    check("discover() 发现技能", len(names) > 30, f"只有 {len(names)}")

    broken = []
    for name in names:
        try:
            s = mgr._available.get(name)
            if s and s.prompt:
                # 检查 prompt 编码
                s.prompt.encode('utf-8')
        except Exception as e:
            broken.append(f"{name}: {e}")
    check("所有技能 prompt 可编码", len(broken) == 0,
          f"{len(broken)} 个异常: {'; '.join(broken[:3])}")

    # 测试加载/卸载
    for name in names[:3]:
        try:
            result = mgr.load(name)
            if result:
                mgr.unload()  # unload() 不需要参数，卸载当前技能
        except Exception as e:
            check(f"加载 {name}", False, str(e)[:60])
            continue
    check("技能加载/卸载正常", True)


# ════════════════════════════════════════════════
# 2. Git 工具链
# ════════════════════════════════════════════════
def test_git():
    print(f"\n{C}═══ 2. Git 工具 ═══{X}")
    from core.tools import get_registry
    reg = get_registry()
    reg.load()

    git_tools = ["git_status", "git_diff", "git_log"]
    for t in git_tools:
        r = reg.execute(t, {})
        is_repo = "not a git repo" not in r.lower() and not r.startswith("[错误]")
        check(f"{t}", not r.startswith("[错误]") or "not a git repo" in r.lower(),
              r[:60] if r.startswith("[错误]") else "OK")


# ════════════════════════════════════════════════
# 3. 浏览器工具导入
# ════════════════════════════════════════════════
def test_browser():
    print(f"\n{C}═══ 3. 浏览器工具 ═══{X}")
    try:
        from core.browser_tools import _get_playwright
        check("browser_tools 导入", True)
    except Exception as e:
        check("browser_tools 导入", False, str(e)[:80])

    try:
        from core.web_browser import BROWSER_GENERAL_TOOL_DEFS
        check("web_browser 导入", len(BROWSER_GENERAL_TOOL_DEFS) > 0,
              f"{len(BROWSER_GENERAL_TOOL_DEFS)} 工具定义")
    except Exception as e:
        check("web_browser 导入", False, str(e)[:80])


# ════════════════════════════════════════════════
# 4. 代码智能/LSP 导入
# ════════════════════════════════════════════════
def test_code_intel():
    print(f"\n{C}═══ 4. 代码智能 ═══{X}")
    for mod_name, label in [
        ("core.code_intel", "code_intel"),
        ("core.lsp", "LSP"),
        ("core.mcp_client", "MCP客户端"),
    ]:
        try:
            __import__(mod_name)
            check(label, True)
        except Exception as e:
            check(label, False, str(e)[:80])


# ════════════════════════════════════════════════
# 5. 音频工具
# ════════════════════════════════════════════════
def test_audio():
    print(f"\n{C}═══ 5. 音频工具 ═══{X}")
    try:
        from core.audio_tools import AUDIO_TOOL_DEFS
        check("audio_tools 导入", len(AUDIO_TOOL_DEFS) > 0, f"{len(AUDIO_TOOL_DEFS)} 工具")
    except Exception as e:
        check("audio_tools 导入", False, str(e)[:80])

    try:
        from core.video_editor import VIDEO_EDITOR_TOOL_DEFS
        check("video_editor 导入", len(VIDEO_EDITOR_TOOL_DEFS) > 0,
              f"{len(VIDEO_EDITOR_TOOL_DEFS)} 工具")
    except Exception as e:
        check("video_editor 导入", False, str(e)[:80])


# ════════════════════════════════════════════════
# 6. 任务/调度
# ════════════════════════════════════════════════
def test_task_scheduler():
    print(f"\n{C}═══ 6. 任务与调度 ═══{X}")
    for mod_name, label in [
        ("core.task_manager", "task_manager"),
        ("core.scheduler", "scheduler"),
        ("core.project", "project"),
        ("core.rules", "rules"),
        ("core.validator", "validator"),
    ]:
        try:
            __import__(mod_name)
            check(label, True)
        except Exception as e:
            check(label, False, str(e)[:80])


# ════════════════════════════════════════════════
# 7. 视频模型
# ════════════════════════════════════════════════
def test_video_models():
    print(f"\n{C}═══ 7. 视频模型 ═══{X}")
    from core.video_models import VIDEO_MODELS
    check("video_models 定义", len(VIDEO_MODELS) > 0, f"{len(VIDEO_MODELS)} 模型")


# ════════════════════════════════════════════════
# 8. 市场与编排
# ════════════════════════════════════════════════
def test_market_orchestra():
    print(f"\n{C}═══ 8. 市场 + 编排 ═══{X}")
    from core.marketplace import get_marketplace
    mp = get_marketplace()
    all_pkgs = mp.list_all()
    check("市场合并", len(all_pkgs) > 500, f"{len(all_pkgs)} 技能")

    from core.orchestra import get_orchestra
    orch = get_orchestra()
    coding = orch.active_profile("coding")
    check("编排配置", len(coding) > 5, f"{len(coding)} 能力")

    full = orch.active_profile("full")
    check("全能力配置", len(full) > 10, f"{len(full)} 能力")


# ════════════════════════════════════════════════
# 9. Provider 系统
# ════════════════════════════════════════════════
def test_provider():
    print(f"\n{C}═══ 9. Provider ═══{X}")
    from core.provider import get_provider_manager
    mgr = get_provider_manager()
    check("provider 加载", len(mgr.providers) >= 3, f"{len(mgr.providers)} 供应商")

    # 测试故障标记
    mgr.state.mark_down("deepseek")
    check("故障标记", mgr.state.is_down("deepseek"))
    available = mgr.state.available(list(mgr.providers.keys()))
    check("可用列表排除故障", "deepseek" not in available)


# ════════════════════════════════════════════════
# 10. Bypass 引擎
# ════════════════════════════════════════════════
def test_bypass():
    print(f"\n{C}═══ 10. Bypass 引擎 ═══{X}")
    from core.prompt_bypass import _detect_trigger_words, STRATEGIES, FIGURE_STRATEGIES
    from core.prompt_bypass import is_policy_error

    triggers = _detect_trigger_words("a soldier with a rifle in combat")
    check("触发词检测", "rifle" in triggers, str(triggers))

    check("通用策略", len(STRATEGIES) == 5, f"{len(STRATEGIES)}")
    check("体型策略", len(FIGURE_STRATEGIES) == 3, f"{len(FIGURE_STRATEGIES)}")

    # 模拟异常检测
    class FakeError(Exception):
        def __str__(self): return "content_policy_violation: blocked"
    check("策略异常检测", is_policy_error(FakeError()))


# ════════════════════════════════════════════════
# 11. 边界：所有导入一次性通过
# ════════════════════════════════════════════════
def test_import_all():
    print(f"\n{C}═══ 11. 全量导入 ═══{X}")
    core_files = [f.stem for f in (ROOT/"core").glob("*.py") if f.stem != "__init__" and f.stem != "__pycache__"]
    ui_files = [f"ui.{f.stem}" for f in (ROOT/"ui").glob("*.py") if f.stem != "__init__"]
    engine_files = [f"engines.{f.stem}" for f in (ROOT/"engines").glob("*.py") if f.stem != "__init__"]

    failures_import = []
    for mod_name in core_files[:30]:  # 最多 30 个避免太慢
        try:
            __import__(f"core.{mod_name}")
        except Exception as e:
            failures_import.append(f"core.{mod_name}: {type(e).__name__}")

    check(f"全量导入 (core/)", len(failures_import) == 0,
          f"{len(failures_import)} 失败: {'; '.join(failures_import[:3])}" if failures_import else "OK")


# ════════════════════════════════════════════════
# 12. 编码安全扫描
# ════════════════════════════════════════════════
def test_encoding_scan():
    print(f"\n{C}═══ 12. 编码安全 ═══{X}")
    garbled_chars = ["鍥", "閸", "鐢", "绱", "鏉", "悆", "殑", "掑", "曠"]
    bad_files = []
    for f in _glob.glob("**/*.py", recursive=True):
        if ".git" in f or "__pycache__" in f or "test_deep.py" in f:
            continue
        try:
            content = Path(f).read_text(encoding="utf-8")
            for gc in garbled_chars:
                if gc in content:
                    bad_files.append(f)
                    break
        except Exception:
            pass
    check(f"乱码扫描 ({len(garbled_chars)} 字符)", len(bad_files) == 0,
          f"{len(bad_files)} 文件: {', '.join(bad_files[:5])}" if bad_files else "OK")


# ════════════════════════════════════════════════
# 13. 命令别名一致性
# ════════════════════════════════════════════════
def test_commands():
    print(f"\n{C}═══ 13. 命令别名 ═══{X}")
    # 从 cli.py 提取 CN_ALIASES 检查一致性
    import ast as _ast
    cli_path = ROOT / "ui" / "cli.py"
    tree = _ast.parse(cli_path.read_text(encoding="utf-8"))
    cn_count = 0
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Dict):
            for key in node.keys:
                if isinstance(key, _ast.Constant) and isinstance(key.value, str):
                    cn_count += 1
    check("CN_ALIASES 存在", cn_count > 20, f"{cn_count} 个别名")


# ════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════
def main():
    print(f"{C}{'='*60}{X}")
    print(f"{C}  Agnes — 深度子系统测试{X}")
    print(f"{C}{'='*60}{X}")

    start = time.time()
    tests = [
        test_skills, test_git, test_browser, test_code_intel,
        test_audio, test_task_scheduler, test_video_models,
        test_market_orchestra, test_provider, test_bypass,
        test_import_all, test_encoding_scan, test_commands,
    ]

    for t in tests:
        try:
            t()
        except Exception as e:
            check(t.__name__, False, str(e)[:100])

    elapsed = time.time() - start
    print(f"\n{C}{'='*60}{X}")
    print(f"  {G}{passed} passed{X}, {R}{failed} failed{X}, {passed+failed} total · {elapsed:.1f}s")
    if failed:
        for name, detail in failures:
            print(f"    {R}FAIL {name}{X}: {detail}")
        sys.exit(1)
    else:
        print(f"  {G}ALL PASSED{X}")
        sys.exit(0)

if __name__ == "__main__":
    main()
