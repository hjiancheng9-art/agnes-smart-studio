"""Tests for core.execution_policy — orchestration routing."""

from __future__ import annotations

from core.execution_policy import ExecutionMode, ExecutionPolicy, choose_policy


class TestChoosePolicy:
    def test_self_check_orchestrate(self):
        policy = choose_policy("自检自修")
        assert policy.mode == ExecutionMode.ORCHESTRATE

    def test_pinyin_orchestrate(self):
        policy = choose_policy("zijianzixiu")
        assert policy.mode == ExecutionMode.ORCHESTRATE

    def test_english_orchestrate(self):
        policy = choose_policy("self heal the system")
        assert policy.mode == ExecutionMode.ORCHESTRATE

    def test_audit_orchestrate(self):
        policy = choose_policy("audit the codebase")
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

