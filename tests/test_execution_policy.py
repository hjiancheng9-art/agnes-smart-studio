"""Tests for core.execution_policy — orchestration routing."""

from __future__ import annotations

from core.execution_policy import ExecutionMode, ExecutionPolicy, choose_policy


class TestChoosePolicy:
    def test_self_check_orchestrate(self):
        """自检 + 范围词 + 动作词 → ORCHESTRATE (semantic feature, not len>40)."""
        policy = choose_policy("请自检整个系统代码质量并修复漏洞")
        assert policy.mode == ExecutionMode.ORCHESTRATE

    def test_self_check_short_with_scope_also_orchestrate(self):
        """Short prompt with 自检 + scope word → still ORCHESTRATE."""
        policy = choose_policy("审计所有核心模块")
        assert policy.mode == ExecutionMode.ORCHESTRATE

    def test_casual_self_check_no_triggers(self):
        """Casual single-keyword mentions must NOT escalate."""
        for casual in ("帮我自检一下", "audit 一下", "自修吗"):
            policy = choose_policy(casual)
            assert policy.mode == ExecutionMode.DIRECT, f"{casual!r} should be DIRECT"

    def test_pinyin_orchestrate(self):
        policy = choose_policy("self-heal and audit the entire codebase")
        assert policy.mode == ExecutionMode.ORCHESTRATE

    def test_english_orchestrate(self):
        policy = choose_policy("self heal the system")
        assert policy.mode == ExecutionMode.ORCHESTRATE

    def test_audit_orchestrate(self):
        policy = choose_policy("audit the entire codebase for security issues and code quality problems")
        assert policy.mode == ExecutionMode.ORCHESTRATE

    def test_direct_simple(self):
        policy = choose_policy("hello world")
        assert policy.mode == ExecutionMode.DIRECT

    def test_swarm_multi(self):
        policy = choose_policy("分别分析 多方案 对比 core和ui的代码质量")
        assert policy.mode in (ExecutionMode.SWARM, ExecutionMode.ORCHESTRATE)


class TestExecutionPolicy:
    def test_policy_fields(self):
        policy = ExecutionPolicy(ExecutionMode.ORCHESTRATE, "test reason")
        assert policy.mode == ExecutionMode.ORCHESTRATE
        assert policy.reason == "test reason"
