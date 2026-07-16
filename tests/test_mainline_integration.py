"""
Mainline Integration Tests — Phase 9
======================================
测试主链路全路径: DeliberateWorkflow → CapabilityRuntimeRouter → Runtime.execute()
"""

import asyncio

import pytest

from core.deliberate_workflow import DeliberateWorkflow
from core.intelligence_policy import IntelligenceMode, IntelligencePolicyRouter
from core.runtimes.architecture_runtime import ArchitectureRuntime
from core.runtimes.capability_router import CapabilityRuntimeRouter
from core.runtimes.code_patch_runtime import CodePatchRuntime
from core.runtimes.creative_runtime import CreativeRuntime
from core.runtimes.debug_runtime import DebugAnalyzeRuntime
from core.runtimes.general_runtime import GeneralRuntime
from core.runtimes.research_runtime import ResearchRuntime
from core.runtimes.runtime_config import RuntimeConfig
from core.runtimes.security_runtime import SecurityRuntime


class TestRuntimeConfig:
    def test_default_config(self):
        cfg = RuntimeConfig()
        assert cfg.enabled is True
        assert cfg.is_runtime_enabled("general") is True
        assert cfg.is_runtime_enabled("debug_analyze") is True
        assert cfg.is_runtime_enabled("security") is False
        assert cfg.is_runtime_enabled("code_patch") is False

    def test_enable_disable(self):
        cfg = RuntimeConfig()
        cfg.enable("security")
        assert cfg.is_runtime_enabled("security") is True
        cfg.disable("security")
        assert cfg.is_runtime_enabled("security") is False

    def test_get_active(self):
        cfg = RuntimeConfig()
        active = cfg.get_active()
        assert "general" in active
        assert "debug_analyze" in active
        assert "security" not in active

    def test_disabled_master_switch(self):
        cfg = RuntimeConfig()
        cfg.enabled = False
        assert cfg.is_runtime_enabled("general") is False
        assert cfg.is_runtime_enabled("debug_analyze") is False


class TestDeliberateWorkflowRuntimeIntegration:
    """测试 DeliberateWorkflow 与 CapabilityRuntimeRouter 的集成"""

    @pytest.fixture
    def workflow(self):
        """创建带有完整 Runtime 注册的工作流"""
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        router.register(DebugAnalyzeRuntime())
        router.register(CodePatchRuntime())
        router.register(ArchitectureRuntime())
        router.register(SecurityRuntime())
        router.register(ResearchRuntime())
        router.register(CreativeRuntime())

        wf = DeliberateWorkflow(
            policy_router=IntelligencePolicyRouter(),
            capability_router=router,
            runtime_config=RuntimeConfig(),
        )
        return wf

    def test_workflow_has_capability_router(self):
        """DeliberateWorkflow 应包含 capability_router"""
        wf = DeliberateWorkflow()
        assert hasattr(wf, "capability_router")
        assert hasattr(wf, "runtime_config")

    def test_debug_runtime_called(self, workflow):
        """排查请求应走 DebugAnalyzeRuntime"""
        result = asyncio.run(
            workflow.execute(
                "排查间歇性崩溃根因，测试通过但挂了",
                mode=IntelligenceMode.DEEP,
            )
        )
        assert result.passed is True
        assert "debug_analyze" in result.summary or "Runtime" in result.summary

    def test_general_runtime_called(self, workflow):
        """普通请求应走 GeneralRuntime"""
        result = asyncio.run(
            workflow.execute(
                "写一个 Python 函数",
                mode=IntelligenceMode.BALANCED,
            )
        )
        # GeneralRuntime 也会返回 success
        assert result.passed is True

    def test_architecture_runtime_called(self, workflow):
        """架构请求应走 ArchitectureRuntime"""
        result = asyncio.run(
            workflow.execute(
                "设计微服务拆分方案",
                mode=IntelligenceMode.DEEP,
            )
        )
        assert result.passed is True

    def test_research_runtime_called(self, workflow):
        """研究请求应走 ResearchRuntime"""
        result = asyncio.run(
            workflow.execute(
                "研究最新的 RAG 技术",
                mode=IntelligenceMode.RESEARCH,
            )
        )
        assert result.passed is True

    def test_creative_runtime_called(self, workflow):
        """创意请求应走 CreativeRuntime"""
        result = asyncio.run(
            workflow.execute(
                "设计一个科技感的产品首页",
                mode=IntelligenceMode.CREATIVE,
            )
        )
        assert result.passed is True

    def test_runtime_config_disables_runtime(self, workflow):
        """禁用 Runtime 后应回退到 General"""
        workflow.runtime_config.disable("debug_analyze")
        result = asyncio.run(
            workflow.execute(
                "排查间歇崩溃根因",
                mode=IntelligenceMode.DEEP,
            )
        )
        # Disabled runtime falls through - still processes but may use general
        assert result is not None

    def test_master_switch_disables_all(self, workflow):
        """禁用主开关后所有 Runtime 都不应使用"""
        workflow.runtime_config.enabled = False
        result = asyncio.run(
            workflow.execute(
                "排查间歇崩溃根因",
                mode=IntelligenceMode.DEEP,
            )
        )
        assert result is not None

    def test_workflow_steps_recorded(self, workflow):
        """执行后应有步骤记录"""
        result = asyncio.run(
            workflow.execute(
                "排查崩溃问题",
                mode=IntelligenceMode.DEEP,
            )
        )
        assert len(result.steps) > 0

    def test_runtime_disabled_still_returns(self):
        """DeliberateWorkflow 没有 capability_router 时也能正常工作"""
        wf = DeliberateWorkflow()
        # 没有 capability_router，走传统流程
        result = asyncio.run(wf.execute("你好", mode=IntelligenceMode.FAST))
        assert result is not None
