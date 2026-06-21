"""Tests for core.multi_agent — parallel multi-agent task coordination."""



class TestAgentTask:
    """AgentTask dataclass defaults."""

    def test_minimal_construction(self):
        from core.multi_agent import AgentTask
        t = AgentTask(id="t1", description="do thing")
        assert t.id == "t1"
        assert t.description == "do thing"
        assert t.tool_sequence == []
        assert t.depends_on == []
        assert t.status == "pending"
        assert t.result == ""

    def test_full_construction(self):
        from core.multi_agent import AgentTask
        t = AgentTask(
            id="t2", description="complex",
            tool_sequence=[{"tool": "x", "args": {}}],
            depends_on=["t1"],
        )
        assert t.tool_sequence == [{"tool": "x", "args": {}}]
        assert t.depends_on == ["t1"]


class TestAgent:
    """Agent dataclass."""

    def test_defaults(self):
        from core.multi_agent import Agent
        a = Agent(id="a1", role="reviewer")
        assert a.id == "a1"
        assert a.role == "reviewer"
        assert a.status == "idle"
        assert a.current_task == ""


class TestCoordinatorInit:
    """MultiAgentCoordinator construction."""

    def test_requires_tool_executor(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        assert callable(coord.execute_tool)

    def test_default_max_workers(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        assert coord.max_workers == 4

    def test_custom_max_workers(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok", max_workers=2)
        assert coord.max_workers == 2

    def test_starts_empty(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        assert coord.agents == []
        assert coord.tasks == []


class TestSpawnTeam:
    """spawn_team() creates agent roster."""

    def test_default_roles(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        coord.spawn_team()
        roles = [a.role for a in coord.agents]
        assert "reviewer" in roles
        assert "debugger" in roles
        assert "implementer" in roles
        assert "tester" in roles

    def test_custom_roles(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        coord.spawn_team(["alpha", "beta"])
        assert len(coord.agents) == 2
        assert coord.agents[0].role == "alpha"

    def test_respects_max_workers(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok", max_workers=2)
        coord.spawn_team(["a", "b", "c", "d"])
        assert len(coord.agents) == 2  # capped at max_workers


class TestDecompose:
    """decompose() breaks goals into tasks by pattern."""

    def test_review_pattern(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        tasks = coord.decompose("review the code")
        assert len(tasks) >= 3
        # Dependency chain exists
        dependent = [t for t in tasks if t.depends_on]
        assert len(dependent) > 0

    def test_debug_pattern(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        tasks = coord.decompose("debug the failing test")
        assert len(tasks) >= 3

    def test_default_pattern(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        tasks = coord.decompose("analyze performance")
        assert len(tasks) >= 3
        # First task should be independent (no depends_on)
        assert tasks[0].depends_on == []

    def test_each_task_has_tool_sequence(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        tasks = coord.decompose("review code")
        for t in tasks:
            assert len(t.tool_sequence) >= 1


class TestExecute:
    """execute() runs the full coordination pipeline."""

    def test_execute_returns_result_dict(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        result = coord.execute("review the code")
        assert isinstance(result, dict)
        assert "goal" in result
        assert "tasks_total" in result
        assert "tasks_done" in result
        assert "elapsed" in result

    def test_execute_with_working_tools(self):
        from core.multi_agent import MultiAgentCoordinator

        def executor(tool, args):
            return f"executed {tool}"

        coord = MultiAgentCoordinator(executor)
        result = coord.execute("investigate architecture")
        assert result["tasks_total"] >= 3
        assert result["tasks_done"] >= 1

    def test_execute_logs_decomposition(self):
        from core.multi_agent import MultiAgentCoordinator
        coord = MultiAgentCoordinator(lambda t, a: "ok")
        result = coord.execute("review code")
        log_events = [e["event"] for e in result["log"]]
        assert "decomposed" in log_events

    def test_failed_task_marks_status(self):
        from core.multi_agent import MultiAgentCoordinator

        def failing_executor(tool, args):
            raise RuntimeError("boom")

        coord = MultiAgentCoordinator(failing_executor)
        result = coord.execute("review code")
        assert result["tasks_failed"] == result["tasks_total"]


class TestCoordinateFunction:
    """Module-level coordinate() helper."""

    def test_coordinate_runs_pipeline(self):
        from core.multi_agent import coordinate
        result = coordinate("review code", lambda t, a: "ok")
        assert isinstance(result, dict)
        assert "tasks_total" in result
