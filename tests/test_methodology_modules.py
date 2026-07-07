"""方法论补齐模块 + brain拆分 + 性能优化 单元测试

覆盖:
- quest_engine     — 任务状态机、依赖链、自动触发
- workbuddy        — 报告生成/导出/模板
- repo_wiki        — 知识库CRUD/搜索/导入
- adr_engine       — 架构决策记录/时间线
- tdd_workflow     — 测试驱动开发流程
- retro_engine     — 复盘记录/模式分析
- ci_pipeline      — 流水线创建/执行
- artifact_pipeline — 制品存储/提升
- rollback_engine  — 灰度发布/回滚
- fast_scanner     — 高性能文件搜索
- mcp_client       — 健康检查/自动重连
- brain拆分        — Mixin方法正确路由
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 清理测试数据 ──
def _clean_output_dirs():
    """Clean test output dirs before each test group."""
    import shutil
    for d in ["output/quests", "output/reports", "output/report_templates",
              "output/pipelines", "output/artifacts", "output/releases",
              "output/backups", "output/retros", "docs/adr"]:
        p = Path(d)
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════
# 1. Quest 引擎
# ════════════════════════════════════════════════════════════

def test_quest_create():
    _clean_output_dirs()
    from core.quest_engine import quest_create, quest_list, quest_load

    q = quest_create("test", steps=[{"name": "s1", "action": "do"}], tags=["test"])
    assert q["status"] == "pending"
    assert q["id"] == "test"
    assert len(q["steps"]) == 1

    loaded = quest_load("test")
    assert loaded is not None
    assert loaded["id"] == "test"

    lst = quest_list(tag="test")
    assert len(lst) >= 1


def test_quest_dependency():
    _clean_output_dirs()
    from core.quest_engine import quest_complete, quest_create, quest_load, quest_start

    # Create and complete a dependency first
    quest_create("dependency-1", tags=["dep"])
    quest_start("dependency-1")
    quest_complete("dependency-1", "ok")
    assert quest_load("dependency-1")["status"] == "done"

    # Now create a quest that depends on it - should NOT be blocked since dep is done
    main = quest_create("main-quest", depends_on=["dependency-1"])
    assert main["status"] == "pending", f"Expected pending, got {main['status']}"

    # Create a quest that depends on a NONEXISTENT quest - should be blocked
    blocked = quest_create("blocked-quest", depends_on=["ghost-dep"])
    assert blocked["status"] == "blocked", f"Expected blocked, got {blocked['status']}"


def test_quest_lifecycle():
    _clean_output_dirs()
    from core.quest_engine import quest_complete, quest_create, quest_list, quest_start

    quest_create("lifecycle", steps=[{"name": "step1", "action": "a"}, {"name": "step2", "action": "b"}])
    quest_start("lifecycle")
    quest_complete("lifecycle", "all done")

    done_list = quest_list(status="done")
    assert any(d["id"] == "lifecycle" for d in done_list)


# ════════════════════════════════════════════════════════════
# 2. WorkBuddy 报告
# ════════════════════════════════════════════════════════════

def test_report_create():
    _clean_output_dirs()
    from core.workbuddy import report_create, report_list

    r = report_create("测试报告", [
        {"heading": "概述", "content": "测试内容", "type": "text"},
        {"heading": "数据", "content": "表数据", "type": "table"},
    ], tags=["test"])

    assert r["title"] == "测试报告"
    assert r["word_count"] > 0
    assert len(r["sections"]) == 2

    lst = report_list(tag="test")
    assert len(lst) >= 1


def test_report_export():
    _clean_output_dirs()
    from core.workbuddy import report_create, report_export

    r = report_create("导出测试", [{"heading": "H1", "content": "C1", "type": "text"}])
    md = report_export(r["id"], "markdown")
    assert md["status"] == "ok"
    assert md["format"] == "markdown"
    assert Path(md["path"]).exists()

    html = report_export(r["id"], "html")
    assert html["status"] == "ok"
    assert html["format"] == "html"


def test_template():
    _clean_output_dirs()
    from core.workbuddy import template_create, template_list

    t = template_create("简报", [{"heading": "总结", "type": "text", "description": "项目总结"}])
    assert t["name"] == "简报"

    lst = template_list()
    assert any(t2["name"] == "简报" for t2 in lst)


# ════════════════════════════════════════════════════════════
# 3. Repo Wiki
# ════════════════════════════════════════════════════════════

def test_wiki_crud():
    _clean_output_dirs()
    from core.repo_wiki import wiki_create, wiki_delete, wiki_list, wiki_read

    w = wiki_create("测试页面", "**markdown** 内容", category="测试", tags=["test"])
    assert w["title"] == "测试页面"

    read = wiki_read(w["id"])
    assert read is not None
    assert "markdown" in read["content"]

    lst = wiki_list(category="测试")
    assert any(p["id"] == w["id"] for p in lst)

    wiki_delete(w["id"])
    assert wiki_read(w["id"]) is None


def test_wiki_search():
    _clean_output_dirs()
    from core.repo_wiki import wiki_create, wiki_search

    wiki_create("Python教程", "Python 是一种编程语言", category="技术")
    wiki_create("Java教程", "Java 也是一种语言", category="技术")

    results = wiki_search("Python")
    assert len(results) >= 1
    assert any("Python教程" in r["title"] for r in results)


# ════════════════════════════════════════════════════════════
# 4. ADR 架构决策
# ════════════════════════════════════════════════════════════

def test_adr():
    _clean_output_dirs()
    from core.adr_engine import adr_create, adr_list, adr_mermaid, adr_update

    a = adr_create("测试决策", "需要决定", "选择方案A", "性能提升50%", status="proposed")
    assert a["id"].startswith("ADR-")
    assert a["status"] == "proposed"

    updated = adr_update(a["id"], status="accepted")
    assert updated["status"] == "accepted"

    lst = adr_list()
    assert len(lst) >= 1

    mermaid = adr_mermaid()
    assert "gantt" in mermaid or "No ADRs" in mermaid


# ════════════════════════════════════════════════════════════
# 5. TDD 工作流
# ════════════════════════════════════════════════════════════

def test_tdd():
    _clean_output_dirs()
    from core.tdd_workflow import tdd_start, tdd_status

    t = tdd_start("测试驱动", test_files=["tests/test_tdd.py"])
    assert t["phase"] == "red"
    assert t["feature"] == "测试驱动"

    status = tdd_status(t["id"])
    assert status["phase"] == "red"

    all_sessions = tdd_status()
    assert "sessions" in all_sessions


# ════════════════════════════════════════════════════════════
# 6. Retro 复盘
# ════════════════════════════════════════════════════════════

def test_retro():
    _clean_output_dirs()
    from core.retro_engine import retro_create, retro_list, retro_summarize

    r = retro_create("项目A", sprint="S1",
                     what_went_well=["团队协作好", "代码质量高"],
                     what_could_improve=["沟通效率"],
                     action_items=[{"task": "改进沟通", "owner": "PM"}])
    assert r["project"] == "项目A"
    assert len(r["what_went_well"]) == 2

    lst = retro_list(project="项目A")
    assert len(lst) >= 1

    retro_create("项目A", sprint="S2", what_went_well=["自动化测试"])
    summary = retro_summarize("项目A")
    assert "top_strengths" in summary


# ════════════════════════════════════════════════════════════
# 7. CI Pipeline
# ════════════════════════════════════════════════════════════

def test_ci_pipeline():
    from core.ci_pipeline import pipeline_create, pipeline_list

    p = pipeline_create("单元测试", stages=["lint"])
    assert p["id"] == "单元测试"
    assert p["status"] == "pending"

    lst = pipeline_list()
    assert any(p2["id"] == "单元测试" for p2 in lst)


# ════════════════════════════════════════════════════════════
# 8. Artifact Pipeline
# ════════════════════════════════════════════════════════════

def test_artifact():
    _clean_output_dirs()
    from core.artifact_pipeline import artifact_list, artifact_promote, artifact_store

    # Create test files
    Path("output/test_artifacts").mkdir(parents=True, exist_ok=True)
    Path("output/test_artifacts/build.zip").write_text("test")

    a = artifact_store("build-001", ["output/test_artifacts/build.zip"], {"commit": "abc123"})
    assert a["build_id"] == "build-001"
    assert a["stage"] == "dev"

    lst = artifact_list("build-001")
    assert len(lst) >= 1

    promoted = artifact_promote("build-001", "staging")
    assert promoted["stage"] == "staging"


# ════════════════════════════════════════════════════════════
# 9. Rollback Engine
# ════════════════════════════════════════════════════════════

def test_release():
    _clean_output_dirs()
    from core.rollback_engine import release_create, release_list, release_rollback, release_rollout

    r = release_create("crux", "2.0.0", files=[], rollout_percent=25, description="灰度测试")
    assert r["version"] == "2.0.0"
    assert r["rollout_percent"] == 25

    rolled = release_rollout(r["id"], 100)
    assert rolled["status"] == "deployed"

    rolled_back = release_rollback(r["id"])
    assert rolled_back["status"] == "rolled_back"

    lst = release_list()
    assert any(r2["id"] == r["id"] for r2 in lst)


# ════════════════════════════════════════════════════════════
# 10. Fast Scanner
# ════════════════════════════════════════════════════════════

def test_fast_scanner():
    from core.fast_scanner import count_files, fast_glob

    files = fast_glob("*.py")
    assert len(files) > 0
    assert all(f.endswith(".py") for f in files)

    n = count_files(".", ".py")
    assert n > 0


def test_fast_scanner_excludes():
    from core.fast_scanner import fast_glob

    # Should NOT include node_modules
    files = fast_glob("*.js")
    for f in files:
        assert "node_modules" not in f, f"node_modules should be excluded: {f}"


# ════════════════════════════════════════════════════════════
# 11. MCP Health Check
# ════════════════════════════════════════════════════════════

def test_mcp_health():
    from core.mcp_client import get_mcp_client

    mc = get_mcp_client()

    # health_check_all should return without error
    results = mc.health_check_all()
    assert isinstance(results, list)
    for r in results:
        assert "name" in r
        assert "status" in r


# ════════════════════════════════════════════════════════════
# 12. Brain Mixin Dispatch
# ════════════════════════════════════════════════════════════

def test_brain_mixin_import():
    from core.brain import SmartBrain

    # Verify SmartBrain is importable with Mixin architecture
    mro = [c.__name__ for c in SmartBrain.__mro__]
    assert mro[0] == "SmartBrain"
    # Mixin classes should be in the MRO
    mixin_names = [c.__name__ for c in SmartBrain.__mro__ if 'Mixin' in c.__name__]
    assert len(mixin_names) >= 1, f"Expected at least 1 Mixin in MRO, got: {mro}"


def test_brain_mixin_methods():
    from core.brain import SmartBrain

    # Key methods from each mixin should be accessible
    mixin_methods = [
        "_match_combat_moves",     # combat
        "creative_leap",           # creative
        "_infer_entity_type",      # aesthetics
        "entity_graft",            # vision
        "enhance_image_prompt",    # core
        "_ask_brain",              # core
    ]
    for name in mixin_methods:
        assert hasattr(SmartBrain, name), f"SmartBrain missing {name}"


def test_brain_combat_mixin():
    from core.brain import SmartBrain

    # Methods originally from combat mixin are now in monolithic SmartBrain
    methods = [m for m in dir(SmartBrain) if not m.startswith("__")]
    assert "_match_combat_moves" in methods
    assert "_detect_combat_scene" in methods


def test_brain_creative_mixin():
    from core.brain import SmartBrain

    methods = [m for m in dir(SmartBrain) if not m.startswith("__")]
    assert "creative_leap" in methods


def test_brain_aesthetics_mixin():
    from core.brain import SmartBrain

    methods = [m for m in dir(SmartBrain) if not m.startswith("__")]
    assert "_match_sweet_spot" in methods


def test_brain_vision_mixin():
    from core.brain import SmartBrain

    methods = [m for m in dir(SmartBrain) if not m.startswith("__")]
    assert "entity_graft" in methods


# ════════════════════════════════════════════════════════════
# 13. AsyncSmartBrain preserved
# ════════════════════════════════════════════════════════════

def test_async_smartbrain():
    from core.brain import AsyncSmartBrain

    assert hasattr(AsyncSmartBrain, "enhance_image_prompt")
    assert hasattr(AsyncSmartBrain, "understand_image")
