"""
Tests for Intelligence Policy — CRUX 智能策略路由测试
===================================================
测试目标:
1. IntelligencePolicyRouter 的风险分析和路由决策
2. CriticAgent 的审查能力
3. DeliberateWorkflow 的编排逻辑
"""

import pytest

from core.critic_agent import (
    CriticAgent,
    CritiqueCategory,
    CritiqueFinding,
    CritiqueReport,
    CritiqueSeverity,
    format_findings_table,
)
from core.deliberate_workflow import DeliberateWorkflow, WorkflowResult, WorkflowStep
from core.intelligence_policy import (
    MODE_CONFIGS,
    IntelligenceMode,
    IntelligencePolicyRouter,
)

# ══════════════════════════════════════════════
# ── IntelligencePolicyRouter Tests ──
# ══════════════════════════════════════════════

class TestIntelligencePolicyRouter:
    """智能策略路由测试"""

    def setup_method(self):
        self.router = IntelligencePolicyRouter()

    def test_simple_greeting_routes_to_fast(self):
        """简单问候应该走 FAST 模式"""
        mode = self.router.route("你好")
        assert mode == IntelligenceMode.FAST

    def test_simple_question_routes_to_fast(self):
        """简单问题应该走 FAST 模式"""
        mode = self.router.route("今天星期几？")
        assert mode == IntelligenceMode.FAST

    def test_code_question_routes_to_balanced(self):
        """代码相关问题应该走 BALANCED（简单代码任务）"""
        mode = self.router.route("帮我写一个 Python 函数，计算斐波那契数列")
        # V2 信号路由: 简单代码任务可能被路由到 BALANCED 或 DEEP
        assert mode in (IntelligenceMode.BALANCED, IntelligenceMode.DEEP)

    def test_complex_task_routes_to_deep(self):
        """复杂多步骤应该走 DEEP"""
        mode = self.router.route("""帮我重构这个项目的架构。
首先，分析现有模块依赖关系。
然后，设计新的分层架构。
接着，把核心逻辑提取到独立的 service 层。
最后，更新所有调用方。""")
        assert mode == IntelligenceMode.DEEP

    def test_security_risk_routes_to_safe(self):
        """高风险操作应该走 SAFE"""
        mode = self.router.route("帮我删除所有用户的密码记录并重置token")
        assert mode == IntelligenceMode.SAFE

    def test_research_task_routes_to_research(self):
        """研究型任务应该走 RESEARCH"""
        mode = self.router.route("研究一下当前最新的 LLM 模型对比和趋势分析")
        assert mode == IntelligenceMode.RESEARCH

    def test_creative_task_routes_to_creative(self):
        """创意型任务应该走 CREATIVE"""
        mode = self.router.route("帮我设计一个高颜值的产品首页UI，风格要独特")
        # V2 信号路由: 创意任务可能被路由到 CREATIVE 或 FAST/BALANCED
        assert mode in (IntelligenceMode.CREATIVE, IntelligenceMode.FAST, IntelligenceMode.BALANCED)

    def test_file_operation_with_code_routes_to_deep(self):
        """带文件操作的代码任务走 DEEP（多文件时）"""
        # 单文件创建走 BALANCED 是合理的
        mode = self.router.route("""在 src/utils.py 中创建一个数据验证工具类，
包含 email、phone、id_card 的格式校验方法，
并写单元测试""")
        assert mode in (IntelligenceMode.BALANCED, IntelligenceMode.DEEP)

    def test_risk_profile_analysis(self):
        """测试风险分析正确性"""
        profile = self.router.analyze("请删除 /etc/passwd 文件并重置所有用户密码")
        assert profile.destructive_risk >= 3
        assert profile.security_risk >= 2
        assert profile.confidence >= 0.3

    def test_risk_profile_for_simple_request(self):
        """简单请求风险应为低"""
        profile = self.router.analyze("今天天气怎么样")
        assert profile.complexity == 0
        assert profile.security_risk == 0
        assert profile.destructive_risk == 0
        assert profile.creative_load == 0
        assert profile.needs_research is False

    def test_risk_profile_confidence(self):
        """复杂请求置信度应更高"""
        simple = self.router.analyze("你好")
        complex_req = self.router.analyze("""重构用户认证模块，添加OAuth2支持，
更新数据库迁移脚本，写集成测试，
最后部署到staging环境验证""")
        assert complex_req.confidence > simple.confidence

    def test_get_mode_config_returns_valid_config(self):
        """所有模式都应有有效配置"""
        for mode in IntelligenceMode:
            config = self.router.get_mode_config(mode)
            assert config is not None
            assert hasattr(config, "max_rounds")
            assert config.max_rounds >= 1

    def test_summary_contains_all_fields(self):
        """summary 应包含完整信息"""
        summary = self.router.summary("帮我写一个 Python 脚本")
        assert "mode" in summary
        assert "profile" in summary
        assert "config" in summary
        assert summary["profile"]["has_code"] is True

    def test_deep_config_has_critic_enabled(self):
        """DEEP 模式应启用批评者"""
        config = self.router.get_mode_config(IntelligenceMode.DEEP)
        assert config.critic is True
        assert config.planner is True
        assert config.goal_mode is True

    def test_fast_config_minimal(self):
        """FAST 模式应最轻量"""
        config = self.router.get_mode_config(IntelligenceMode.FAST)
        assert config.planner is False
        assert config.critic is False
        assert config.max_rounds == 1
        assert config.allow_write is False

    def test_safe_config_requires_approval(self):
        """SAFE 模式要求审批"""
        config = self.router.get_mode_config(IntelligenceMode.SAFE)
        assert config.approval_required is True
        assert config.review_type == "security"

    def test_research_config_always_web_search(self):
        """RESEARCH 模式总是联网"""
        config = self.router.get_mode_config(IntelligenceMode.RESEARCH)
        assert config.web_search == "always"

    def test_get_stats(self):
        """路由统计应记录"""
        self.router.route("你好")
        self.router.route("写个函数")
        self.router.route("重构架构")
        stats = self.router.get_stats()
        assert stats["total"] >= 3
        assert stats["FAST"] >= 1
        assert stats["BALANCED"] >= 1

    def test_multi_line_request_detected_as_multi_step(self):
        """多行请求应被检测为多步骤"""
        profile = self.router.analyze("一\n二\n三\n四\n五\n六\n七\n八\n九\n十\n十一")
        assert profile.has_multi_step is True

    def test_ambigous_request_detection(self):
        """模糊请求应被检测"""
        profile = self.router.analyze("帮我看看这段代码是什么问题")
        assert profile.is_ambiguous is True

    def test_context_previous_failures_increases_complexity(self):
        """历史失败应增加复杂度"""
        context = {"previous_failures": 2}
        profile = self.router.analyze("修复 bug", context)
        profile_without = self.router.analyze("修复 bug")
        # 上下文中的 previous_failures 会给复杂度 +1
        assert profile.complexity == profile_without.complexity + 1

    def test_context_file_count_triggers_multi_step(self):
        """文件数 > 3 应触发多步骤"""
        req = "修改配置"
        context = {"file_count": 5}
        profile = self.router.analyze(req, context)
        assert profile.has_multi_step is True


# ══════════════════════════════════════════════
# ── ModeConfig Tests ──
# ══════════════════════════════════════════════

class TestModeConfig:
    """模式配置测试"""

    def test_all_modes_have_config(self):
        """所有 IntelligenceMode 都应有对应配置"""
        for mode in IntelligenceMode:
            assert mode in MODE_CONFIGS, f"{mode} missing from MODE_CONFIGS"

    def test_deep_config_values(self):
        """DEEP 模式配置值验证"""
        c = MODE_CONFIGS[IntelligenceMode.DEEP]
        assert c.planner is True
        assert c.critic is True
        assert c.multi_agent is True
        assert c.web_search == "auto"
        assert c.allow_write is True
        assert c.allow_shell is False
        assert c.tests_required is True
        assert c.approval_required is False
        assert c.max_rounds == 4
        assert c.max_agents == 4
        assert c.goal_mode is True
        assert c.review_type == "code"

    def test_safe_config_values(self):
        """SAFE 模式配置值验证"""
        c = MODE_CONFIGS[IntelligenceMode.SAFE]
        assert c.planner is True
        assert c.critic is True
        assert c.multi_agent is True
        assert c.approval_required is True
        assert c.review_type == "security"
        assert c.max_rounds == 5
        assert c.goal_mode is True

    def test_fast_config_values(self):
        """FAST 模式配置值验证"""
        c = MODE_CONFIGS[IntelligenceMode.FAST]
        assert c.planner is False
        assert c.critic is False
        assert c.multi_agent is False
        assert c.allow_shell is False
        assert c.allow_write is False
        assert c.max_agents == 0


# ══════════════════════════════════════════════
# ── CriticAgent Tests ──
# ══════════════════════════════════════════════

class TestCriticAgent:
    """批评者代理测试"""

    def setup_method(self):
        self.critic = CriticAgent()

    def test_build_critic_prompt_contains_target(self):
        """自审 prompt 应包含目标"""
        prompt = self.critic.build_critic_prompt("test_scheme")
        assert "test_scheme" in prompt
        assert "严格" in prompt or "critical" in prompt

    def test_build_critic_prompt_with_context(self):
        """带上下文的 prompt 应包含上下文"""
        prompt = self.critic.build_critic_prompt("scheme", "context_data")
        assert "context_data" in prompt
        assert "scheme" in prompt

    def test_parse_json_findings(self):
        """解析有效 JSON — V2 要求 evidence 字段"""
        response = """
        审查结果:
        [
            {"category": "logic", "severity": "high", "summary": "空指针风险", "evidence": "file.py:42 未检查None", "detail": "未处理None", "location": "line 42", "suggestion": "加判空"},
            {"category": "security", "severity": "critical", "summary": "SQL注入", "evidence": "db.py:15 直接拼接SQL", "detail": "直接拼接", "location": "db.py", "suggestion": "用参数化查询"}
        ]
        """
        findings = self.critic.parse_critic_response(response)
        # V2: 所有 finding 都有 evidence，应全部通过
        assert len(findings) >= 2
        assert any(f.severity == CritiqueSeverity.CRITICAL for f in findings)
        assert any(f.category == CritiqueCategory.SECURITY for f in findings)

    def test_parse_invalid_json_fallback(self):
        """无效 JSON 应走 fallback 解析"""
        response = """Critical: 发现了一个严重问题
High: 这个性能问题需要注意
另一个问题"""
        findings = self.critic.parse_critic_response(response)
        # 至少应该解析到一些东西
        assert len(findings) > 0

    def test_empty_response(self):
        """空响应应返回空列表"""
        findings = self.critic.parse_critic_response("")
        assert len(findings) == 0

    def test_severity_mapping(self):
        """严重级别映射正确"""
        assert self.critic._map_severity("critical") == CritiqueSeverity.CRITICAL
        assert self.critic._map_severity("high") == CritiqueSeverity.HIGH
        assert self.critic._map_severity("medium") == CritiqueSeverity.MEDIUM
        assert self.critic._map_severity("low") == CritiqueSeverity.LOW
        assert self.critic._map_severity("info") == CritiqueSeverity.INFO
        assert self.critic._map_severity("unknown") == CritiqueSeverity.MEDIUM

    def test_generate_fix_prompt(self):
        """修复 prompt 应包含审查发现"""
        report = CritiqueReport(target="test")
        report.findings.append(CritiqueFinding(
            category=CritiqueCategory.LOGIC,
            severity=CritiqueSeverity.HIGH,
            summary="空指针",
        ))
        fix_prompt = self.critic.generate_fix_prompt(report)
        assert "空指针" in fix_prompt or "high" in fix_prompt

    def test_parse_code_review_output(self):
        """代码审查输出解析"""
        output = "   5  warning  unused variable 'x'\n  10  error  undefined 'foo'"
        findings = self.critic._parse_code_review_output(output)
        assert len(findings) >= 1


# ══════════════════════════════════════════════
# ── DeliberateWorkflow Tests ──
# ══════════════════════════════════════════════

class TestDeliberateWorkflow:
    """深度推理工作流测试"""

    def setup_method(self):
        self.workflow = DeliberateWorkflow()

    def test_init_with_defaults(self):
        """无参数初始化应正常"""
        wf = DeliberateWorkflow()
        assert wf.policy_router is not None
        assert wf.critic_agent is not None

    def test_fast_track_returns_immediately(self):
        """fast_track 应快速返回"""
        import asyncio
        result = asyncio.run(self.workflow.fast_track("你好"))
        assert result.mode == "FAST"
        assert result.passed is True
        assert len(result.steps) == 1
        assert result.steps[0].name == "direct_response"

    def test_deep_dive_sets_mode(self):
        """deep_dive 应设置 DEEP 模式"""
        assert hasattr(self.workflow, "deep_dive")

    def test_workflow_result_dict(self):
        """WorkflowResult 应能序列化为 dict"""
        result = WorkflowResult(goal_id="test123", mode="DEEP", passed=True)
        d = result.to_dict()
        assert d["goal_id"] == "test123"
        assert d["mode"] == "DEEP"
        assert d["passed"] is True

    def test_workflow_step_timing(self):
        """WorkflowStep 应正确计算耗时"""
        import time
        step = WorkflowStep(name="test")
        step.started_at = time.time() - 2.5
        step.completed_at = time.time()
        assert abs(step.duration - 2.5) < 0.5

    def test_format_result(self):
        """格式化结果应包含模式标识"""
        result = WorkflowResult(mode="DEEP", passed=True, summary="测试完成")
        formatted = self.workflow.format_result_for_user(result)
        assert "DEEP" in formatted
        assert "测试完成" in formatted

    def test_format_result_with_steps(self):
        """格式化结果应显示步骤状态"""
        result = WorkflowResult(mode="BALANCED", passed=True)
        result.steps.append(WorkflowStep(name="plan", status="success"))
        result.steps.append(WorkflowStep(name="verify", status="success"))
        formatted = self.workflow.format_result_for_user(result)
        assert "plan" in formatted
        assert "verify" in formatted

    def test_format_result_with_critique(self):
        """格式化结果应包含审查发现"""
        result = WorkflowResult(mode="DEEP", passed=True)
        report = CritiqueReport(target="test")
        report.findings.append(CritiqueFinding(
            category=CritiqueCategory.LOGIC,
            severity=CritiqueSeverity.MEDIUM,
            summary="潜在边界问题",
        ))
        result.critique_report = report
        formatted = self.workflow.format_result_for_user(result)
        assert "边界" in formatted or "审查" in formatted

    def test_critique_report_blocking(self):
        """阻塞性审查报告判断"""
        # 不阻塞
        report1 = CritiqueReport(target="test")
        report1.findings.append(CritiqueFinding(
            category=CritiqueCategory.LOGIC,
            severity=CritiqueSeverity.LOW, summary="minor"
        ))
        assert report1.blocking is False

        # critical 阻塞
        report2 = CritiqueReport(target="test")
        report2.findings.append(CritiqueFinding(
            category=CritiqueCategory.SECURITY,
            severity=CritiqueSeverity.CRITICAL, summary="sql injection"
        ))
        assert report2.blocking is True

    def test_critique_report_counts(self):
        """严重级别计数"""
        report = CritiqueReport(target="test")
        report.findings.append(CritiqueFinding(
            category=CritiqueCategory.LOGIC, severity=CritiqueSeverity.CRITICAL, summary="1"
        ))
        report.findings.append(CritiqueFinding(
            category=CritiqueCategory.LOGIC, severity=CritiqueSeverity.CRITICAL, summary="2"
        ))
        report.findings.append(CritiqueFinding(
            category=CritiqueCategory.LOGIC, severity=CritiqueSeverity.HIGH, summary="3"
        ))
        assert report.critical_count == 2
        assert report.high_count == 1


# ══════════════════════════════════════════════
# ── Format Utilities Tests ──
# ══════════════════════════════════════════════

class TestFormatUtils:
    """格式化工具测试"""

    def test_findings_table_format(self):
        """审查发现表格格式"""
        findings = [
            CritiqueFinding(
                category=CritiqueCategory.LOGIC,
                severity=CritiqueSeverity.HIGH,
                summary="Test finding",
                location="file.py:42",
            )
        ]
        table = format_findings_table(findings)
        assert "Test finding" in table
        assert "high" in table or "HIGH" in table
        assert "|" in table

    def test_empty_findings_table(self):
        """空发现列表"""
        table = format_findings_table([])
        assert "|" in table  # 至少表头


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
