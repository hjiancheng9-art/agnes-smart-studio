"""工具评分引擎单测 — 静态健康度 + 运行时质量双层评分。

覆盖:
    - 等级阈值 (grade_from_score)
    - 静态 4 维度: 测试覆盖 / schema / 风险 / 可达性
    - 运行时评分: 成功率 / 速度 / P95 / 参数失败率 / 空数据降级
    - 全量聚合报告: 分级分布 / worst_5 / untested / average
    - 调用日志 round-trip (log_call -> load_recent -> group_by_tool)
    - 端到端 smoke (真实 registry 全量评分不抛异常)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import tool_call_log
from core.tool_scorecard import (
    DESTRUCTIVE_TOOLS,
    GRADE_THRESHOLDS,
    HIGH_RISK_TOOLS,
    grade_from_score,
    reset_test_coverage_cache,
    save_report,
    score_all,
    score_tool_runtime,
    score_tool_static,
)
from core.tools import ToolRegistry

# ── fixtures ────────────────────────────────────────────────────


@pytest.fixture
def fresh_registry():
    """构造一个最小 ToolRegistry, 仅含 builtin + 一个 safe + 一个 high-risk 工具定义。

    用 monkeypatch-free 方式: ToolRegistry() 默认只装 builtin executors,
    我们直接往 _definitions 塞测试用 defn, 避开 tools.json。
    """
    reg = ToolRegistry()
    # 不调用 reg.load() — 只用 builtin executors + 手工注入的测试定义
    reg._definitions = [
        {  # safe, schema 完备
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the content of a file from disk path",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {  # high-risk
            "type": "function",
            "function": {
                "name": "git_push",
                "description": "Push commits to remote repository branch",
                "parameters": {
                    "type": "object",
                    "properties": {"force": {"type": "boolean"}},
                    "required": [],
                },
            },
        },
        {  # destructive
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Overwrite a file with new content",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
    ]
    # 给 read_file 注册一个 executor, 让可达性维度满分; 其他不注册 → builtin/no-executor 分
    reg._executors["read_file"] = lambda **kw: "ok"
    reg._tool_modules["read_file"] = "test"
    return reg


@pytest.fixture(autouse=True)
def reset_caches():
    """每个测试前后清测试覆盖缓存, 避免跨用例污染。"""
    reset_test_coverage_cache()
    yield
    reset_test_coverage_cache()


# ── 等级阈值 ────────────────────────────────────────────────────


class TestGradeThresholds:
    def test_a_threshold(self):
        assert grade_from_score(90) == "A"
        assert grade_from_score(100) == "A"
        assert grade_from_score(95.5) == "A"

    def test_b_threshold(self):
        assert grade_from_score(89.9) == "B"
        assert grade_from_score(75) == "B"

    def test_c_threshold(self):
        assert grade_from_score(74.9) == "C"
        assert grade_from_score(60) == "C"

    def test_d_threshold(self):
        assert grade_from_score(59.9) == "D"
        assert grade_from_score(0) == "D"
        assert grade_from_score(-5) == "D"

    def test_thresholds_sorted_desc(self):
        """GRADE_THRESHOLDS 必须降序, 否则 grade_from_score 逻辑会错。"""
        scores = [t for _, t in GRADE_THRESHOLDS]
        assert scores == sorted(scores, reverse=True)


# ── 静态评分 ────────────────────────────────────────────────────


class TestStaticScoring:
    def test_safe_well_typed_tool_gets_high_score(self, fresh_registry):
        """read_file: safe + 完备 schema + 有 executor → 高分。"""
        s = score_tool_static("read_file", fresh_registry)
        assert s["name"] == "read_file"
        assert s["score"] > 0
        # 风险维度必须满分(25)
        assert s["dimensions"]["risk"]["score"] == 25
        assert s["dimensions"]["risk"]["detail"] == "safe"
        # 可达性维度有 executor → 满分(20)
        assert s["dimensions"]["reachability"]["score"] == 20
        # schema 维度: desc≥20 + 1 required + all typed → 10+8+7 = 25
        assert s["dimensions"]["schema"]["score"] == 25

    def test_high_risk_tool_gets_risk_penalty(self, fresh_registry):
        """git_push 命中 HIGH_RISK_TOOLS → 风险维度只有 8 分。"""
        s = score_tool_static("git_push", fresh_registry)
        assert s["dimensions"]["risk"]["score"] == 8
        assert "high-risk" in s["dimensions"]["risk"]["detail"]

    def test_destructive_tool_gets_middle_risk(self, fresh_registry):
        """write_file 命中 DESTRUCTIVE_TOOLS → 风险维度 15 分。"""
        s = score_tool_static("write_file", fresh_registry)
        assert s["dimensions"]["risk"]["score"] == 15
        assert s["dimensions"]["risk"]["detail"] == "destructive"

    def test_unknown_tool_gets_zero_reachability(self, fresh_registry):
        """未注册的工具 → 可达性 0 (dead code)。"""
        s = score_tool_static("totally_unknown_tool", fresh_registry)
        assert s["dimensions"]["reachability"]["score"] == 0
        assert s["dimensions"]["reachability"]["detail"] == "dead code"

    def test_builtin_only_tool_gets_partial_reachability(self, fresh_registry):
        """有定义无 executor 的工具 → 可达性 5 (builtin path)。"""
        # git_push 只有定义, 没注册 executor
        s = score_tool_static("git_push", fresh_registry)
        assert s["dimensions"]["reachability"]["score"] == 5
        assert "builtin" in s["dimensions"]["reachability"]["detail"]

    def test_score_in_valid_range(self, fresh_registry):
        """任何工具分数必须在 [0, 100] 区间。"""
        for name in ["read_file", "git_push", "write_file", "nope"]:
            s = score_tool_static(name, fresh_registry)
            assert 0 <= s["score"] <= 100, f"{name}: {s['score']}"

    def test_no_schema_definition(self, fresh_registry):
        """完全没有定义的工具 → schema 0 分。"""
        # 清空 definitions 再测
        fresh_registry._definitions = []
        s = score_tool_static("anything", fresh_registry)
        assert s["dimensions"]["schema"]["score"] == 0

    def test_grade_consistent_with_score(self, fresh_registry):
        """返回的 grade 必须与 score 通过 grade_from_score 一致。"""
        for name in ["read_file", "git_push", "write_file"]:
            s = score_tool_static(name, fresh_registry)
            assert s["grade"] == grade_from_score(s["score"])

    def test_high_risk_set_nonempty_and_contains_git_push(self):
        """HIGH_RISK_TOOLS 必须含 git_push (与 chat.py 确认门对齐)。"""
        assert "git_push" in HIGH_RISK_TOOLS
        assert len(HIGH_RISK_TOOLS) >= 3  # 至少几个高风险

    def test_destructive_set_disjoint_from_high_risk(self):
        """两个集合语义上应互斥 (高风险 vs 破坏性)。"""
        assert HIGH_RISK_TOOLS.isdisjoint(DESTRUCTIVE_TOOLS)


# ── 运行时评分 ──────────────────────────────────────────────────


class TestRuntimeScoring:
    def test_empty_calls_returns_na(self):
        """无调用数据 → score=None, grade=N/A。"""
        r = score_tool_runtime("read_file", [])
        assert r["score"] is None
        assert r["grade"] == "N/A"
        assert r["call_count"] == 0

    def test_all_success_gets_high_score(self):
        """全成功 + 极快 → 接近满分 (50 + 30 + 20)。"""
        calls = [
            {"status": "ok", "duration_ms": 5.0},
            {"status": "ok", "duration_ms": 8.0},
            {"status": "ok", "duration_ms": 3.0},
        ]
        r = score_tool_runtime("fast_tool", calls)
        assert r["score"] >= 95
        assert r["grade"] == "A"
        assert r["success_rate"] == 100.0
        assert r["call_count"] == 3
        assert r["arg_fail_rate"] == 0.0

    def test_all_failures_gets_low_score(self):
        """全异常 + 慢 → 低分。"""
        calls = [
            {"status": "exception", "duration_ms": 6000.0},
            {"status": "exception", "duration_ms": 7000.0},
        ]
        r = score_tool_runtime("bad_tool", calls)
        # 成功率 0 + 速度 0 + 稳定 20 = ~20
        assert r["score"] <= 25
        assert r["grade"] == "D"
        assert r["success_rate"] == 0.0

    def test_arg_fail_rate_computed(self):
        """参数失败单独计数。"""
        calls = [
            {"status": "ok", "duration_ms": 10.0},
            {"status": "arg_validation_failed", "duration_ms": 0.0},
            {"status": "arg_validation_failed", "duration_ms": 0.0},
            {"status": "ok", "duration_ms": 10.0},
        ]
        r = score_tool_runtime("flaky", calls)
        assert r["arg_fail_rate"] == 50.0  # 2/4
        assert r["success_rate"] == 50.0  # 2/4

    def test_p95_from_durations(self):
        """P95 应取接近最大值的样本。"""
        durations = [10 * i for i in range(1, 21)]  # 10..200, 20 个样本
        calls = [{"status": "ok", "duration_ms": d} for d in durations]
        r = score_tool_runtime("p95test", calls)
        # P95 索引 = min(19, int(20*0.95)) = min(19, 19) = 19 → durations[19] = 200
        assert r["p95_ms"] == 200
        assert r["avg_ms"] == 105.0  # (10+200)*20/2/20 = 105

    def test_missing_duration_treated_as_zero(self):
        """缺失 duration_ms 不应崩, 按缺失处理。"""
        calls = [
            {"status": "ok"},  # 无 duration_ms
            {"status": "ok", "duration_ms": 5.0},
        ]
        r = score_tool_runtime("partial", calls)
        assert r["call_count"] == 2
        # 至少能算出 avg, 不抛异常
        assert isinstance(r["avg_ms"], float)

    def test_score_always_in_range(self):
        """任何极端数据组合都不能越界。"""
        # 全 0 时长
        r1 = score_tool_runtime("x", [{"status": "ok", "duration_ms": 0}] * 10)
        assert 0 <= r1["score"] <= 100
        # 超长时长
        r2 = score_tool_runtime("x", [{"status": "ok", "duration_ms": 999999.0}])
        assert 0 <= r2["score"] <= 100


# ── 全量聚合报告 ────────────────────────────────────────────────


class TestScoreAll:
    def test_report_structure(self, fresh_registry):
        """聚合报告必须含所有约定字段。"""
        report = score_all(fresh_registry)
        for key in (
            "generated_at",
            "total_tools",
            "grade_distribution",
            "average_score",
            "worst_5",
            "untested",
            "untested_count",
            "high_risk",
            "tools",
        ):
            assert key in report, f"missing {key}"

    def test_total_tools_matches_registry(self, fresh_registry):
        """total_tools 应等于 registry 工具数。"""
        report = score_all(fresh_registry)
        assert report["total_tools"] == len(fresh_registry.tool_names)
        assert len(report["tools"]) == report["total_tools"]

    def test_grade_distribution_sums_to_total(self, fresh_registry):
        """A+B+C+D 必须等于总工具数。"""
        report = score_all(fresh_registry)
        gd = report["grade_distribution"]
        total = sum(gd.values())
        assert total == report["total_tools"]

    def test_worst_5_is_subset_and_sorted(self, fresh_registry):
        """worst_5 是 tools 的子集且按分数升序。"""
        report = score_all(fresh_registry)
        scores_by_name = {t["name"]: t["score"] for t in report["tools"]}
        worst_scores = [scores_by_name[n] for n in report["worst_5"]]
        assert worst_scores == sorted(worst_scores)
        assert len(report["worst_5"]) <= 5

    def test_high_risk_listed(self, fresh_registry):
        """风险分 <25 的工具必须出现在 high_risk 清单。"""
        report = score_all(fresh_registry)
        # read_file safe, git_push high-risk, write_file destructive 都 <25 风险分
        assert "git_push" in report["high_risk"]
        assert "write_file" in report["high_risk"]
        assert "read_file" not in report["high_risk"]

    def test_runtime_attached_when_provided(self, fresh_registry):
        """传入 runtime_calls 时, 对应工具应附加 runtime 字段。"""
        runtime = {
            "read_file": [{"status": "ok", "duration_ms": 5.0}] * 3,
        }
        report = score_all(fresh_registry, runtime_calls=runtime)
        rf = next(t for t in report["tools"] if t["name"] == "read_file")
        assert "runtime" in rf
        assert rf["runtime"]["call_count"] == 3

    def test_runtime_absent_when_not_provided(self, fresh_registry):
        """不传 runtime_calls → 工具无 runtime 字段。"""
        report = score_all(fresh_registry)
        rf = next(t for t in report["tools"] if t["name"] == "read_file")
        assert "runtime" not in rf

    def test_average_score_in_range(self, fresh_registry):
        report = score_all(fresh_registry)
        assert 0 <= report["average_score"] <= 100

    def test_save_report_writes_file(self, fresh_registry, tmp_path):
        """save_report 应写出可被 json 重新加载的文件。"""
        import json

        report = score_all(fresh_registry)
        out = save_report(report, path=tmp_path / "sc.json")
        assert out.exists()
        reloaded = json.loads(out.read_text(encoding="utf-8"))
        assert reloaded["total_tools"] == report["total_tools"]


# ── 调用日志 round-trip ─────────────────────────────────────────


class TestCallLog:
    def test_log_and_load_round_trip(self, tmp_path, monkeypatch):
        """log_call 写入 → load_recent 读出, 字段完整。"""
        # 重定向 LOG_FILE 到临时文件, 避免污染真实日志
        fake_log = tmp_path / "calls.jsonl"
        monkeypatch.setattr(tool_call_log, "LOG_FILE", fake_log)

        tool_call_log.log_call("tool_a", "ok", 3.5, {"path": "/x"})
        tool_call_log.log_call("tool_a", "ok", 4.2, {"path": "/y"})
        tool_call_log.log_call("tool_b", "exception", 0.0, {"name": "b"})

        recs = tool_call_log.load_recent(limit=100)
        assert len(recs) == 3
        # 最新在前
        assert recs[0]["tool"] == "tool_b"
        # args 只记 key
        assert recs[0]["args_keys"] == ["name"]
        assert recs[2]["args_keys"] == ["path"]

    def test_load_recent_filter_by_tool(self, tmp_path, monkeypatch):
        fake_log = tmp_path / "calls.jsonl"
        monkeypatch.setattr(tool_call_log, "LOG_FILE", fake_log)

        tool_call_log.log_call("x", "ok", 1.0)
        tool_call_log.log_call("y", "ok", 2.0)
        tool_call_log.log_call("x", "ok", 3.0)

        only_x = tool_call_log.load_recent(limit=10, tool_name="x")
        assert len(only_x) == 2
        assert all(r["tool"] == "x" for r in only_x)

    def test_group_by_tool(self, tmp_path, monkeypatch):
        fake_log = tmp_path / "calls.jsonl"
        monkeypatch.setattr(tool_call_log, "LOG_FILE", fake_log)

        for _ in range(5):
            tool_call_log.log_call("alpha", "ok", 1.0)
        for _ in range(3):
            tool_call_log.log_call("beta", "ok", 1.0)

        grouped = tool_call_log.group_by_tool()
        assert set(grouped.keys()) == {"alpha", "beta"}
        assert len(grouped["alpha"]) == 5
        assert len(grouped["beta"]) == 3

    def test_log_failure_is_silent(self, tmp_path, monkeypatch):
        """写入失败时绝不能抛异常 (日志不能阻塞工具执行)。"""
        # 指向一个不存在的目录, 触发 OSError
        bad_path = tmp_path / "no_such_dir" / "calls.jsonl"
        monkeypatch.setattr(tool_call_log, "LOG_FILE", bad_path)
        # 不应抛
        tool_call_log.log_call("x", "ok", 1.0)

    def test_clear_log(self, tmp_path, monkeypatch):
        fake_log = tmp_path / "calls.jsonl"
        monkeypatch.setattr(tool_call_log, "LOG_FILE", fake_log)
        for _ in range(4):
            tool_call_log.log_call("x", "ok", 1.0)
        cleared = tool_call_log.clear_log()
        assert cleared == 4
        assert tool_call_log.load_recent() == []


# ── 端到端 smoke (真实 registry) ────────────────────────────────


class TestE2EWithRealRegistry:
    """用真实 ToolRegistry 全量评分, 验证不抛异常 + 数据合理。"""

    def test_real_registry_score_all_runs(self):
        reg = ToolRegistry()
        reg.load()
        report = score_all(reg)
        assert report["total_tools"] == len(reg.tool_names)
        assert report["total_tools"] > 0
        assert sum(report["grade_distribution"].values()) == report["total_tools"]
        # 每个工具分都应在合理区间
        for t in report["tools"]:
            assert 0 <= t["score"] <= 100
            assert t["grade"] in ("A", "B", "C", "D")

    def test_real_registry_with_runtime(self):
        """真实 registry + group_by_tool(空也无妨) → 不崩。"""
        reg = ToolRegistry()
        reg.load()
        runtime = tool_call_log.group_by_tool(limit=50)
        report = score_all(reg, runtime_calls=runtime)
        # 有运行时数据的工具应附 runtime 字段
        for t in report["tools"]:
            if "runtime" in t:
                rt = t["runtime"]
                assert rt["call_count"] >= 0
