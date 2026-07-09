"""Tests for ConfirmCheckpoint + MCP Context"""

from core.confirm_checkpoint import (
    ConfirmCheckpoint,
    ConfirmLevel,
    ConfirmManager,
    ambiguous_intent_checkpoint,
    deploy_checkpoint,
    destructive_action_checkpoint,
    multi_step_checkpoint,
)
from core.mcp_context import (
    INTENT_TO_SCENES,
    MCP_TOOL_SCENES,
    filter_tools_by_intent,
    get_context_prompt,
)

# ─── ConfirmCheckpoint Tests ────────────────────────────


class TestConfirmCheckpoint:
    def test_creation(self):
        cp = ConfirmCheckpoint(
            id="test-1",
            title="测试确认",
            description="这是一个测试",
            level=ConfirmLevel.MEDIUM,
        )
        assert cp.id == "test-1"
        assert cp.level == ConfirmLevel.MEDIUM
        assert cp.approved is None

    def test_to_message(self):
        cp = ConfirmCheckpoint(
            id="test-1",
            title="高风险操作",
            description="即将删除文件",
            level=ConfirmLevel.HIGH,
        )
        msg = cp.to_message()
        assert "高风险操作" in msg
        assert "删除文件" in msg
        assert "确认" in msg

    def test_critical_shows_irreversible_warning(self):
        cp = ConfirmCheckpoint(
            id="test",
            title="重大变更",
            description="不可逆",
            level=ConfirmLevel.CRITICAL,
        )
        msg = cp.to_message()
        assert "不可逆" in msg

    def test_low_level_has_info_icon(self):
        cp = ConfirmCheckpoint(
            id="test",
            title="信息",
            description="x",
            level=ConfirmLevel.LOW,
        )
        msg = cp.to_message()
        assert "ℹ️" in msg


class TestConfirmManager:
    def setup_method(self):
        self.cm = ConfirmManager()

    def test_request_adds_to_pending(self):
        cp = ConfirmCheckpoint(
            id="test-1",
            title="Test",
            description="Test",
            level=ConfirmLevel.MEDIUM,
        )
        self.cm.request(cp)
        assert len(self.cm.get_pending()) == 1

    def test_resolve_moves_to_history(self):
        cp = ConfirmCheckpoint(
            id="test-1",
            title="Test",
            description="Test",
            level=ConfirmLevel.MEDIUM,
        )
        self.cm.request(cp)
        resolved = self.cm.resolve("test-1", approved=True, feedback="ok")
        assert resolved is not None
        assert resolved.approved is True
        assert resolved.user_feedback == "ok"
        assert len(self.cm.get_pending()) == 0

    def test_resolve_nonexistent_returns_none(self):
        result = self.cm.resolve("nonexistent", True)
        assert result is None

    def test_auto_resolve_expired(self):
        cp = ConfirmCheckpoint(
            id="test-1",
            title="Test",
            description="Test",
            level=ConfirmLevel.MEDIUM,
            timeout=0,
            auto_approve=True,
        )
        self.cm.request(cp)
        # Simulate creation in the past
        cp.created_at = 0
        resolved = self.cm.auto_resolve_expired()
        assert len(resolved) == 1
        assert resolved[0].approved is True

    def test_auto_resolve_without_auto_approve(self):
        cp = ConfirmCheckpoint(
            id="test-1",
            title="Test",
            description="Test",
            level=ConfirmLevel.MEDIUM,
            timeout=0,
            auto_approve=False,
        )
        self.cm.request(cp)
        cp.created_at = 0
        resolved = self.cm.auto_resolve_expired()
        assert len(resolved) == 1
        assert resolved[0].approved is False

    def test_stats(self):
        cp = ConfirmCheckpoint(
            id="test",
            title="Test",
            description="x",
            level=ConfirmLevel.MEDIUM,
        )
        self.cm.request(cp)
        self.cm.resolve("test", approved=True)
        stats = self.cm.stats()
        assert stats["total"] == 1
        assert stats["approved"] == 1
        assert stats["rejected"] == 0

    def test_get_history(self):
        for i in range(3):
            cp = ConfirmCheckpoint(
                id=f"test-{i}",
                title=f"Test {i}",
                description="x",
                level=ConfirmLevel.MEDIUM,
            )
            self.cm.request(cp)
            self.cm.resolve(f"test-{i}", approved=True)
        history = self.cm.get_history(limit=2)
        assert len(history) == 2


class TestCheckpointFactories:
    def test_destructive_action_checkpoint(self):
        cp = destructive_action_checkpoint("删除", "/tmp/test.txt")
        assert cp.level == ConfirmLevel.HIGH
        assert "删除" in cp.title
        assert "/tmp" in cp.description

    def test_deploy_checkpoint(self):
        cp = deploy_checkpoint("production", ["修改配置", "更新数据库"])
        assert cp.level == ConfirmLevel.CRITICAL
        assert "production" in cp.title
        assert "修改配置" in cp.description
        assert "更新数据库" in cp.description

    def test_ambiguous_intent_checkpoint(self):
        cp = ambiguous_intent_checkpoint(
            "这个项目有点问题",
            ["代码审查", "性能分析", "安全审计", "架构重构"],
        )
        assert cp.level == ConfirmLevel.MEDIUM
        assert cp.auto_approve is True
        assert len(cp.options) == 4
        assert "代码审查" in cp.options

    def test_multi_step_checkpoint(self):
        cp = multi_step_checkpoint(
            "代码审查",
            "发现3个问题",
            "修复问题",
        )
        assert cp.level == ConfirmLevel.LOW
        assert cp.auto_approve is True
        assert "代码审查" in cp.title
        assert "继续" in cp.options


# ─── MCP Context Tests ───────────────────────────────────


class TestMCPContext:
    def test_filter_code_tools(self):
        tools = ["run_test", "generate_image", "web_search", "run_bash"]
        filtered = filter_tools_by_intent(tools, "review")
        assert "run_test" in filtered
        assert "generate_image" not in filtered
        assert "web_search" in filtered

    def test_filter_creative_tools(self):
        tools = ["generate_image", "run_test", "comfyui_submit_workflow"]
        filtered = filter_tools_by_intent(tools, "generate")
        assert "generate_image" in filtered
        assert "comfyui_submit_workflow" in filtered
        assert "run_test" not in filtered

    def test_filter_all_tools_for_diagnose(self):
        """Diagnose needs code + infra + web"""
        tools = ["run_test", "web_search", "generate_image", "run_bash"]
        filtered = filter_tools_by_intent(tools, "diagnose")
        assert "run_test" in filtered
        assert "web_search" in filtered
        assert "run_bash" in filtered
        assert "generate_image" not in filtered

    def test_unknown_intent_defaults_to_infra(self):
        tools = ["run_bash", "generate_image"]
        filtered = filter_tools_by_intent(tools, "unknown")
        assert "run_bash" in filtered

    def test_context_prompt(self):
        prompt = get_context_prompt("generate")
        assert "creative" in prompt

    def test_context_prompt_different_intents(self):
        assert "code" in get_context_prompt("review")
        assert "web" in get_context_prompt("search")
        assert "infra" in get_context_prompt("deploy")

    def test_mcp_tool_scenes_coverage(self):
        """Ensure all major tool categories are represented"""
        scenes = set(MCP_TOOL_SCENES.values())
        assert "code" in scenes
        assert "creative" in scenes
        assert "infra" in scenes
        assert "web" in scenes
        assert "comfyui" in scenes

    def test_intent_to_scenes_coverage(self):
        """Every intent type should map to at least one scene"""
        for intent in INTENT_TO_SCENES:
            assert len(INTENT_TO_SCENES[intent]) >= 1
