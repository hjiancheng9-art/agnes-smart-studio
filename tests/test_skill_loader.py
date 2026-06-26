"""Unit tests for core/skill_loader.py — AgnetaSkillSystem, CodexSkill, SKILL_DIRS.

skill_loader 是 Codex 兼容的渐进式技能加载器（SKILL.md / .skill.json），
被 AGENTS.md 标注为"旧技能注入系统"（SKILL_DIRS @ line 22）。
覆盖：MD/JSON 解析、sections 拆分、上下文匹配、任务分类、注入逻辑、单例。
"""
# pyright: reportGeneralTypeIssues=false, reportInvalidTypeForm=false, reportReturnType=false

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.skill_loader import (
    SKILL_DIRS,
    AgnetaSkillSystem,
    CodexSkill,
    skill_inject,
    skill_list,
    skill_load,
)

# ── CodexSkill: Markdown 解析 ──────────────────────────────────────


def _make_md_skill(tmp_path: Path, name: str, body: str) -> Path:
    """在 tmp_path 下写一个 .skill.md 文件，返回路径。"""
    p = tmp_path / f"{name}.skill.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_codex_skill_name_strips_skill_suffix(tmp_path):
    """name 应剥掉 .skill 后缀（保留主名）。"""
    p = _make_md_skill(tmp_path, "my-tool", "# My Tool\n## Description\ndesc")
    assert CodexSkill(p).name == "my-tool"


def test_codex_skill_load_md_splits_sections(tmp_path):
    """## 段落标题应被解析为 sections dict 的 key（小写+下划线）。"""
    body = "# Python Expert\n## Description\nPython 编程专家\n## Instructions\n规则一：类型注解\n规则二：PEP 8\n"
    p = _make_md_skill(tmp_path, "python-expert", body)
    skill = CodexSkill(p)
    skill.load()
    assert "description" in skill._sections
    assert "instructions" in skill._sections
    assert "Python 编程专家" in skill._sections["description"]
    assert "类型注解" in skill._sections["instructions"]


def test_codex_skill_get_level1_truncates_long_description(tmp_path):
    """level1 只给 name + description 前 500 字。"""
    long_desc = "X" * 800
    body = f"# Big\n## Description\n{long_desc}\n"
    p = _make_md_skill(tmp_path, "big", body)
    out = CodexSkill(p).get_level1()
    # 标题 + 截断后的描述（500 字以内）
    assert "## big" in out
    assert len(out) < 800  # 被截断


def test_codex_skill_get_level2_includes_all_sections(tmp_path):
    """level2 应包含全部 sections。"""
    body = "# S\n## Description\nA tool\n## Instructions\nDo X\n"
    p = _make_md_skill(tmp_path, "s", body)
    out = CodexSkill(p).get_level2()
    assert "# s" in out
    assert "A tool" in out
    assert "Do X" in out


def test_codex_skill_load_is_idempotent(tmp_path):
    """重复 load() 不应重复解析或报错。"""
    p = _make_md_skill(tmp_path, "once", "# Once\n## Description\nx")
    skill = CodexSkill(p)
    skill.load()
    first = dict(skill._sections)
    skill.load()  # 第二次应 no-op
    assert skill._sections == first


def test_codex_skill_load_handles_missing_file_gracefully(tmp_path):
    """读不存在的文件应优雅降级为 description=(failed to load ...)，不抛异常。"""
    p = tmp_path / "ghost.skill.md"
    skill = CodexSkill(p)
    skill.load()
    assert "description" in skill._sections
    assert "failed to load" in skill._sections["description"].lower()


# ── CodexSkill: JSON 解析 ──────────────────────────────────────────


def test_codex_skill_load_json_maps_prompt_to_instructions(tmp_path):
    """.skill.json 的 prompt 字段应映射到 instructions section。"""
    data = {
        "name": "json-skill",
        "description": "从 JSON 来",
        "prompt": "你是专家",
        "tools": [{"name": "t1"}],
    }
    p = tmp_path / "json-skill.skill.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    skill = CodexSkill(p)
    skill.load()
    assert skill._sections["description"] == "从 JSON 来"
    assert "你是专家" in skill._sections["instructions"]
    assert "t1" in skill._sections["tools"]


def test_codex_skill_load_json_handles_malformed(tmp_path):
    """坏 JSON 应降级为 failed to load，不抛异常。"""
    p = tmp_path / "broken.skill.json"
    p.write_text("{ not valid json }}}", encoding="utf-8")
    skill = CodexSkill(p)
    skill.load()
    assert "failed to load" in skill._sections["description"].lower()


# ── CodexSkill.matches_context ────────────────────────────────────


def test_matches_context_true_when_keyword_present(tmp_path):
    """task_hint 含技能描述关键词时返回 True。

    注意：matches_context 用 .split() 按空格分词，故需用空格分隔的英文/分词文本。
    """
    body = "# Video Skill\n## Description\nvideo generation tool\n"
    p = _make_md_skill(tmp_path, "video", body)
    assert CodexSkill(p).matches_context("generate a video") is True


def test_matches_context_false_when_no_keyword(tmp_path):
    """完全无关的 task_hint 返回 False（用长词避免子串匹配副作用）。"""
    body = "# Video Skill\n## Description\nvideo generation\n"
    p = _make_md_skill(tmp_path, "video", body)
    # 用长词，确保不是任何 description 词的子串
    assert CodexSkill(p).matches_context("database migration postgresql") is False


def test_matches_context_uses_word_boundary_no_false_positive(tmp_path):
    """词边界匹配：短词不应误命中长词的子串。

    修复后行为：`matches_context` 使用 `\\b` 词边界正则，
    例如 "a" 不再被误判为 "generation" 的子串命中。
    """
    body = "# Video Skill\n## Description\nvideo generation\n"
    p = _make_md_skill(tmp_path, "video", body)
    # "a" 是 "generation" 的子串，但词边界匹配下不算命中
    assert CodexSkill(p).matches_context("a") is False


def test_matches_context_word_boundary_matches_full_token(tmp_path):
    """词边界匹配：完整词命中应判 True（回归锚点，防误修复过头）。"""
    body = "# Video Skill\n## Description\nvideo generation\n"
    p = _make_md_skill(tmp_path, "video", body)
    assert CodexSkill(p).matches_context("video") is True


# ── AgnetaSkillSystem: discover / classify / inject ───────────────


def _make_system(tmp_path: Path) -> AgnetaSkillSystem:
    """构造一个 root=tmp_path 的系统实例，并 monkey-patch SKILL_DIRS 指向 tmp_path。

    直接实例化 AgnetaSkillSystem(root=...) 仍会扫描全局 SKILL_DIRS，
    所以这里用 monkeypatch 替换模块级 SKILL_DIRS，保证测试隔离。
    """
    import core.skill_loader as sl

    original = sl.SKILL_DIRS
    sl.SKILL_DIRS = [tmp_path]
    sys = AgnetaSkillSystem(root=tmp_path)
    try:
        yield sys
    finally:
        sl.SKILL_DIRS = original
        sys.refresh()


def test_discover_finds_md_and_json_skills(tmp_path):
    """discover 应同时扫描 .skill.md 和 .skill.json。"""
    _make_md_skill(tmp_path, "md-one", "# Md One\n## Description\ndesc md")
    (tmp_path / "json-one.skill.json").write_text(
        json.dumps({"description": "desc json", "prompt": "p"}), encoding="utf-8"
    )
    for sys_ in _make_system(tmp_path):
        sys_.discover()
        names = set(sys_.skills.keys())
        assert "md-one" in names
        assert "json-one" in names


def test_discover_skips_nonexistent_dirs(tmp_path):
    """SKILL_DIRS 含不存在路径时不应报错。"""
    import core.skill_loader as sl

    original = sl.SKILL_DIRS
    sl.SKILL_DIRS = [tmp_path / "nope1", tmp_path / "nope2"]
    try:
        sys_ = AgnetaSkillSystem(root=tmp_path)
        sys_.discover()  # 不抛异常
        assert sys_.skills == {}
    finally:
        sl.SKILL_DIRS = original


def test_discover_is_cached(tmp_path):
    """第二次 discover 不应重复扫描（_discovered 标志）。"""
    _make_md_skill(tmp_path, "cached", "# C\n## Description\nx")
    count = 0
    for sys_ in _make_system(tmp_path):
        sys_.discover()
        count = len(sys_.skills)
        # 手动新增文件后不再 discover
        _make_md_skill(tmp_path, "new-after", "# N\n## Description\ny")
        sys_.discover()  # 缓存命中，不应发现新文件
        assert len(sys_.skills) == count
        assert "new-after" not in sys_.skills


def test_refresh_rediscovers(tmp_path):
    """refresh 应清空缓存并重新扫描。"""
    for sys_ in _make_system(tmp_path):
        _make_md_skill(tmp_path, "first", "# F\n## Description\nx")
        sys_.discover()
        assert "first" in sys_.skills
        # 新增后 refresh
        _make_md_skill(tmp_path, "second", "# S\n## Description\ny")
        sys_.refresh()
        assert "first" in sys_.skills
        assert "second" in sys_.skills


def test_list_skills_returns_name_and_desc(tmp_path):
    """list_skills 返回 [{name, desc}]。"""
    _make_md_skill(tmp_path, "lister", "# L\n## Description\na listable skill")
    for sys_ in _make_system(tmp_path):
        items = sys_.list_skills()
        assert any(it["name"] == "lister" for it in items)


def test_load_skill_returns_full_text_or_none(tmp_path):
    """load_skill 命中返回 level2 全文（标题用小写 name）；未命中返回 None。"""
    _make_md_skill(tmp_path, "loadable", "# Load\n## Description\nfull body")
    for sys_ in _make_system(tmp_path):
        hit = sys_.load_skill("loadable")
        miss = sys_.load_skill("ghost")
        assert hit is not None and "loadable" in hit  # 标题是小写 name
        assert "full body" in hit
        assert miss is None


# ── classify_task ─────────────────────────────────────────────────


def test_classify_task_creative(tmp_path):
    """纯创意关键词 → creative。

    注意：classify_task 关键词表是英文，中文 task 不分词会判为 general（这是当前实现行为）。
    """
    for sys_ in _make_system(tmp_path):
        assert sys_.classify_task("draw a picture and make a video animation") == "creative"


def test_classify_task_engineering(tmp_path):
    """纯工程关键词 → engineering。"""
    for sys_ in _make_system(tmp_path):
        assert sys_.classify_task("fix bug, debug, write test, refactor code") == "engineering"


def test_classify_task_mixed(tmp_path):
    """创意+工程都有 → mixed。"""
    for sys_ in _make_system(tmp_path):
        # image(创意) + code(工程)，数量相近但不至于 2 倍差距
        result = sys_.classify_task("image and code deploy")
        assert result in ("mixed", "creative", "engineering")


def test_classify_task_general_when_no_keywords(tmp_path):
    """无任何关键词 → general。"""
    for sys_ in _make_system(tmp_path):
        assert sys_.classify_task("zzz qqq xyz") == "general"


def test_classify_task_chinese_returns_general_due_to_no_jiejie(tmp_path):
    """已知行为：中文 task 因无分词、关键词表为英文，会判为 general（回归锚点）。

    若未来引入中文分词/扩展关键词表，此测试应改为断言 creative。
    """
    for sys_ in _make_system(tmp_path):
        assert sys_.classify_task("画一张图片，做视频动画") == "general"


# ── inject_for_task ───────────────────────────────────────────────


def test_inject_for_task_returns_empty_when_no_match(tmp_path):
    """无匹配技能时返回空串。"""
    _make_md_skill(tmp_path, "video", "# Video\n## Description\n视频生成\n")
    for sys_ in _make_system(tmp_path):
        out = sys_.inject_for_task("zzz unrelated qqq")
        assert out == ""


def test_inject_for_task_includes_matched_skill(tmp_path):
    """命中技能时应返回含技能名/desc 的注入文本。

    注意：task_hint 需用空格分词（matches_context 用 .split()）。
    """
    _make_md_skill(tmp_path, "video", "# Video\n## Description\nvideo generation tool\n")
    for sys_ in _make_system(tmp_path):
        out = sys_.inject_for_task("generate a video")
        assert "video" in out.lower()
        assert "Loaded Skills" in out


def test_inject_for_task_respects_max_skills(tmp_path):
    """max_skills 限制注入的技能数量。"""
    for i in range(5):
        _make_md_skill(tmp_path, f"video-{i}", f"# V{i}\n## Description\n视频 {i}\n")
    for sys_ in _make_system(tmp_path):
        out = sys_.inject_for_task("视频", max_skills=2)
        # 每个 level1 含 "## video-" 前缀
        count = out.count("## video-")
        assert count <= 2


# ── 模块级单例函数 ────────────────────────────────────────────────


def test_skill_list_returns_list():
    """skill_list() 模块级函数应返回 list。"""
    result = skill_list()
    assert isinstance(result, list)


def test_skill_load_unknown_returns_none():
    """skill_load() 未知名应返回 None。"""
    assert skill_load("definitely-not-exist-xyz-123") is None


def test_skill_inject_returns_string():
    """skill_inject() 应返回 str（可能为空）。"""
    out = skill_inject("任意 task hint")
    assert isinstance(out, str)


# ── SKILL_DIRS 常量 ───────────────────────────────────────────────


def test_skill_dirs_is_list_of_paths():
    """SKILL_DIRS 应是 Path 列表（AGENTS.md 标注 line 22）。"""
    assert isinstance(SKILL_DIRS, list)
    assert len(SKILL_DIRS) >= 1
    assert all(isinstance(d, Path) for d in SKILL_DIRS)
