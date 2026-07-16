"""Routing Signals — 独立信号测试"""

from core.routing_signals import (
    compute_mode_scores,
    get_route_decision,
    get_top_modes,
    signal_has_code,
    signal_has_debug_symptom,
    signal_has_destructive_ops,
    signal_has_file_ops,
    signal_has_multi_step,
    signal_has_planning_indicators,
    signal_has_security_risk,
    signal_has_shell_ops,
    signal_is_architecture,
    signal_is_bug_fix,
    signal_is_code_review,
    signal_is_creative,
    signal_is_deep_investigation,
    signal_is_rapid_prototype,
    signal_is_research,
    signal_is_simple_chat,
    signal_is_simple_lookup,
    signal_is_test_task,
    signal_needs_web_search,
)


class TestAllSignals:
    """每个信号函数的基础验证"""

    def test_has_code_positive(self):
        assert signal_has_code("写一个 Python 函数", {}) > 0.3

    def test_has_code_negative(self):
        assert signal_has_code("你好", {}) < 0.3

    def test_has_code_import(self):
        assert signal_has_code("import os; from django import", {}) > 0.5

    def test_has_multi_step_positive(self):
        score = signal_has_multi_step("首先分析,然后设计,最后实现", {})
        assert score > 0.5

    def test_has_multi_step_negative(self):
        assert signal_has_multi_step("hello", {}) < 0.3

    def test_is_architecture_system(self):
        assert signal_is_architecture("重构整个微服务架构", {}) > 0.5

    def test_is_architecture_function_level_dampened(self):
        score = signal_is_architecture("重构一下这个函数签名", {})
        assert score < 0.5  # Should be dampened for function-level

    def test_has_security_risk_token(self):
        assert signal_has_security_risk("重置所有用户的token", {}) > 0.3

    def test_has_security_risk_negative(self):
        assert signal_has_security_risk("你好", {}) < 0.3

    def test_has_destructive_ops(self):
        assert signal_has_destructive_ops("删除所有文件", {}) > 0.3

    def test_is_research(self):
        assert signal_is_research("研究最新的RAG技术", {}) > 0.3

    def test_is_research_with_code_dampened(self):
        score = signal_is_research("研究一下这个 import os 的 bug", {})
        assert score < 0.7  # Code keywords reduce research

    def test_is_creative_ui(self):
        assert signal_is_creative("设计一个科技感的产品首页", {}) > 0.3

    def test_is_creative_tech_scheme_dampened(self):
        score = signal_is_creative("设计一个数据库分表方案", {})
        assert score < 0.5  # Tech keywords dampen creative

    def test_has_debug_symptom(self):
        assert signal_has_debug_symptom("程序报错 TypeError", {}) > 0.3

    def test_is_deep_investigation(self):
        assert signal_is_deep_investigation("排查根因", {}) > 0.5

    def test_is_simple_lookup(self):
        assert signal_is_simple_lookup("帮我查一下这个IP地址", {}) > 0.5

    def test_is_simple_chat_hello(self):
        assert signal_is_simple_chat("你好", {}) > 0.5

    def test_is_simple_chat_negative(self):
        score = signal_is_simple_chat("设计微服务架构方案", {})
        assert score < 0.5

    def test_has_file_ops(self):
        assert signal_has_file_ops("在 src/utils.py 中创建文件", {}) > 0.3

    def test_is_test_task(self):
        assert signal_is_test_task("写单元测试", {}) > 0.5

    def test_is_rapid_prototype(self):
        assert signal_is_rapid_prototype("快速写一个demo", {}) > 0.3

    def test_has_planning_indicators(self):
        assert signal_has_planning_indicators("设计方案", {}) > 0.3

    def test_is_bug_fix(self):
        assert signal_is_bug_fix("修复这个bug", {}) > 0.5

    def test_is_code_review(self):
        assert signal_is_code_review("帮我review这段代码", {}) > 0.5

    def test_has_shell_ops(self):
        assert signal_has_shell_ops("npm install react", {}) > 0.5

    def test_needs_web_search(self):
        assert signal_needs_web_search("最新的2025技术趋势", {}) > 0.3


class TestScoreComputation:
    def test_compute_mode_scores(self):
        scores = compute_mode_scores("你好")
        assert "FAST" in scores
        assert "BALANCED" in scores
        assert scores["FAST"] > scores.get("DEEP", 0)

    def test_compute_different_scores(self):
        simple = compute_mode_scores("你好")
        complex_req = compute_mode_scores("重构微服务架构，拆成独立模块")
        assert complex_req.get("DEEP", 0) > simple.get("DEEP", 0)

    def test_get_top_modes(self):
        top = get_top_modes("你好", top_n=2)
        assert len(top) == 2
        assert top[0][0] in ("FAST", "BALANCED")

    def test_get_route_decision(self):
        mode, scores = get_route_decision("重构微服务架构")
        assert mode in ("DEEP", "BALANCED", "RESEARCH")
