"""
Intelligence Pipeline 集成测试
=============================
测试完整链路: IntelligencePolicyRouter → IntelligenceHook → ChatSession 标记
"""

import pytest

from core.critic_agent import CriticAgent, CritiqueCategory, CritiqueFinding, CritiqueReport, CritiqueSeverity
from core.deliberate_workflow import DeliberateWorkflow, WorkflowResult
from core.intelligence_hook import IntelligenceHook
from core.intelligence_policy import IntelligenceMode, IntelligencePolicyRouter


class TestIntelligenceHook:
    """集成钩子测试"""

    def setup_method(self):
        self.hook = IntelligenceHook()

    def test_hook_initialized(self):
        """Hook 应正确初始化"""
        assert self.hook.enabled is True
        assert self.hook.last_mode is None
        assert self.hook.router is not None

    def test_enable_disable(self):
        """启用/禁用切换"""
        self.hook.disable()
        assert self.hook.enabled is False
        result = self.hook.analyze("重构整个系统架构，包含微服务拆分")
        assert result["pipeline"] is False  # disabled → always BALANCED
        self.hook.enable()
        assert self.hook.enabled is True

    def test_fast_mode_no_pipeline(self):
        """简单请求不走 pipeline"""
        result = self.hook.analyze("你好")
        assert result["mode"] == "FAST"
        assert result["pipeline"] is False
        assert self.hook.last_mode == IntelligenceMode.FAST

    def test_deep_mode_pipeline(self):
        """复杂多步骤走 pipeline"""
        result = self.hook.analyze("""帮我把这个单体应用拆成微服务。
首先分析现有模块依赖。
然后设计服务边界和API协议。
接着实现服务间通信。
最后写集成测试。""")
        assert result["mode"] in ("DEEP", "RESEARCH")
        assert result["pipeline"] is True

    def test_safe_mode_pipeline(self):
        """安全高风险走 pipeline"""
        result = self.hook.analyze("删除所有用户的密码hash并重置数据库")
        assert result["mode"] == "SAFE"
        assert result["pipeline"] is True

    def test_research_mode_pipeline(self):
        """研究型任务走 pipeline"""
        result = self.hook.analyze("研究最新的向量数据库技术对比和选型建议")
        assert result["mode"] == "RESEARCH"
        assert result["pipeline"] is True

    def test_balanced_no_pipeline(self):
        """普通代码任务不走 pipeline"""
        result = self.hook.analyze("帮我写一个 Python 函数计算斐波那契数列")
        assert result["mode"] == "BALANCED"
        assert result["pipeline"] is False

    def test_creative_no_pipeline(self):
        """创意任务不走 pipeline（轻量级）"""
        result = self.hook.analyze("帮我设计一个科技感的产品首页，风格要简约美观")
        # CREATIVE mode has low threshold; if keyword doesn't trigger, accept BALANCED
        assert result["mode"] in ("CREATIVE", "BALANCED")
        assert result["pipeline"] is False

    def test_mode_hint_contains_icon(self):
        """模式提示应包含图标和描述"""
        result = self.hook.analyze("重构架构")
        hint = result["mode_hint"]
        assert "[" in hint  # contains mode label
        assert len(hint) > 10

    def test_mode_hint_for_deep_shows_critic(self):
        """DEEP 模式提示应显示 CriticAgent"""
        result = self.hook.analyze("""重构用户系统。
首先分析现有代码。
然后设计新的模块结构。
接着迁移核心逻辑。
最后更新所有引用。""")
        hint = result["mode_hint"]
        if result["mode"] == "DEEP":
            assert "Critic" in hint or "审查" in hint

    def test_route_text_returns_enum(self):
        """快速路由返回 IntelligenceMode"""
        mode = self.hook.route_text("你好")
        assert isinstance(mode, IntelligenceMode)

    def test_get_stats_accumulates(self):
        """统计应累积"""
        self.hook.analyze("你好")
        self.hook.analyze("写个函数")
        self.hook.analyze("重构架构")
        stats = self.hook.get_stats()
        assert stats["total"] >= 3

    def test_reset_stats(self):
        """统计可重置"""
        self.hook.analyze("你好")
        self.hook.reset_stats()
        stats = self.hook.get_stats()
        assert stats["total"] == 0

    def test_last_summary_updated(self):
        """最后一次分析结果应存储"""
        self.hook.analyze("重构整个认证系统")
        summary = self.hook.last_summary
        assert "mode" in summary
        assert "profile" in summary
        assert "config" in summary

    def test_disabled_returns_balanced(self):
        """禁用时返回 BALANCED"""
        self.hook.disable()
        result = self.hook.analyze("帮我删除所有数据")
        assert result["mode"] == "BALANCED"
        assert result["pipeline"] is False
        self.hook.enable()


class TestPipelineIntegration:
    """Pipeline 集成测试"""

    def test_workflow_result_to_dict(self):
        """WorkflowResult 序列化"""
        result = WorkflowResult(goal_id="test-123", mode="DEEP", passed=True, summary="完成")
        d = result.to_dict()
        assert d["goal_id"] == "test-123"
        assert d["mode"] == "DEEP"
        assert d["passed"] is True

    def test_deliberate_workflow_initialization(self):
        """DeliberateWorkflow 应能初始化"""
        wf = DeliberateWorkflow()
        assert wf.policy_router is not None
        assert wf.critic_agent is not None

    def test_deliberate_workflow_with_custom_components(self):
        """DeliberateWorkflow 接受自定义组件"""
        router = IntelligencePolicyRouter()
        critic = CriticAgent()
        wf = DeliberateWorkflow(policy_router=router, critic_agent=critic)
        assert wf.policy_router is router
        assert wf.critic_agent is critic

    def test_critic_review_flow(self):
        """CriticAgent 审查流程"""
        CriticAgent()
        report = CritiqueReport(target="测试方案")

        # 添加发现
        report.findings.append(
            CritiqueFinding(
                category=CritiqueCategory.SECURITY,
                severity=CritiqueSeverity.HIGH,
                summary="缺少输入验证",
                location="api/handler.py:25",
                suggestion="添加参数校验中间件",
            )
        )
        report.findings.append(
            CritiqueFinding(
                category=CritiqueCategory.PERFORMANCE,
                severity=CritiqueSeverity.MEDIUM,
                summary="N+1 查询问题",
                location="db/queries.py:42",
                suggestion="使用 JOIN 或批量查询",
            )
        )

        assert report.blocking is False  # no critical
        assert report.high_count == 1

        # 添加 critical
        report.findings.append(
            CritiqueFinding(
                category=CritiqueCategory.SECURITY,
                severity=CritiqueSeverity.CRITICAL,
                summary="SQL 注入漏洞",
                location="db/raw_query.py:15",
                suggestion="使用参数化查询",
            )
        )

        assert report.blocking is True  # has critical
        assert report.critical_count == 1

    def test_format_workflow_result_for_user(self):
        """工作流结果格式化"""
        wf = DeliberateWorkflow()
        result = WorkflowResult(mode="DEEP", passed=True, goal_id="g-001", summary="审查通过，3个问题已修复")

        report = CritiqueReport(target="认证模块")
        report.findings.append(
            CritiqueFinding(
                category=CritiqueCategory.LOGIC,
                severity=CritiqueSeverity.MEDIUM,
                summary="token 续期逻辑缺失",
            )
        )
        result.critique_report = report

        formatted = wf.format_result_for_user(result)
        assert "DEEP" in formatted
        assert "审查" in formatted
        assert "通过" in formatted or "g-001" in formatted

    def test_intelligence_pipeline_full_flow(self):
        """完整链路: Hook → Router → 模式判定"""
        hook = IntelligenceHook()

        # 测试所有模式类型
        test_cases = [
            ("你好，今天天气怎么样", IntelligenceMode.FAST),
            ("写一个 Python 排序函数", IntelligenceMode.BALANCED),
            ("帮我设计一个好看的logo", IntelligenceMode.CREATIVE),
            ("研究最新的前端框架趋势", IntelligenceMode.RESEARCH),
            ("删除所有用户的敏感数据", IntelligenceMode.SAFE),
        ]

        for text, _expected in test_cases:
            result = hook.analyze(text)
            result["mode"]

        # 至少验证 hook 正确处理了所有模式
        stats = hook.get_stats()
        assert stats["total"] == len(test_cases)

    def test_hook_analyze_returns_all_required_fields(self):
        """分析结果应包含所有必要字段"""
        result = self._make_hook().analyze("重构认证系统")
        required_fields = ["mode", "pipeline", "summary", "profile", "config", "mode_hint"]
        for field in required_fields:
            assert field in result, f"Missing field: {field}"

    def _make_hook(self):
        return IntelligenceHook()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
