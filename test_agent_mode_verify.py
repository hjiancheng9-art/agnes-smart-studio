"""Quick functional verification of AgentMode 4-tier system."""
from core.multi_agent import (
    AgentMode, AgentModeResult, compute_agent_mode, should_use_multi_agent,
    keyword_score, length_score, file_scope_score, failure_score,
    risk_score, ambiguity_score, simplicity_score,
    build_context_state, record_agent_mode_result, get_mode_statistics,
)


def test_enum():
    assert AgentMode.SINGLE.value == "single"
    assert AgentMode.SWARM.value == "swarm"
    print("AgentMode enum: OK")


def test_dataclass():
    r = AgentModeResult(mode=AgentMode.SINGLE, task_type="test", success=True, latency=0.5)
    assert r.success
    assert r.latency == 0.5
    assert r.user_correction is False
    print("AgentModeResult: OK")


def test_build_context_state():
    ctx = build_context_state(recent_failures=2, files_touched=8, error_repeated=True)
    assert ctx["recent_failures"] == 2
    assert ctx["files_touched"] == 8
    assert ctx["error_repeated"] is True
    assert ctx["task_continuation"] is False
    print("build_context_state: OK")


def test_keyword_score():
    ks, m = keyword_score("重构整个项目的架构并审计所有跨文件引用")
    print(f"  keyword_score: {ks:.1f} matched={m}")
    assert ks > 3.0


def test_length_score():
    assert length_score("x" * 600) == 1.5
    assert length_score("x" * 100) == 0.0
    assert length_score("x" * 2500) == 3.0
    print(f"  length_score: OK")


def test_file_scope_score():
    assert file_scope_score({"files_touched": 12}) == 2.0
    assert file_scope_score({"files_touched": 1}) == 0.0
    assert file_scope_score({}) == 0.0
    print(f"  file_scope_score: OK")


def test_failure_score():
    ff = failure_score({"recent_failures": 3, "error_repeated": True})
    assert ff == 5.0
    ff2 = failure_score({})
    assert ff2 == 0.0
    print(f"  failure_score: OK")


def test_risk_score():
    rk, rm = risk_score("delete all files and reset config")
    assert rk >= 8.0  # delete(4) + reset(4)
    print(f"  risk_score: {rk:.1f} matched={rm}")


def test_ambiguity_score():
    am, amm = ambiguity_score("这个东西大概可能不太好用，看看试试")
    assert am >= 2.0
    print(f"  ambiguity_score: {am:.1f} matched={amm}")


def test_simplicity_score():
    sp, sm = simplicity_score("简单的一句话直接回答")
    assert sp >= 6.0
    print(f"  simplicity_score: {sp:.1f} matched={sm}")


def test_mode_simple():
    mode, score, bd = compute_agent_mode("简单的一句话")
    print(f"  Simple: mode={mode.value} score={score:.1f}")
    assert mode == AgentMode.SINGLE, f"Expected SINGLE got {mode}"


def test_mode_complex_with_failures():
    mode, score, _ = compute_agent_mode(
        "重构整个项目的架构并迁移数据库，批量处理所有跨文件引用，同时审查安全性",
        session=build_context_state(recent_failures=2, files_touched=15, error_repeated=True),
    )
    print(f"  Complex+failures: mode={mode.value} score={score:.1f}")
    assert mode in (AgentMode.SWARM, AgentMode.PLAN_EXECUTE)


def test_mode_multi_perspective():
    mode, score, _ = compute_agent_mode("对比这两个方案，多角度分析")
    print(f"  Multi-perspective: mode={mode.value} score={score:.1f}")
    assert mode in (AgentMode.PLAN_EXECUTE, AgentMode.SINGLE_WITH_REVIEWER)


def test_backward_compat():
    should, reason = should_use_multi_agent("简单的一句话")
    print(f"  should_use_multi_agent(simple): {should} — {reason}")
    assert should is False

    should2, reason2 = should_use_multi_agent("重构整个项目的架构并迁移数据库批量处理")
    print(f"  should_use_multi_agent(complex): {should2} — {reason2}")
    assert should2 is True


def test_record_and_stats():
    # Clear any prior state (module-level list)
    from core import multi_agent
    multi_agent._agent_mode_history.clear()

    record_agent_mode_result(AgentModeResult(AgentMode.SINGLE, "simple", True, 0.1))
    record_agent_mode_result(AgentModeResult(AgentMode.SWARM, "complex", True, 5.0))
    record_agent_mode_result(AgentModeResult(
        AgentMode.SINGLE, "simple", False, 0.2, user_correction=True,
    ))
    stats = get_mode_statistics()
    print(f"  stats: {stats}")
    assert stats["single"]["total"] == 2
    assert stats["single"]["success_rate"] == 0.5
    assert stats["single"]["correction_rate"] == 0.5
    assert stats["swarm"]["total"] == 1
    assert stats["swarm"]["success_rate"] == 1.0
    print("  record_agent_mode_result + get_mode_statistics: OK")


def test_breakdown_structure():
    _, _, bd = compute_agent_mode("测试", session=build_context_state())
    for key in ["keyword", "length", "file_scope", "failure", "risk", "ambiguity", "simplicity", "total", "mode"]:
        assert key in bd, f"Missing breakdown key: {key}"
    assert isinstance(bd["total"], float)
    print("  breakdown structure: OK")


if __name__ == "__main__":
    test_enum()
    test_dataclass()
    test_build_context_state()
    test_keyword_score()
    test_length_score()
    test_file_scope_score()
    test_failure_score()
    test_risk_score()
    test_ambiguity_score()
    test_simplicity_score()
    test_mode_simple()
    test_mode_complex_with_failures()
    test_mode_multi_perspective()
    test_backward_compat()
    test_record_and_stats()
    test_breakdown_structure()
    print()
    print("=== ALL 16 TESTS PASSED ===")
