"""Unit tests for core/skills.py — SkillManager, Skill, get_manager.

SkillManager 是启动路径模块（chat.py:29 顶层 import），坏就崩。
覆盖：发现、加载、卸载、prompt 拼接、工具注入、validate、单例。
"""
# pyright: reportOptionalMemberAccess=false

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.skills import Skill, SkillManager, get_manager

# ── 模拟 skill JSON 数据 ─────────────────────────────────────────────

VALID_SKILL = {
    "name": "test-python-expert",
    "description": "Python 编程专家技能",
    "version": "1.0",
    "prompt": "你是 Python 专家。规则：\n1. 优先使用类型注解\n2. 遵循 PEP 8",
    "icon": "🐍",
}

SKILL_WITH_TOOLS = {
    "name": "test-comfyui-bridge",
    "description": "ComfyUI 桥接技能",
    "version": "2.0",
    "prompt": "你是 ComfyUI 工作流调度专家，擅长 ComfyUI API 调用和节点配置。",
    "tools": [
        {"name": "comfyui_generate", "type": "shell", "description": "生成图片"},
        {"name": "comfyui_queue", "type": "shell", "description": "查询队列"},
    ],
}

INVALID_SKILL_NO_NAME = {"description": "缺名字", "prompt": "x" * 30}
INVALID_SKILL_SHORT_PROMPT = {"name": "too-short", "description": "prompt太短", "prompt": "hi"}


class TestSkill:
    """Skill 数据对象基础测试。"""

    def test_skill_from_dict(self, tmp_path):
        f = tmp_path / "test.skill.json"
        f.write_text(json.dumps(VALID_SKILL), encoding="utf-8")
        skill = Skill(VALID_SKILL, f)
        assert skill.name == "test-python-expert"
        assert skill.description == "Python 编程专家技能"
        assert skill.version == "1.0"
        assert "Python 专家" in skill.prompt
        assert skill.icon == "🐍"
        assert skill.tools == []
        assert skill.file == f

    def test_skill_defaults_from_minimal_dict(self, tmp_path):
        minimal = {"prompt": "x" * 30}
        f = tmp_path / "minimal.skill.json"
        f.write_text(json.dumps(minimal), encoding="utf-8")
        skill = Skill(minimal, f)
        assert skill.name == "minimal.skill"  # .stem strips only last suffix (.json)
        assert skill.description == ""
        assert skill.version == "1.0"
        assert skill.tools == []

    def test_skill_repr(self, tmp_path):
        f = tmp_path / "repr.skill.json"
        f.write_text(json.dumps(VALID_SKILL), encoding="utf-8")
        skill = Skill(VALID_SKILL, f)
        assert "test-python-expert" in repr(skill)
        assert "Skill" in repr(skill)


class TestSkillManagerDiscover:
    """SkillManager.discover() — 技能发现。"""

    def test_discover_finds_skill_files(self, tmp_path):
        (tmp_path / "a.skill.json").write_text(json.dumps(VALID_SKILL), encoding="utf-8")
        (tmp_path / "b.skill.json").write_text(json.dumps(SKILL_WITH_TOOLS), encoding="utf-8")
        mgr = SkillManager(skills_dir=tmp_path)
        result = mgr.discover()
        assert len(result) == 2
        assert "test-python-expert" in result
        assert "test-comfyui-bridge" in result

    def test_discover_skips_invalid_json(self, tmp_path):
        (tmp_path / "valid.skill.json").write_text(json.dumps(VALID_SKILL), encoding="utf-8")
        (tmp_path / "broken.skill.json").write_text("{bad json", encoding="utf-8")
        mgr = SkillManager(skills_dir=tmp_path)
        result = mgr.discover()
        assert len(result) == 1  # only valid one
        assert "valid" not in result  # name is test-python-expert, not "valid"

    def test_discover_creates_missing_dir(self, tmp_path):
        new_dir = tmp_path / "nonexistent" / "nested"
        mgr = SkillManager(skills_dir=new_dir)
        result = mgr.discover()
        assert new_dir.exists()
        assert len(result) == 0

    def test_discover_empty_dir(self, tmp_path):
        mgr = SkillManager(skills_dir=tmp_path)
        result = mgr.discover()
        assert len(result) == 0
        assert mgr.available_names == []


class TestSkillManagerLoadUnload:
    """SkillManager.load / unload — 技能加载与卸载。"""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.tmp = tmp_path
        (tmp_path / "expert.skill.json").write_text(json.dumps(VALID_SKILL), encoding="utf-8")
        self.mgr = SkillManager(skills_dir=tmp_path)

    def test_load_returns_skill(self):
        skill = self.mgr.load("test-python-expert")
        assert skill is not None
        assert skill.name == "test-python-expert"

    def test_load_sets_loaded_property(self):
        self.mgr.load("test-python-expert")
        assert self.mgr.loaded is not None
        assert self.mgr.loaded.name == "test-python-expert"

    def test_load_unknown_returns_none(self):
        skill = self.mgr.load("nonexistent-skill")
        assert skill is None
        assert self.mgr.loaded is None

    def test_unload_clears_loaded(self):
        self.mgr.load("test-python-expert")
        self.mgr.unload()
        assert self.mgr.loaded is None

    def test_load_overwrites_previous(self):
        (self.tmp / "other.skill.json").write_text(json.dumps(SKILL_WITH_TOOLS), encoding="utf-8")
        self.mgr.load("test-python-expert")
        self.mgr.load("test-comfyui-bridge")
        assert self.mgr.loaded.name == "test-comfyui-bridge"


class TestSkillManagerPromptAndTools:
    """SkillManager.get_system_prompt / get_extra_tools — prompt 拼接和工具注入。"""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        (tmp_path / "skill.skill.json").write_text(json.dumps(SKILL_WITH_TOOLS), encoding="utf-8")
        self.mgr = SkillManager(skills_dir=tmp_path)

    def test_get_system_prompt_without_loaded_returns_base(self):
        result = self.mgr.get_system_prompt("base prompt here")
        assert result == "base prompt here"

    def test_get_system_prompt_with_loaded_appends_skill(self):
        self.mgr.load("test-comfyui-bridge")
        result = self.mgr.get_system_prompt("base prompt")
        assert "base prompt" in result
        assert "[Skill 激活: test-comfyui-bridge]" in result
        assert "ComfyUI" in result

    def test_get_system_prompt_empty_skill_prompt_returns_base(self, tmp_path):
        empty_prompt = {**VALID_SKILL, "prompt": "   "}
        (tmp_path / "empty.skill.json").write_text(json.dumps(empty_prompt), encoding="utf-8")
        mgr = SkillManager(skills_dir=tmp_path)
        mgr.load("test-python-expert")
        assert mgr.get_system_prompt("base") == "base"

    def test_get_extra_tools_without_loaded_returns_empty(self):
        assert self.mgr.get_extra_tools() == []

    def test_get_extra_tools_with_loaded_returns_tools(self):
        self.mgr.load("test-comfyui-bridge")
        tools = self.mgr.get_extra_tools()
        assert len(tools) == 2
        assert tools[0]["name"] == "comfyui_generate"
        assert tools[1]["name"] == "comfyui_queue"


class TestSkillManagerValidate:
    """SkillManager.validate() — 技能文件结构验证。"""

    def test_validate_all_valid(self, tmp_path):
        (tmp_path / "a.skill.json").write_text(json.dumps(VALID_SKILL), encoding="utf-8")
        (tmp_path / "b.skill.json").write_text(json.dumps(SKILL_WITH_TOOLS), encoding="utf-8")
        mgr = SkillManager(skills_dir=tmp_path)
        result = mgr.validate()
        assert len(result["passed"]) == 2
        assert len(result["failed"]) == 0

    def test_validate_catches_missing_name(self, tmp_path):
        (tmp_path / "bad.skill.json").write_text(json.dumps(INVALID_SKILL_NO_NAME), encoding="utf-8")
        mgr = SkillManager(skills_dir=tmp_path)
        result = mgr.validate()
        assert len(result["failed"]) == 1
        assert "缺少 name" in result["failed"][0]["errors"]

    def test_validate_catches_short_prompt(self, tmp_path):
        (tmp_path / "short.skill.json").write_text(json.dumps(INVALID_SKILL_SHORT_PROMPT), encoding="utf-8")
        mgr = SkillManager(skills_dir=tmp_path)
        result = mgr.validate()
        assert len(result["failed"]) == 1
        assert "prompt 过短" in result["failed"][0]["errors"][0]

    def test_validate_catches_broken_json(self, tmp_path):
        (tmp_path / "broken.skill.json").write_text("not json{{", encoding="utf-8")
        mgr = SkillManager(skills_dir=tmp_path)
        result = mgr.validate()
        assert len(result["failed"]) == 1
        assert "Invalid JSON" in result["failed"][0]["error"]


class TestSkillManagerSingleton:
    """get_manager() 单例行为。"""

    def test_get_manager_returns_skill_manager(self):
        mgr = get_manager()
        assert isinstance(mgr, SkillManager)

    def test_get_manager_returns_same_instance(self):
        assert get_manager() is get_manager()
