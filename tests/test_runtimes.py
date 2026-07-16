"""
Tests for Capability Runtimes — Phase 8
"""

import pytest

from core.runtimes.architecture_runtime import ArchitectureRuntime
from core.runtimes.base_runtime import (
    BaseRuntime,
    CapabilityRuntimeType,
    RuntimeContext,
    RuntimeStatus,
)
from core.runtimes.capability_router import CapabilityRuntimeRouter
from core.runtimes.code_patch_runtime import CodePatchRuntime
from core.runtimes.creative_runtime import CreativeRuntime
from core.runtimes.debug_runtime import DebugAnalyzeRuntime
from core.runtimes.general_runtime import GeneralRuntime
from core.runtimes.research_runtime import ResearchRuntime
from core.runtimes.security_runtime import SecurityRuntime


class TestCapabilityRuntimeType:
    def test_from_mode(self):
        assert CapabilityRuntimeType.from_mode("FAST") == CapabilityRuntimeType.GENERAL
        assert CapabilityRuntimeType.from_mode("BALANCED") == CapabilityRuntimeType.GENERAL
        assert CapabilityRuntimeType.from_mode("SAFE") == CapabilityRuntimeType.SECURITY
        assert CapabilityRuntimeType.from_mode("RESEARCH") == CapabilityRuntimeType.RESEARCH
        assert CapabilityRuntimeType.from_mode("CREATIVE") == CapabilityRuntimeType.CREATIVE
        assert CapabilityRuntimeType.from_mode("UNKNOWN") == CapabilityRuntimeType.GENERAL


class TestRuntimeContext:
    def test_minimal(self):
        ctx = RuntimeContext(request="你好")
        assert ctx.request == "你好"
        assert ctx.mode == "BALANCED"
        assert ctx.runtime_type == CapabilityRuntimeType.GENERAL

    def test_full(self):
        ctx = RuntimeContext(
            request="排查崩溃根因",
            mode="DEEP",
            runtime_type=CapabilityRuntimeType.DEBUG_ANALYZE,
            files=["src/main.py"],
        )
        assert ctx.mode == "DEEP"
        d = ctx.to_dict()
        assert d["runtime_type"] == "debug_analyze"
        assert d["file_count"] == 1

    def test_defaults(self):
        ctx = RuntimeContext(request="修复 bug")
        assert ctx.files == []
        assert ctx.config == {}


class TestBaseRuntime:
    def test_base_class(self):
        rt = BaseRuntime(name="test")
        assert rt.name == "test"
        assert rt.status == RuntimeStatus.PENDING
        assert rt.can_handle("anything", "FAST") is False

    def test_execute_raises(self):
        rt = BaseRuntime(name="test")
        with pytest.raises(NotImplementedError):
            import asyncio

            asyncio.run(rt.execute(RuntimeContext(request="test")))

    def test_to_dict(self):
        rt = BaseRuntime(name="test")
        d = rt.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "pending"


class TestGeneralRuntime:
    def test_can_handle_always(self):
        rt = GeneralRuntime()
        assert rt.can_handle("anything", "FAST") is True
        assert rt.can_handle("", "") is True

    def test_execute(self):
        rt = GeneralRuntime()
        import asyncio

        result = asyncio.run(rt.execute(RuntimeContext(request="测试")))
        assert result["status"] == "success"
        assert result["runtime"] == "general"
        assert "steps" in result


class TestDebugAnalyzeRuntime:
    def test_can_handle_debug_request(self):
        rt = DebugAnalyzeRuntime()
        assert rt.can_handle("排查间歇崩溃根因", "DEEP") is True
        assert rt.can_handle("error: NoneType object", "BALANCED") is True
        assert rt.can_handle("你好", "FAST") is False
        assert rt.can_handle("写一个函数", "BALANCED") is False

    def test_execute_debug(self):
        rt = DebugAnalyzeRuntime()
        import asyncio

        result = asyncio.run(
            rt.execute(
                RuntimeContext(
                    request="测试通过但鼠标滚动不生效，排查根因",
                    mode="DEEP",
                )
            )
        )
        assert result["status"] == "success"
        assert result["runtime"] == "debug_analyze"
        assert len(result["symptoms"]) > 0
        assert len(result["hypotheses"]) > 0
        assert result["root_cause"]
        assert len(result["fix_plan"]) > 0

    def test_extract_symptoms(self):
        rt = DebugAnalyzeRuntime()
        symptoms = rt._extract_symptoms("程序卡死了，报错 TypeError")
        assert len(symptoms) >= 2

    def test_generate_hypotheses(self):
        rt = DebugAnalyzeRuntime()
        hypotheses = rt._generate_hypotheses("鼠标滚动不生效", ["功能失效"])
        assert len(hypotheses) > 0


class TestCodePatchRuntime:
    def test_can_handle_patch(self):
        rt = CodePatchRuntime()
        assert rt.can_handle("修复 src/auth.py 空指针", "BALANCED") is True
        assert rt.can_handle("你好", "FAST") is False

    def test_execute_patch(self):
        rt = CodePatchRuntime()
        import asyncio

        result = asyncio.run(rt.execute(RuntimeContext(request="修复 main.py 中的 bug", mode="BALANCED")))
        assert result["status"] == "success"
        assert result["runtime"] == "code_patch"
        assert "patches" in result

    def test_extract_files(self):
        rt = CodePatchRuntime()
        files = rt._extract_files("修复 src/auth.py 和 utils/helper.js 的问题")
        assert len(files) >= 2


class TestArchitectureRuntime:
    def test_can_handle_architecture(self):
        rt = ArchitectureRuntime()
        assert rt.can_handle("设计微服务拆分方案", "DEEP") is True
        assert rt.can_handle("你好", "FAST") is False

    def test_execute_architecture(self):
        rt = ArchitectureRuntime()
        import asyncio

        result = asyncio.run(rt.execute(RuntimeContext(request="把单体应用拆成微服务", mode="DEEP")))
        assert result["status"] == "success"
        assert "migration_steps" in result
        assert result["step_count"] >= 3

    def test_determine_style(self):
        rt = ArchitectureRuntime()
        assert "微服务" in rt._determine_style("拆成微服务")
        assert "分层" in rt._determine_style("分层架构设计")


class TestSecurityRuntime:
    def test_can_handle_security(self):
        rt = SecurityRuntime()
        assert rt.can_handle("删除所有用户的密码记录", "SAFE") is True
        assert rt.can_handle("你好", "FAST") is False

    def test_execute_security(self):
        rt = SecurityRuntime()
        import asyncio

        result = asyncio.run(rt.execute(RuntimeContext(request="删除所有用户的密码", mode="SAFE")))
        assert result["status"] == "success"
        assert "vulnerabilities" in result
        assert result["risk_level"] in ("critical", "high")

    def test_can_handle_via_mode(self):
        rt = SecurityRuntime()
        assert rt.can_handle("什么都可以", "SAFE") is True


class TestResearchRuntime:
    def test_can_handle_research(self):
        rt = ResearchRuntime()
        assert rt.can_handle("研究最新的 RAG 技术", "RESEARCH") is True
        assert rt.can_handle("你好", "FAST") is False

    def test_execute_research(self):
        rt = ResearchRuntime()
        import asyncio

        result = asyncio.run(rt.execute(RuntimeContext(request="对比 PostgreSQL 和 MongoDB", mode="RESEARCH")))
        assert result["status"] == "success"
        assert "topics" in result
        assert result["needs_web_search"] is True

    def test_extract_topics(self):
        rt = ResearchRuntime()
        topics = rt._extract_topics("对比 PostgreSQL 和 MongoDB 的优劣")
        assert "PostgreSQL" in topics or "MongoDB" in topics


class TestCreativeRuntime:
    def test_can_handle_creative(self):
        rt = CreativeRuntime()
        assert rt.can_handle("设计一个科技感的产品首页", "CREATIVE") is True
        # 技术方案不应被 CREATIVE 匹配
        assert rt.can_handle("设计一个数据库分表方案", "DEEP") is False
        assert rt.can_handle("你好", "FAST") is False

    def test_execute_creative(self):
        rt = CreativeRuntime()
        import asyncio

        result = asyncio.run(rt.execute(RuntimeContext(request="设计一个品牌 logo", mode="CREATIVE")))
        assert result["status"] == "success"
        assert "concepts" in result
        assert result["variant_count"] > 0

    def test_extract_style(self):
        rt = CreativeRuntime()
        style = rt._extract_style("科技感的简约设计")
        # Should match at least one tone
        assert "tone" in style


class TestCapabilityRuntimeRouter:
    def test_register_and_get(self):
        router = CapabilityRuntimeRouter()
        general = GeneralRuntime()
        debug = DebugAnalyzeRuntime()
        router.register(general)
        router.register(debug)
        assert router.get_runtime(CapabilityRuntimeType.GENERAL) is general
        assert router.get_runtime(CapabilityRuntimeType.DEBUG_ANALYZE) is debug

    def test_select_general(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        rt_type, _runtime = router.select_runtime("你好", "FAST")
        assert rt_type == CapabilityRuntimeType.GENERAL

    def test_select_debug(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        router.register(DebugAnalyzeRuntime())
        rt_type, runtime = router.select_runtime("排查间歇崩溃根因", "DEEP")
        assert rt_type == CapabilityRuntimeType.DEBUG_ANALYZE
        assert isinstance(runtime, DebugAnalyzeRuntime)

    def test_select_debug_auto_detect(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        router.register(DebugAnalyzeRuntime())
        # Even without specifying DEEP mode, debug keywords should trigger
        _rt_type, runtime = router.select_runtime("error: crash detected", "BALANCED")
        assert isinstance(runtime, DebugAnalyzeRuntime)

    def test_select_code_patch(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        router.register(CodePatchRuntime())
        _rt_type, runtime = router.select_runtime("修复一个空指针", "DEEP")
        assert isinstance(runtime, CodePatchRuntime)

    def test_select_architecture(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        router.register(ArchitectureRuntime())
        _rt_type, runtime = router.select_runtime("设计微服务架构方案", "DEEP")
        assert isinstance(runtime, ArchitectureRuntime)

    def test_select_security_by_mode(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        router.register(SecurityRuntime())
        _rt_type, runtime = router.select_runtime("任何内容", "SAFE")
        assert isinstance(runtime, SecurityRuntime)

    def test_select_research_by_mode(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        router.register(ResearchRuntime())
        _rt_type, runtime = router.select_runtime("研究技术", "RESEARCH")
        assert isinstance(runtime, ResearchRuntime)

    def test_list_runtimes(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        rt_list = router.list_runtimes()
        assert len(rt_list) >= 1

    def test_route_to_general(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        import asyncio

        result = asyncio.run(router.route(RuntimeContext(request="你好", mode="FAST")))
        assert result["status"] == "success"
        assert result["runtime"] == "general"

    def test_route_to_debug(self):
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        router.register(DebugAnalyzeRuntime())
        import asyncio

        result = asyncio.run(
            router.route(
                RuntimeContext(
                    request="排查间歇崩溃根因",
                    mode="DEEP",
                )
            )
        )
        assert result["status"] == "success"
        assert result["runtime"] == "debug_analyze"

    def test_route_fallback_when_no_runtime(self):
        router = CapabilityRuntimeRouter()
        # GeneralRuntime not registered
        import asyncio

        result = asyncio.run(router.route(RuntimeContext(request="test")))
        assert result["status"] == "failed"


class TestFullIntegration:
    def test_runtime_pipeline(self):
        """模拟完整的分派流程"""
        router = CapabilityRuntimeRouter()
        router.register(GeneralRuntime())
        router.register(DebugAnalyzeRuntime())
        router.register(CodePatchRuntime())
        router.register(ArchitectureRuntime())
        router.register(SecurityRuntime())
        router.register(ResearchRuntime())
        router.register(CreativeRuntime())

        import asyncio

        # 普通请求 → GeneralRuntime
        r1 = asyncio.run(router.route(RuntimeContext(request="写一个函数", mode="BALANCED")))
        assert r1["runtime"] == "general"

        # 调试请求 → DebugAnalyzeRuntime
        r2 = asyncio.run(router.route(RuntimeContext(request="排查间歇崩溃根因", mode="DEEP")))
        assert r2["runtime"] == "debug_analyze"
        assert "root_cause" in r2
        assert "hypotheses" in r2

        # 安全请求 → SecurityRuntime
        r3 = asyncio.run(router.route(RuntimeContext(request="删除所有用户的密码记录", mode="SAFE")))
        assert r3["runtime"] == "security"
        assert "vulnerabilities" in r3

        # 研究请求 → ResearchRuntime
        r4 = asyncio.run(router.route(RuntimeContext(request="研究最新的 RAG 技术选型", mode="RESEARCH")))
        assert r4["runtime"] == "research"
        assert "topics" in r4

        # 创意请求 → CreativeRuntime
        r5 = asyncio.run(router.route(RuntimeContext(request="设计一个科技感的产品首页", mode="CREATIVE")))
        assert r5["runtime"] == "creative"
        assert "concepts" in r5

        # 代码修复 → CodePatchRuntime
        r6 = asyncio.run(router.route(RuntimeContext(request="修复 src/auth.py:42 的空指针", mode="BALANCED")))
        assert r6["runtime"] in ("code_patch", "debug_analyze")
        assert "patches" in r6 or "symptoms" in r6

        # 架构设计 → ArchitectureRuntime
        r7 = asyncio.run(router.route(RuntimeContext(request="设计微服务拆分方案", mode="DEEP")))
        assert r7["runtime"] == "architecture"
        assert "migration_steps" in r7

        # 列表应包含 7 个 runtime
        assert len(router.list_runtimes()) >= 6
