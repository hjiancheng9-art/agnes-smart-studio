"""测试 RuntimeOrchestrator — 覆盖分类、dry-run、流式、能力集成."""

import os

import pytest

from core.runtime_orchestrator import (
    DNAProfile,
    OrchestrationCallbacks,
    OrchestrationError,
    OrchestrationMixin,
    OrchestrationMode,
    OrchestrationProgress,
    OrchestrationResult,
    RuntimeOrchestrator,
    classify_intent,
    execute,
    execute_stream,
    preview,
)
from core.task_complexity import TaskComplexity


@pytest.fixture(autouse=True)
def dry_run_patch(monkeypatch):
    """Prevent capability loading hangs caused by _ensure_capabilities → wire_all()."""
    monkeypatch.setenv("CRUX_DRY_RUN", "1")
    monkeypatch.setenv("CRUX_TEST_MODE", "1")

    try:
        from core.runtime_orchestrator import RuntimeOrchestrator

        original = RuntimeOrchestrator._ensure_capabilities

        def _dry_run_ensure(self, *args, **kwargs):
            if os.getenv("CRUX_DRY_RUN") == "1":
                return {"beasts": "mock_七兽已接线", "plugins": [], "skills": []}
            return original(self, *args, **kwargs)

        monkeypatch.setattr(RuntimeOrchestrator, "_ensure_capabilities", _dry_run_ensure)
    except ImportError:
        pass

    try:
        from core.capabilities import CapabilityManager

        original_wire = CapabilityManager.wire_all

        def _dry_run_wire(self, *args, **kwargs):
            if os.getenv("CRUX_DRY_RUN") == "1":
                return None
            return original_wire(self, *args, **kwargs)

        monkeypatch.setattr(CapabilityManager, "wire_all", _dry_run_wire)
    except ImportError:
        pass

    return True


class TestClassifyIntent:
    """Backward-compat classify_intent uses unified classifier under the hood."""

    def test_micro_task(self):
        g, _d = classify_intent("添加注释")
        assert g in (TaskComplexity.SIMPLE, TaskComplexity.TRIVIAL)

    def test_normal_fix(self):
        g, d = classify_intent("修复登录页拼写错误")
        assert g == TaskComplexity.MODERATE
        assert d == DNAProfile.CRUX

    def test_complex_refactor(self):
        g, _d = classify_intent("重构支付模块")
        assert g == TaskComplexity.COMPLEX

    def test_critical_architecture(self):
        g, _d = classify_intent("设计微服务架构迁移方案")
        assert g >= TaskComplexity.COMPLEX

    def test_normal_update(self):
        g, _d = classify_intent("更新用户配置")
        assert g == TaskComplexity.MODERATE

    def test_implement_codebuddy(self):
        g, _d = classify_intent("实现用户认证模块")
        assert g == TaskComplexity.COMPLEX

    def test_audit_codex(self):
        g, _d = classify_intent("安全审计代码")
        assert g >= TaskComplexity.COMPLEX

    def test_unknown_goal(self):
        g, d = classify_intent("hello world")
        assert g in (TaskComplexity.SIMPLE, TaskComplexity.TRIVIAL)
        assert d == DNAProfile.CRUX


class TestOrchestratorInit:
    def test_default_init(self):
        orch = RuntimeOrchestrator()
        assert orch.max_recovery == 3
        assert orch.max_concurrent == 8
        assert orch.mode == OrchestrationMode.AUTO

    def test_custom_init(self):
        orch = RuntimeOrchestrator(
            max_recovery=5,
            max_concurrent=4,
            skills=["actor-craft"],
            mode=OrchestrationMode.FULL,
            cost_budget_usd=10.0,
        )
        assert orch.max_recovery == 5
        assert orch.max_concurrent == 4
        assert orch.skills == ["actor-craft"]
        assert orch.mode == OrchestrationMode.FULL

    def test_callbacks(self):
        events = []
        cb = OrchestrationCallbacks(on_progress=lambda e: events.append(e.message))
        orch = RuntimeOrchestrator(callbacks=cb)
        orch._emit(OrchestrationProgress(phase="test"), "info", "hello")
        assert len(events) == 1
        assert events[0] == "hello"


class TestDryRun:
    def test_preview_returns_plan(self):
        result = preview("重构支付模块")
        assert result.verdict == "dry_run"
        assert len(result.plan_preview) >= 1
        # grade now uses TaskComplexity enum names (see commit 5d5eefd);
        # "重构支付模块" classifies as COMPLEX.
        assert result.grade in ("COMPLEX", "CRITICAL")

    def test_preview_has_steps(self):
        result = preview("实现用户认证")
        for step in result.plan_preview:
            assert "step" in step
            assert "action" in step


@pytest.mark.slow
class TestExecuteSimple:
    def test_trivial_goal(self):
        result = execute("echo hello", mode=OrchestrationMode.DRY_RUN)
        assert result.verdict in ("pass", "fail", "dry_run")

    def test_execute_returns_result(self):
        result = execute("修复拼写", mode=OrchestrationMode.DRY_RUN)
        assert isinstance(result, OrchestrationResult)
        assert result.goal == "修复拼写"

    def test_execute_sets_grade_dna(self):
        result = execute("重构支付", mode=OrchestrationMode.DRY_RUN)
        assert result.grade in ("SIMPLE", "MODERATE", "COMPLEX", "CRITICAL")
        assert result.dna in ("crux", "claude")


@pytest.mark.slow
class TestExecuteStream:
    def test_stream_yields_events(self):
        events = list(execute_stream("修复拼写错误", mode=OrchestrationMode.DRY_RUN))
        assert len(events) > 0
        for e in events:
            assert isinstance(e, OrchestrationProgress)

    def test_stream_has_beasts(self):
        events = list(execute_stream("重构支付", mode=OrchestrationMode.DRY_RUN))
        beast_events = [e for e in events if e.beast]
        assert len(beast_events) >= 1

    def test_stream_has_phases(self):
        events = list(execute_stream("添加注释", mode=OrchestrationMode.DRY_RUN))
        phases = {e.phase for e in events}
        assert "gate" in phases

    def test_to_tui(self):
        p = OrchestrationProgress(phase="execute", beast="baihu", message="test", level="info")
        style, text = p.to_tui()
        assert "baihu" in text
        assert "activity-info" in style


class TestCapabilities:
    def test_refresh_returns_dict(self):
        orch = RuntimeOrchestrator()
        caps = orch.refresh_capabilities()
        assert isinstance(caps, dict)
        assert len(caps) >= 3  # beasts, agents, pricing minimum

    def test_agent_roles_loaded(self):
        orch = RuntimeOrchestrator()
        orch._ensure_capabilities("test")
        assert len(orch._agent_roles) >= 4

    def test_select_agent_role(self):
        orch = RuntimeOrchestrator()
        orch._ensure_capabilities("test")
        role = orch._select_agent_role(DNAProfile.CLAUDE)
        assert isinstance(role, str)
        assert len(role) > 0


class TestActiveRuns:
    def test_empty_initially(self):
        orch = RuntimeOrchestrator()
        assert orch.active_runs() == []

    def test_cancel_nonexistent(self):
        orch = RuntimeOrchestrator()
        assert orch.cancel("nonexistent") is False


class TestDataModels:
    def test_error_fields(self):
        e = OrchestrationError(phase="execute", code="TEST", message="test error")
        assert e.phase == "execute"
        assert e.recoverable is True

    def test_result_defaults(self):
        r = OrchestrationResult()
        assert r.verdict == "unknown"
        assert r.steps_executed == 0
        assert r.errors == []

    def test_progress_fields(self):
        p = OrchestrationProgress(trace_id="abc", phase="plan", phase_index=3)
        assert p.total_phases == 6
        assert p.level == "info"


class TestOrchestrationMixin:
    def test_mixin_methods_exist(self):
        assert hasattr(OrchestrationMixin, "orchestrate")
        assert hasattr(OrchestrationMixin, "orchestrate_stream")
        assert hasattr(OrchestrationMixin, "_init_orchestrator")
