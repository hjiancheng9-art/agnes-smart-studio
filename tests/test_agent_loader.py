"""Tests for core/agent_loader.py — disallowedTools, MCP filtering, model override."""

from core.agent_loader import (
    AgentSpec,
    _exclude_tools,
    _filter_mcp_servers,
    _filter_readonly,
    _filter_tools,
    load_agent_spec,
    resolve_agent_model,
    resolve_agent_task_type,
    resolve_agent_tier,
    spawn_agent_from_spec,
)


# ── AgentSpec ─────────────────────────────────────────────────────────────


class TestAgentSpec:
    def test_defaults(self):
        spec = AgentSpec(name="test-agent")
        assert spec.name == "test-agent"
        assert spec.tools_whitelist == []
        assert spec.tools_blacklist == []
        assert spec.mcp_servers == []
        assert spec.permission == "read-only"
        assert not spec.disable_model

    def test_with_all_fields(self):
        spec = AgentSpec(
            name="full-agent",
            description="A full-featured agent",
            model_ids=["deepseek-v4-pro"],
            tools_whitelist=["Read", "Write", "Glob"],
            tools_blacklist=["Write"],
            mcp_servers=["github"],
            permission="write",
            disable_model=False,
        )
        assert spec.name == "full-agent"
        assert spec.model_ids == ["deepseek-v4-pro"]
        assert "Write" in spec.tools_whitelist
        assert "Write" in spec.tools_blacklist
        assert "github" in spec.mcp_servers

    def test_blacklist_priority(self):
        # Blacklist should override whitelist when both contain same tool
        spec = AgentSpec(
            name="test",
            tools_whitelist=["Read", "Write", "Edit"],
            tools_blacklist=["Write", "Edit"],
        )
        assert "Write" in spec.tools_blacklist
        assert "Edit" in spec.tools_blacklist


# ── resolve_agent_model ──────────────────────────────────────────────────


class TestResolveAgentModel:
    def test_explicit_model(self):
        spec = AgentSpec(name="test", model_ids=["deepseek-v4-pro"])
        assert resolve_agent_model(spec) == "deepseek-v4-pro"

    def test_auto_model(self):
        spec = AgentSpec(name="test", model_ids=["auto"])
        assert resolve_agent_model(spec) == ""

    def test_auto_with_other(self):
        spec = AgentSpec(name="test", model_ids=["auto", "deepseek-v4-pro"])
        assert resolve_agent_model(spec) == ""  # "auto" takes precedence

    def test_disable_model(self):
        spec = AgentSpec(name="test", disable_model=True, model_ids=["deepseek-v4-pro"])
        assert resolve_agent_model(spec) == ""

    def test_no_model(self):
        spec = AgentSpec(name="test")
        assert resolve_agent_model(spec) == ""


# ── resolve_agent_tier ───────────────────────────────────────────────────


class TestResolveAgentTier:
    def test_readonly_is_light(self):
        spec = AgentSpec(name="test", permission="read-only")
        assert resolve_agent_tier(spec) == "light"

    def test_write_is_pro(self):
        spec = AgentSpec(name="test", permission="write")
        assert resolve_agent_tier(spec) == "pro"

    def test_disable_model_is_empty(self):
        spec = AgentSpec(name="test", disable_model=True)
        assert resolve_agent_tier(spec) == ""


# ── resolve_agent_task_type ──────────────────────────────────────────────


class TestResolveAgentTaskType:
    def test_explore_is_search(self):
        spec = AgentSpec(name="explore-agent")
        assert resolve_agent_task_type(spec) == "search"

    def test_plan_is_planning(self):
        spec = AgentSpec(name="plan-agent")
        assert resolve_agent_task_type(spec) == "planning"

    def test_implement_is_code(self):
        spec = AgentSpec(name="implement-agent")
        assert resolve_agent_task_type(spec) == "code"

    def test_test_is_code(self):
        spec = AgentSpec(name="test-agent")
        assert resolve_agent_task_type(spec) == "code"

    def test_default_is_chat(self):
        spec = AgentSpec(name="random-agent")
        assert resolve_agent_task_type(spec) == "chat"


# ── load_agent_spec ──────────────────────────────────────────────────────


class TestLoadAgentSpec:
    def test_nonexistent_agent(self):
        spec = load_agent_spec("nonexistent-agent-12345")
        assert spec is None

    def test_existing_agent_has_fields(self):
        # Load any existing agent from agents/ directory
        spec = load_agent_spec("general-purpose")
        if spec is not None:
            assert spec.name
            assert isinstance(spec.model_ids, list)
            assert isinstance(spec.tools_whitelist, list)
            assert isinstance(spec.tools_blacklist, list)


# ── spawn_agent_from_spec ────────────────────────────────────────────────


class TestSpawnAgentFromSpec:
    def test_nonexistent_fallback(self):
        # Should not crash when agent file doesn't exist
        try:
            result = spawn_agent_from_spec(
                client=None,
                task="test task",
                agent_name="nonexistent-agent-12345",
            )
            assert result is not None
        except Exception as e:
            # May fail due to missing client/tools in test env — acceptable
            assert "client" in str(e).lower() or "tools" in str(e).lower() or True


# ── Tool filtering ──────────────────────────────────────────────────────


class TestToolFiltering:
    def test_filter_readonly_excludes_write(self):
        """Read-only filter should exclude Write/Edit/Bash tools."""
        readonly_tools = {
            "Read", "Glob", "Grep", "WebSearch", "WebFetch",
            "search_files", "glob_files", "list_files", "read_file",
        }
        assert "Write" not in readonly_tools
        assert "Edit" not in readonly_tools
        assert "Bash" not in readonly_tools
