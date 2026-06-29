"""端到端冒烟测试 — 验证 CRUX 核心工作流。

覆盖场景：
  1. 核心模块导入完整性
  2. 事件总线创建 + 发射 + 订阅
  3. 会话管理创建/保存/恢复/删除
  4. 权限管理器三级模式切换
  5. 技能发现加载
  6. 模型路由选择
  7. 插件系统发现加载
  8. 安全脱敏功能
  9. 熔断器/恢复机制可用性
  10. 七兽 lore DNA 可导入
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class TestE2eCoreImport:
    """核心模块必须完整导入。"""

    def test_agent_imports(self):
        from core.agent import ContextManager, PlanStep, PlanExecutor, StepStatus, parse_plan
        assert ContextManager is not None

    def test_event_bus_imports(self):
        from core.event_bus import EventBus, SessionMetadata, bus, SESSION_CREATED, SESSION_CLOSED
        assert EventBus is not None
        assert SessionMetadata is not None
        assert SESSION_CREATED == "session:created"

    def test_session_mgr_imports(self):
        from core.session_mgr import session_save, session_restore, session_delete, session_list
        assert session_save is not None
        assert callable(session_list)

    def test_skill_loader_imports(self):
        from core.skill_loader import AgnetaSkillSystem, CodexSkill, SkillHeader, listZCodeSkills
        assert AgnetaSkillSystem is not None
        assert SkillHeader is not None

    def test_plugin_system_imports(self):
        from core.plugin_system import PluginManager, PluginManifest
        assert PluginManager is not None
        assert PluginManifest is not None

    def test_model_routing_imports(self):
        from core.model_routing import resolve_model, pick_best_model, ModelSpec, ProviderSpec, count_models
        assert resolve_model is not None
        assert ModelSpec is not None
        assert callable(count_models)

    def test_permission_imports(self):
        from core.permission import PermissionManager, PermissionMode, get_permission_manager
        assert PermissionManager is not None

    def test_resilience_imports(self):
        from core.resilience import SafeExecutor, ErrorClassifier, RetryPolicy, redact_sensitive
        assert SafeExecutor is not None
        assert redact_sensitive is not None

    def test_lore_dna_imports(self):
        from core.lore.zcode_dna import SCHEMA_VERSION, ZCODE_VALIDATION_PATTERNS
        from core.lore.five_beasts import SEVEN_BEASTS_PROMPT
        from core.lore.crux_dna import CRUX_DNA_SYSTEM_PROMPT
        assert SCHEMA_VERSION == "crux.zcode-dna.v1"
        assert "玄武" in SEVEN_BEASTS_PROMPT
        assert len(CRUX_DNA_SYSTEM_PROMPT) > 100

    def test_sandbox_imports(self):
        from core.sandbox import Sandbox, sandbox_check, DANGEROUS_PATTERNS, ALLOWED_ROOTS
        assert Sandbox is not None
        assert callable(sandbox_check)

    def test_provider_imports(self):
        from core.provider import get_provider_manager, get_provider_name, get_model_info
        assert get_provider_manager is not None


class TestE2eEventBusFlow:
    """事件总线完整工作流。"""

    def test_event_lifecycle(self):
        from core.event_bus import bus, SESSION_CREATED, SESSION_CLOSED, SessionMetadata

        received = []
        bus.on(SESSION_CREATED, lambda **kw: received.append(("created", kw)))
        bus.on(SESSION_CLOSED, lambda **kw: received.append(("closed", kw)))

        meta = SessionMetadata(id="e2e-test", name="E2E Test")
        bus.emit(SESSION_CREATED, **meta.to_dict())
        bus.emit(SESSION_CLOSED, session_id="e2e-test", reason="test")

        assert len(received) == 2
        assert received[0][0] == "created"
        assert received[1][0] == "closed"

    def test_metrics_tracking(self):
        from core.event_bus import bus, SESSION_CREATED, TURN_STARTED
        bus.reset_metrics()
        bus.emit(SESSION_CREATED, id="m1", name="metrics-test")
        bus.emit(TURN_STARTED)
        m = bus.get_metrics()
        assert "total_sessions" in m
        assert "total_turns" in m
        assert "tool_call_count" in m


class TestE2eSessionManager:
    """会话管理完整工作流。"""

    def test_session_crud(self):
        from core.session_mgr import session_save, session_restore, session_delete, session_list

        name = "e2e-test-session"
        messages = [{"role": "user", "content": "hello"}]

        # Save
        session_save(name, messages)

        # Restore
        restored = session_restore(name)
        assert restored is not None

        # Delete
        session_delete(name)

    def test_session_persistence_roundtrip(self):
        from core.session_mgr import session_save, session_restore, session_delete

        name = "e2e-persistence-test"
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there!"},
        ]
        session_save(name, msgs)
        restored = session_restore(name)
        session_delete(name)

        assert restored is not None
        assert len(restored) >= 1


class TestE2ePermissionSystem:
    """权限系统三级模式。"""

    def test_mode_switching(self):
        from core.permission import PermissionManager, PermissionMode

        pm = PermissionManager()
        assert pm.mode == PermissionMode.AUTO

        pm.set_mode(PermissionMode.YOLO)
        assert pm.mode == PermissionMode.YOLO

        pm.set_mode(PermissionMode.MANUAL)
        assert pm.mode == PermissionMode.MANUAL

        pm.set_mode(PermissionMode.AUTO)

    def test_needs_confirmation(self):
        from core.permission import PermissionManager, PermissionMode

        pm = PermissionManager()
        pm.set_mode(PermissionMode.YOLO)
        assert not pm.needs_confirmation("run_bash", {"command": "rm -rf /"})

        pm.set_mode(PermissionMode.MANUAL)
        # MANUAL mode may require confirmation for write tools
        result = pm.needs_confirmation("write_file", {"path": "/etc/passwd"})
        assert result is not None

    def test_remember_and_forget(self):
        from core.permission import PermissionManager

        pm = PermissionManager()
        pm.remember("git_push")
        pm.forget("git_push")
        pm.forget_all()
        assert pm.get_summary()["remembered_count"] == 0


class TestE2eSkillSystem:
    """SKILL.md 发现和加载。"""

    def test_skill_discovery(self):
        from core.skill_loader import AgnetaSkillSystem

        sys = AgnetaSkillSystem()
        sys.discover()
        skills = sys.list_skills()
        assert isinstance(skills, list)

    def test_zcode_api_aliases(self):
        from core.skill_loader import listZCodeSkills

        skills = listZCodeSkills()
        assert isinstance(skills, list)


class TestE2eModelRouting:
    """模型路由基本功能。"""

    def test_resolve_model(self):
        from core.model_routing import resolve_model, _MODEL_INDEX

        # Use the first model ID that actually exists in the catalog
        first_id = list(_MODEL_INDEX.keys())[0]
        result = resolve_model(first_id)
        assert result is not None

    def test_count_models(self):
        from core.model_routing import count_models

        stats = count_models()
        assert isinstance(stats, dict)
        assert stats.get("models", 0) > 0

    def test_resolve_unknown_model(self):
        from core.model_routing import resolve_model

        result = resolve_model("nonexistent-model-xyz-999")
        assert result is None


class TestE2ePluginSystem:
    """插件发现和加载。"""

    def test_plugin_discovery(self):
        from core.plugin_system import PluginManager

        pm = PluginManager()
        discovered = pm.discover()
        assert isinstance(discovered, list)
        assert len(discovered) >= 1  # at least superpowers

    def test_plugin_manifest_validation_valid(self):
        from core.plugin_system import PluginManifest

        m = PluginManifest(name="valid-plugin", version="1.0.0")
        ok, msg = m.validate()
        assert ok
        assert msg == "ok"

    def test_bad_plugin_name_rejected(self):
        from core.plugin_system import PluginManifest

        m = PluginManifest(name="Bad Name!", version="1.0.0")
        ok, msg = m.validate()
        assert not ok
        assert "name" in str(msg).lower() or "Bad" in str(msg)


class TestE2eSecurity:
    """安全脱敏功能验证。"""

    def test_redact_sensitive_keys(self):
        from core.resilience import redact_sensitive

        assert redact_sensitive("sk-abc123def456ghi789jkl012") == "<REDACTED>"
        assert redact_sensitive("safe text") == "safe text"

    def test_sandbox_sandbox_check(self):
        from core.sandbox import sandbox_check, DANGEROUS_PATTERNS, ALWAYS_DANGEROUS

        assert len(DANGEROUS_PATTERNS) > 0
        assert len(ALWAYS_DANGEROUS) > 0

        # Test dangerous command detection
        result = sandbox_check("rm -rf /")
        assert result is not None  # Returns a dict or similar


class TestE2eSessionMetadataSchema:
    """SessionMetadata 完整 Schema。"""

    def test_session_metadata_creation(self):
        from core.event_bus import SessionMetadata, SCHEMA_VERSION

        sm = SessionMetadata(id="s1", name="test")
        assert sm.id == "s1"
        assert sm.schema_version == SCHEMA_VERSION
        assert sm.usage_count == 0

    def test_session_metadata_touch(self):
        from core.event_bus import SessionMetadata

        sm = SessionMetadata(id="s1")
        sm.touch()
        assert sm.usage_count == 1
        assert sm.last_active is not None
        assert sm.updated_at > 0

    def test_session_metadata_roundtrip(self):
        from core.event_bus import SessionMetadata

        sm = SessionMetadata(id="s1", name="roundtrip", tags=["test", "demo"])
        d = sm.to_dict()
        restored = SessionMetadata.from_dict(d)
        assert restored.id == "s1"
        assert restored.name == "roundtrip"
        assert restored.tags == ["test", "demo"]


class TestE2eSkillHeaderSchema:
    """SkillHeader 完整 Schema。"""

    def test_skill_header_yaml_frontmatter(self):
        from core.skill_loader import SkillHeader

        sh = SkillHeader.parse("---\nname: my-skill\nversion: 1.0.0\ntags: test, demo\n---\n\n# Content")
        assert sh.name == "my-skill"
        assert sh.version == "1.0.0"
        assert "test" in sh.tags

    def test_skill_header_metadata_section(self):
        from core.skill_loader import SkillHeader

        content = """# my-skill

## Description
A test skill

## Metadata
- name: my-skill
- version: 2.0.0
- tags: test, verification
"""
        sh = SkillHeader.parse(content)
        assert sh.name == "my-skill"
        assert sh.version == "2.0.0"
        assert "test" in sh.tags

    def test_skill_header_h1_fallback(self):
        from core.skill_loader import SkillHeader

        sh = SkillHeader.parse("# fallback-skill\n\nNo metadata here\n")
        assert sh.name == "fallback-skill"
        ok, errs = sh.validate()
        assert ok


class TestE2eSafeExecutor:
    """SafeExecutor 安全执行工作流。"""

    def test_execute_success(self):
        from core.resilience import SafeExecutor

        executor = SafeExecutor()
        def hello(x):
            return f"Hello {x}"

        r = executor.execute("echo", hello, {"x": "world"})
        assert r["success"]
        assert "Hello world" in r["result"]

    def test_execute_failure_caught_exception(self):
        from core.resilience import SafeExecutor

        executor = SafeExecutor()
        def fail():
            raise ValueError("test error")

        r = executor.execute("error", fail, {})
        assert not r["success"]
        assert "error" in r

    def test_execute_redacts_api_keys(self):
        from core.resilience import SafeExecutor

        executor = SafeExecutor()
        def leak():
            return "api_key=sk-abc123def456ghi789jkl012"

        r = executor.execute("leak", leak, {})
        assert "<REDACTED>" in r["result"]
        assert "sk-abc" not in r["result"]


class TestE2eCodexSkill:
    """CodexSkill 渐进披露。"""

    def test_level1_disclosure(self):
        from core.skill_loader import CodexSkill

        skill_dir = ROOT / "skills_md"
        skills = list(skill_dir.glob("*.skill.md")) + list(skill_dir.glob("*.SKILL.md"))
        if skills:
            skill = CodexSkill(skills[0])
            l1 = skill.get_level1()
            assert len(l1) > 0
            assert skill.name in l1 or "##" in l1 or "#" in l1

    def test_level2_disclosure(self):
        from core.skill_loader import CodexSkill

        skill_dir = ROOT / "skills_md"
        skills = list(skill_dir.glob("*.skill.md")) + list(skill_dir.glob("*.SKILL.md"))
        if skills:
            skill = CodexSkill(skills[0])
            l2 = skill.get_level2()
            assert len(l2) > 0
