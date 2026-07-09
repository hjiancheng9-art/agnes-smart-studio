"""工具评分引擎 — 给每个工具打静态健康度 + 运行时质量双层评分。

静态评分维度（满分 100）：
    - 测试覆盖   30 分（扫描 tests/*.py 中是否出现该工具名）
    - Schema 完备 25 分（description 长度 + required 标注 + 类型标注）
    - 风险等级   25 分（_HIGH_RISK_TOOLS 扣分 + 破坏性工具扣分）
    - 可达性     20 分（reg.has(name) 即已注册，死代码扣分）

运行时评分维度（基于 tool_calls.jsonl）：
    - 成功率 / 平均耗时 / 调用频次 / 参数校验失败率

等级阈值：A ≥ 90 · B ≥ 75 · C ≥ 60 · D < 60

入口：
    score_tool_static(name, reg)        → 单工具静态分
    score_tool_runtime(name, calls)     → 单工具运行时分
    score_all(reg)                      → 全量聚合报告（含分级分布 / TOP5）
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.tools import ToolRegistry

__all__ = [
    "GRADE_THRESHOLDS",
    "HIGH_RISK_TOOLS",
    "DESTRUCTIVE_TOOLS",
    "score_tool_static",
    "score_tool_runtime",
    "score_all",
    "grade_from_score",
]

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"

# ── 风险工具名单（与 core/chat.py:_HIGH_RISK_TOOLS 对齐）──────────────────
HIGH_RISK_TOOLS: frozenset[str] = frozenset(
    {
        "git_add_commit",  # 本地提交
        "git_push",  # 推送远端
        "git_pr_create",  # 创建 PR
        "git_pr_merge",  # 合并 PR（不可逆）
        "git_tag",  # tag（语义版本不可逆）
    }
)

# 破坏性工具（扣分但不阻拦，需配合 sandbox / 确认门）
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        "run_bash",  # shell 执行（已过 sandbox）
        "patch_file",  # 多文件修改（已有 backup + rollback）
        "write_file",  # 覆盖写
        "edit_file",  # 替换
        "github_write_file",  # 远端写
        "deploy_vercel",  # 部署
    }
)

# 等级阈值
GRADE_THRESHOLDS = [("A", 90), ("B", 75), ("C", 60), ("D", 0)]


def grade_from_score(score: float) -> str:
    """根据分数返回等级 A/B/C/D。"""
    for grade, threshold in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "D"


# ════════════════════════════════════════════════════════════
#  测试覆盖检测（一次性扫全 tests/ 目录，缓存结果）
# ════════════════════════════════════════════════════════════

_test_coverage_cache: dict[str, int] | None = None


def _scan_test_coverage() -> dict[str, int]:
    """扫描 tests/*.py，统计每个工具名被多少个测试文件提及。

    返回 {tool_name: file_count}。结果进程级缓存。
    """
    global _test_coverage_cache
    if _test_coverage_cache is not None:
        return _test_coverage_cache

    coverage: dict[str, int] = {}
    if not TESTS_DIR.is_dir():
        _test_coverage_cache = {}
        return _test_coverage_cache

    # 只扫 .py 文件，避免 .md 报告污染（报告里每个工具都出现一次）
    for test_file in TESTS_DIR.glob("*.py"):
        try:
            content = test_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # 简单子串匹配（工具名都是 snake_case，足够精确）
        # 性能：tests/ 不大，全量扫一遍约 <50ms
        for match in re.finditer(r'"([a-z][a-z0-9_]{2,})"', content):
            name = match.group(1)
            coverage[name] = coverage.get(name, 0) + 1
        # 也匹配单引号
        for match in re.finditer(r"'([a-z][a-z0-9_]{2,})'", content):
            name = match.group(1)
            coverage[name] = coverage.get(name, 0) + 1

    _test_coverage_cache = coverage
    return coverage


def reset_test_coverage_cache() -> None:
    """重置测试覆盖缓存（测试用）。"""
    global _test_coverage_cache
    _test_coverage_cache = None


# ════════════════════════════════════════════════════════════
#  静态评分
# ════════════════════════════════════════════════════════════


def _score_test_coverage(name: str, coverage: dict[str, int]) -> tuple[int, str]:
    """测试覆盖维度（满分 30）。

    被多个测试文件提及 → 满分；只被 1 个提及 → 半分；零提及 → 0。
    """
    file_count = coverage.get(name, 0)
    if file_count >= 2:
        return 30, f"{file_count} files"
    if file_count == 1:
        return 20, "1 file"
    return 0, "untested"


def _score_schema(name: str, defn: dict | None) -> tuple[int, str]:
    """Schema 完备性维度（满分 25）。

    - description ≥ 20 字符:  10 分
    - 有 required 标注:       8 分
    - 参数有 type 标注:        7 分
    """
    if not defn:
        return 0, "no schema"

    fn = defn.get("function", defn)
    desc = fn.get("description", "") or ""
    params = fn.get("parameters", {}) or {}
    properties = params.get("properties", {}) or {}
    required = params.get("required", []) or []

    score = 0
    reasons = []

    # description
    if len(desc) >= 20:
        score += 10
        reasons.append("desc≥20")
    elif len(desc) >= 5:
        score += 5
        reasons.append("desc short")

    # required 标注（有参数的工具应有 required）
    if properties:
        if required:
            score += 8
            reasons.append(f"{len(required)} required")
        else:
            # 无 required 但有参数：可能是全可选，给 4 分
            score += 4
            reasons.append("all optional")
    else:
        # 无参数工具：给满分 required 部分
        score += 8
        reasons.append("no params")

    # 类型标注
    typed = sum(1 for p in properties.values() if isinstance(p, dict) and p.get("type"))
    if properties:
        if typed == len(properties):
            score += 7
            reasons.append("all typed")
        elif typed > 0:
            score += 4
            reasons.append(f"{typed}/{len(properties)} typed")
    else:
        score += 7  # 无参数给满

    return score, " · ".join(reasons)


def _score_risk(name: str) -> tuple[int, str]:
    """风险等级维度（满分 25，越安全越高分）。

    - 普通只读工具:           25 分
    - 破坏性工具（DESTRUCTIVE）: 15 分
    - 高风险工具（HIGH_RISK）:   8 分
    """
    if name in HIGH_RISK_TOOLS:
        return 8, "high-risk (gated)"
    if name in DESTRUCTIVE_TOOLS:
        return 15, "destructive"
    return 25, "safe"


def _score_reachability(name: str, reg: ToolRegistry) -> tuple[int, str]:
    """执行器可达性维度（满分 20）。

    - 已注册有 executor:  20 分
    - 仅定义无 executor:  5 分（builtin 走硬编码路径）
    - 完全未注册:          0 分（死代码）
    """
    if reg.has(name):
        return 20, "registered"
    # 检查是否在 definitions 中（builtin 工具）
    for d in reg.definitions:
        if d.get("function", {}).get("name") == name:
            return 5, "builtin (no executor)"
    return 0, "dead code"


def score_tool_static(name: str, reg: ToolRegistry) -> dict[str, Any]:
    """计算单个工具的静态健康度评分。

    Returns:
        {
            "name": str, "score": int, "grade": str,
            "dimensions": {"test": [score, reason], "schema": [...], ...},
            "total": int
        }
    """
    coverage = _scan_test_coverage()

    # 找该工具的定义
    defn = None
    for d in reg.definitions:
        if d.get("function", {}).get("name") == name:
            defn = d
            break

    test_s, test_r = _score_test_coverage(name, coverage)
    schema_s, schema_r = _score_schema(name, defn)
    risk_s, risk_r = _score_risk(name)
    reach_s, reach_r = _score_reachability(name, reg)

    total = test_s + schema_s + risk_s + reach_s

    return {
        "name": name,
        "score": total,
        "grade": grade_from_score(total),
        "dimensions": {
            "test_coverage": {"score": test_s, "max": 30, "detail": test_r},
            "schema": {"score": schema_s, "max": 25, "detail": schema_r},
            "risk": {"score": risk_s, "max": 25, "detail": risk_r},
            "reachability": {"score": reach_s, "max": 20, "detail": reach_r},
        },
    }


# ════════════════════════════════════════════════════════════
#  运行时评分
# ════════════════════════════════════════════════════════════


def score_tool_runtime(name: str, calls: list[dict]) -> dict[str, Any]:
    """基于调用日志计算单工具运行时质量分。

    Args:
        name: 工具名
        calls: 该工具的调用记录列表（来自 tool_call_log.load_recent 过滤后），
               每条含 status/duration_ms/args_keys 等

    Returns:
        运行时评分 dict，无数据时 score=None。
    """
    if not calls:
        return {
            "name": name,
            "score": None,
            "grade": "N/A",
            "call_count": 0,
            "success_rate": None,
            "avg_ms": None,
            "p95_ms": None,
            "arg_fail_rate": None,
        }

    total = len(calls)
    success = sum(1 for c in calls if c.get("status") == "ok")
    arg_fails = sum(1 for c in calls if c.get("status") == "arg_validation_failed")
    durations = sorted(c.get("duration_ms", 0) for c in calls if c.get("duration_ms") is not None)

    success_rate = success / total if total else 0.0
    arg_fail_rate = arg_fails / total if total else 0.0
    avg_ms = sum(durations) / len(durations) if durations else 0.0
    # P95
    if durations:
        p95_idx = min(len(durations) - 1, int(len(durations) * 0.95))
        p95_ms = durations[p95_idx]
    else:
        p95_ms = 0.0

    # 综合分：成功率 50% + 速度 30% + 稳定性(1-arg_fail) 20%
    speed_score = 30.0
    if avg_ms > 0:
        # <100ms 满分，>5000ms 0 分，线性
        speed_score = max(0.0, 30.0 * (1 - (avg_ms - 100) / 4900))
    runtime_score = success_rate * 50 + speed_score + (1 - arg_fail_rate) * 20
    runtime_score = round(min(100.0, max(0.0, runtime_score)), 1)

    return {
        "name": name,
        "score": runtime_score,
        "grade": grade_from_score(runtime_score),
        "call_count": total,
        "success_rate": round(success_rate * 100, 1),
        "avg_ms": round(avg_ms, 1),
        "p95_ms": round(p95_ms, 1),
        "arg_fail_rate": round(arg_fail_rate * 100, 1),
    }


# ════════════════════════════════════════════════════════════
#  全量聚合报告
# ════════════════════════════════════════════════════════════


def score_all(reg: ToolRegistry, runtime_calls: dict[str, list[dict]] | None = None) -> dict[str, Any]:
    """生成全量评分报告。

    Args:
        reg: ToolRegistry 实例
        runtime_calls: 可选，{tool_name: [call_records]}；传入则附加运行时评分

    Returns:
        {
            "generated_at": float,
            "total_tools": int,
            "grade_distribution": {"A": n, "B": n, ...},
            "worst_5": [...],
            "untested": [names],
            "high_risk": [names],
            "tools": [per-tool score dicts],
        }
    """
    tool_names = list(reg.tool_names)
    tools_scored = []
    untested: list[str] = []
    high_risk_list: list[str] = []

    for name in tool_names:
        s = score_tool_static(name, reg)
        if s["dimensions"]["test_coverage"]["score"] == 0:
            untested.append(name)
        if s["dimensions"]["risk"]["score"] < 25:
            high_risk_list.append(name)

        # 附加运行时（若有数据）
        if runtime_calls and name in runtime_calls:
            s["runtime"] = score_tool_runtime(name, runtime_calls[name])

        tools_scored.append(s)

    # 按分数升序（最差在前）
    tools_sorted = sorted(tools_scored, key=lambda x: x["score"])
    worst_5 = [t["name"] for t in tools_sorted[:5]]

    # 分级分布
    grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0}
    for t in tools_scored:
        grade_dist[t["grade"]] = grade_dist.get(t["grade"], 0) + 1

    return {
        "generated_at": time.time(),
        "total_tools": len(tool_names),
        "grade_distribution": grade_dist,
        "average_score": round(sum(t["score"] for t in tools_scored) / max(len(tools_scored), 1), 1),
        "worst_5": worst_5,
        "untested": untested,
        "untested_count": len(untested),
        "high_risk": high_risk_list,
        "tools": tools_scored,
    }


def save_report(report: dict[str, Any], path: Path | None = None) -> Path:
    """把报告持久化到 output/tool_scorecard.json。"""
    from core.config import OUTPUT_DIR

    target = path or (OUTPUT_DIR / "tool_scorecard.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return target
