"""Unit tests for core/methodology.py — classification, state machine, verification.

These are the primary tests for the methodology engine.
For property-based/fuzz tests see test_zcode_properties.py.
"""

from core.methodology import (
    MethodologyState,
    TaskLevel,
    classify_task,
    detect_red_flags,
    escalate_task,
    get_methodology_state,
    reset_methodology_state,
)

# ── TaskLevel enum ──


def test_tasklevel_enum_values():
    assert TaskLevel.A.name == "A"
    assert TaskLevel.B.name == "B"
    assert TaskLevel.C.name == "C"
    assert TaskLevel.D.name == "D"
    assert list(TaskLevel) == [TaskLevel.A, TaskLevel.B, TaskLevel.C, TaskLevel.D]


# ── classify_task ──


class TestClassifyTask:
    def test_empty_intent_defaults_to_a(self):
        assert classify_task("") == TaskLevel.A

    def test_simple_question_is_a(self):
        assert classify_task("what is python") == TaskLevel.A

    def test_trivial_edits_are_a(self):
        for intent in ["fix typo", "add comment", "update comment", "fix typo in readme", "解释这段代码", "改文案"]:
            assert classify_task(intent) == TaskLevel.A, f"expected A for: {intent}"

    def test_bugfix_is_b(self):
        for intent in ["fix bug in login", "修复bug", "补一个错误"]:
            assert classify_task(intent, ["core/auth.py"]) == TaskLevel.B

    def test_single_file_bugfix_is_b(self):
        assert classify_task("fix encoding bug", ["core/encoding.py"]) == TaskLevel.B

    def test_two_file_bugfix_is_b(self):
        assert classify_task("fix two file bug", ["core/a.py", "core/b.py"]) == TaskLevel.B

    def test_refactor_is_c(self):
        assert classify_task("重构", ["core/a.py", "core/b.py", "core/c.py"]) == TaskLevel.C

    def test_architecture_is_c(self):
        assert (
            classify_task("architecture redesign", ["core/a.py", "core/b.py", "core/c.py", "core/d.py"]) == TaskLevel.C
        )

    def test_three_plus_files_is_c(self):
        assert classify_task("some change", ["a.py", "b.py", "c.py"]) == TaskLevel.C

    def test_deploy_is_d(self):
        assert classify_task("deploy to production") == TaskLevel.D

    def test_auth_credentials_are_d(self):
        assert classify_task("update auth credentials") == TaskLevel.D

    def test_migration_is_d(self):
        assert classify_task("database migration") == TaskLevel.D

    def test_models_json_plus_core_is_d(self):
        assert classify_task("update config", ["core/config.py", "models.json"]) == TaskLevel.D

    def test_refactor_authentication_is_c_not_d(self):
        """'authentication system' should not trigger D (only bare 'auth' keyword)."""
        assert classify_task("refactor the authentication system") == TaskLevel.C

    def test_return_type_is_tasklevel(self):
        assert isinstance(classify_task("anything"), TaskLevel)


# ── escalate_task ──


class TestEscalateTask:
    def test_a_to_d_for_auth(self):
        assert escalate_task(TaskLevel.A, "涉及 auth 系统") == TaskLevel.D

    def test_c_to_d_for_impact(self):
        assert escalate_task(TaskLevel.C, "影响其他模块") == TaskLevel.D

    def test_a_to_c_for_multi_file(self):
        assert escalate_task(TaskLevel.A, "超过3个文件") == TaskLevel.C

    def test_b_to_c_for_new_dep(self):
        assert escalate_task(TaskLevel.B, "新增依赖") == TaskLevel.C

    def test_d_stays_d(self):
        assert escalate_task(TaskLevel.D, "anything") == TaskLevel.D

    def test_a_stays_a_for_trivial(self):
        assert escalate_task(TaskLevel.A, "") == TaskLevel.A


# ── detect_red_flags ──


class TestDetectRedFlags:
    def test_detects_chinese_subjective(self):
        flags = detect_red_flags("应该好了，应该没问题")
        assert len(flags) >= 2

    def test_clean_response_has_no_flags(self):
        flags = detect_red_flags("修复完成，core/auth.py 测试通过")
        assert len(flags) == 0

    def test_detects_looks_good(self):
        flags = detect_red_flags("looks good to me")
        assert len(flags) == 1
        assert "looks good" in flags[0].lower()

    def test_detects_concurrent_refactor(self):
        flags = detect_red_flags("顺便重构也要改")
        assert len(flags) >= 1


# ── MethodologyState ──


class TestMethodologyState:
    def test_initial_state(self):
        state = MethodologyState()
        assert state.task_level == TaskLevel.A
        assert state.step_count == 0
        assert not state.plan_exists

    def test_classify_sets_level_and_advances(self):
        state = MethodologyState()
        state.classify("deploy to prod", ["core/deploy.py"])
        assert state.task_level == TaskLevel.D
        assert state.workflow_step == 3

    def test_requires_plan_for_c_and_d(self):
        for level in [TaskLevel.C, TaskLevel.D]:
            state = MethodologyState(task_level=level)
            assert state.requires_plan

    def test_does_not_require_plan_for_a_and_b(self):
        for level in [TaskLevel.A, TaskLevel.B]:
            state = MethodologyState(task_level=level)
            assert not state.requires_plan

    def test_requires_worktree_for_d(self):
        state = MethodologyState(task_level=TaskLevel.D)
        assert state.requires_worktree

    def test_advance_workflow_moves_forward(self):
        state = MethodologyState()
        state.advance_workflow("plan_created")
        assert state.workflow_step >= 4

    def test_escalate_updates_level_and_records(self):
        state = MethodologyState(task_level=TaskLevel.B)
        new_level = state.escalate("新增依赖")
        assert new_level == TaskLevel.C
        assert state.task_level == TaskLevel.C
        assert len(state.escalation_history) > 0

    def test_record_tool_increments_count(self):
        state = MethodologyState()
        state.record_tool("read_file")
        assert state.tool_call_count == 1

    def test_record_step_increments_count(self):
        state = MethodologyState()
        state.record_step()
        assert state.step_count == 1

    def test_summary_contains_key_info(self):
        state = MethodologyState(task_level=TaskLevel.C)
        state.record_tool("search_files")
        state.record_step()
        summary = state.summary()
        assert "C" in summary or "complex" in summary or "search_files" in summary


# ── Module-level functions ──


def test_get_methodology_state_is_singleton():
    reset_methodology_state()
    s1 = get_methodology_state()
    s2 = get_methodology_state()
    assert s1 is s2


def test_reset_methodology_state_creates_new():
    reset_methodology_state()
    s1 = get_methodology_state()
    reset_methodology_state()
    s2 = get_methodology_state()
    assert s1 is not s2
