"""Plan-Verify-Replan Closed Loop — 结构化规划-验证闭环。

把 ENGINEERING_DISCIPLINE 里"探索→计划→执行→验证→报告"从 prompt 建议
变成代码强制执行：每一步都有结构化输出校验，验证失败自动 re-plan。

核心组件:
- PlanStep / Plan / VerificationResult — 结构化数据模型
- validate_plan() — 计划合法性校验
- PlanVerifyLoop — 主循环控制器 (plan → execute → verify → replan)
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "PlanStep",
    "Plan",
    "VerificationResult",
    "validate_plan",
    "PlanVerifyLoop",
]

ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════
# Structured Data Models
# ═══════════════════════════════════════════════════════════════


@dataclass
class PlanStep:
    """结构化的计划步骤，强制 LLM 输出符合此 schema。"""

    id: str
    description: str
    action: str = "execute"  # "explore" | "plan" | "execute" | "verify" | "report"
    tool: str = ""
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    success_criteria: str = ""
    verify_method: str | None = None  # "syntax" | "test:<target>" | "grep:<pattern>" | "llm" | None


@dataclass
class Plan:
    """完整的计划，含目标、步骤、最大重试次数。"""

    goal: str
    finish_line: str = ""  # 完成标准
    steps: list[PlanStep] = field(default_factory=list)
    max_replans: int = 3
    current_attempt: int = 0


@dataclass
class VerificationResult:
    """验证结果。"""

    step_id: str
    passed: bool
    evidence: str = ""
    failure_reason: str = ""
    suggestion: str = ""


# ═══════════════════════════════════════════════════════════════
# Plan Validator
# ═══════════════════════════════════════════════════════════════


def validate_plan(plan: Plan, registry: Any) -> list[str]:
    """验证计划合法性，返回错误列表（空 = 通过）。

    校验项:
    1. 必须有 explore 步骤（先探索再行动）
    2. 必须有 verify 步骤（验证目标是否达成）
    3. depends_on 引用的 step id 必须存在
    4. tool 名必须在 ToolRegistry 中存在
    5. finish_line 不能为空
    """
    errors: list[str] = []

    # 1. 必须有 explore 步骤
    has_explore = any(s.action == "explore" for s in plan.steps)
    if not has_explore:
        errors.append("计划必须包含 explore 步骤（先探索再行动）")

    # 2. 必须有 verify 步骤
    has_verify = any(s.action == "verify" for s in plan.steps)
    if not has_verify:
        errors.append("计划必须包含 verify 步骤（验证目标是否达成）")

    # 3. 依赖检查
    step_ids = {s.id for s in plan.steps}
    for s in plan.steps:
        for dep in s.depends_on:
            if dep not in step_ids:
                errors.append(f"步骤 {s.id} 依赖不存在的步骤: {dep}")

    # 4. 工具存在性检查
    has_tool_check = hasattr(registry, "has") and callable(getattr(registry, "has"))
    for s in plan.steps:
        if s.tool and has_tool_check and not registry.has(s.tool):
            errors.append(f"步骤 {s.id} 使用不存在的工具: {s.tool}")

    # 5. finish_line 检查
    if not plan.finish_line.strip():
        errors.append("必须明确定义完成标准（finish_line）")

    return errors


# ═══════════════════════════════════════════════════════════════
# Plan-Verify-Replan Loop
# ═══════════════════════════════════════════════════════════════


class PlanVerifyLoop:
    """规划-验证闭环控制器。

    主循环: plan → execute → verify → 失败则 re-plan（最多 max_replans 次）。
    """

    def __init__(
        self,
        llm_callable: Callable[[str], str],
        tool_executor: Callable[[str, dict], str],
        registry: Any,
        max_replans: int = 3,
    ) -> None:
        self.llm = llm_callable
        self.tool_exec = tool_executor
        self.registry = registry
        self.max_replans = max_replans

    def execute_with_replan(self, goal: str, finish_line: str = "", initial_plan: Plan | None = None) -> dict:
        """主循环：plan → execute → verify → 失败则 re-plan。

        Args:
            goal: 任务目标
            finish_line: 完成标准
            initial_plan: 可选的预设计划（由 LLM 通过 execute_plan 工具传入）

        Returns:
            结构化结果 dict
        """
        # 1. 使用预设计划或生成新计划
        if initial_plan:
            plan = initial_plan
            plan.finish_line = finish_line or plan.finish_line
        else:
            plan = self._generate_plan(goal, finish_line)

        errors = validate_plan(plan, self.registry)
        if errors:
            return {"status": "plan_invalid", "goal": goal, "errors": errors}

        for attempt in range(1, self.max_replans + 1):
            plan.current_attempt = attempt

            # 2. 执行计划
            result = self._execute_plan(plan)

            # 3. 验证每个有 verify_method 的步骤
            verification = self._verify_all_steps(plan, result)

            # 4. 全部通过 → 返回成功
            if all(v.passed for v in verification):
                return {
                    "status": "completed",
                    "goal": goal,
                    "finish_line": plan.finish_line,
                    "attempts": attempt,
                    "verification": [asdict(v) for v in verification],
                    "result": result,
                }

            # 5. 有失败 → re-plan（如果还有预算）
            if attempt < self.max_replans:
                failed = [v for v in verification if not v.passed]
                plan = self._replan(plan, failed, result)
                errors = validate_plan(plan, self.registry)
                if errors:
                    return {"status": "replan_invalid", "goal": goal, "attempt": attempt, "errors": errors}
            else:
                # 用完所有重试
                return {
                    "status": "exhausted",
                    "goal": goal,
                    "finish_line": plan.finish_line,
                    "attempts": attempt,
                    "verification": [asdict(v) for v in verification],
                    "result": result,
                }

    # ── 内部方法 ──

    def _generate_plan(self, goal: str, finish_line: str) -> Plan:
        """使用 LLM 生成初始计划。"""
        prompt = f"""你是计划生成引擎。给定目标和完成标准，生成 3-5 个步骤的结构化计划。

目标: {goal}
完成标准: {finish_line}

规则:
1. 第一步必须是 explore（读取相关文件理解现状）
2. 必须包含至少一个 verify 步骤（验证目标是否达成）
3. 每个步骤必须指定 tool、depends_on、success_criteria
4. verify_method 可选: "syntax" | "test:<target>" | "grep:<pattern>" | "llm" | null

返回格式（仅 JSON 数组）:
[{{"id":"s1","description":"读取错误日志","action":"explore","tool":"read_file","args":{{"path":"output/last_error.txt"}},"depends_on":[],"success_criteria":"成功读取文件","verify_method":null}},
 {{"id":"s2","description":"实施修复","action":"execute","tool":"edit_file","args":{{"path":"...","old_text":"...","new_text":"..."}},"depends_on":["s1"],"success_criteria":"编辑成功","verify_method":"syntax"}},
 {{"id":"s3","description":"运行测试","action":"verify","tool":"run_test","args":{{}},"depends_on":["s2"],"success_criteria":"所有测试通过","verify_method":"test"}}]
"""
        response = self.llm(prompt)
        json_str = response.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1]) if len(lines) > 2 else json_str
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()

        step_data = json.loads(json_str)
        steps = [PlanStep(**s) for s in step_data]
        return Plan(goal=goal, finish_line=finish_line, steps=steps, max_replans=self.max_replans)

    def _execute_plan(self, plan: Plan) -> dict:
        """执行计划的所有步骤（依赖顺序）。"""
        results: dict[str, str] = {}
        step_map = {s.id: s for s in plan.steps}

        # 拓扑排序 waves
        executed: set[str] = set()
        remaining = list(plan.steps)

        while remaining:
            wave = []
            still = []
            for s in remaining:
                deps = set(s.depends_on)
                if deps.issubset(executed):
                    wave.append(s)
                else:
                    still.append(s)

            if not wave:
                # 无法继续：循环依赖或缺失
                for s in still:
                    results[s.id] = f"[跳过] 依赖无法满足: {s.depends_on}"
                break

            for s in wave:
                try:
                    result = self.tool_exec(s.tool, s.args)
                    results[s.id] = str(result)[:1000]
                except (OSError, ValueError, RuntimeError) as e:
                    results[s.id] = f"[失败] {type(e).__name__}: {e}"

            executed.update(s.id for s in wave)
            remaining = still

        return results

    def _verify_all_steps(self, plan: Plan, results: dict[str, str]) -> list[VerificationResult]:
        """验证所有有 verify_method 的步骤。"""
        verification: list[VerificationResult] = []
        for s in plan.steps:
            v = self._verify_step(s, results.get(s.id, ""))
            verification.append(v)
        return verification

    def _verify_step(self, step: PlanStep, result: str) -> VerificationResult:
        """根据 verify_method 执行验证。"""
        if step.verify_method is None:
            return VerificationResult(step_id=step.id, passed=True, evidence="无需验证")

        method = step.verify_method

        # 策略 1: 语法检查
        if method == "syntax":
            try:
                import ast

                for sd in (ROOT / "core", ROOT / "engines", ROOT / "pipeline"):
                    if sd.exists():
                        for pf in sd.rglob("*.py"):
                            if "__pycache__" not in pf.parts:
                                ast.parse(pf.read_text(encoding="utf-8"))
                # Also scan root-level .py files
                for pf in ROOT.glob("*.py"):
                    if "__pycache__" not in pf.parts:
                        ast.parse(pf.read_text(encoding="utf-8"))
                return VerificationResult(step_id=step.id, passed=True, evidence="语法检查通过")
            except SyntaxError as e:
                return VerificationResult(step_id=step.id, passed=False, failure_reason=f"语法错误: {e}")

        # 策略 2: 测试检查
        if method.startswith("test"):
            target = method.split(":", 1)[1] if ":" in method else "tests/"
            try:
                from core.pytest_runner import run_pytest_safe

                r = run_pytest_safe(test_target=target, timeout=30, cwd=ROOT)
                if r.returncode == 0:
                    return VerificationResult(step_id=step.id, passed=True, evidence="测试通过")
                return VerificationResult(
                    step_id=step.id,
                    passed=False,
                    failure_reason=f"测试失败 (exit={r.returncode})",
                    suggestion=(r.stdout or r.stderr or "")[-500:],
                )
            except (ImportError, OSError) as e:
                return VerificationResult(step_id=step.id, passed=False, failure_reason=f"测试模块不可用: {e}")

        # 策略 3: grep 验证（检查某个 pattern 是否出现在代码中）
        if method.startswith("grep"):
            pattern = method.split(":", 1)[1] if ":" in method else ""
            try:
                r = subprocess.run(["rg", "-l", pattern, "core/"], capture_output=True, text=True, cwd=ROOT)
                if r.returncode == 0:
                    files = r.stdout.strip().split("\n")
                    return VerificationResult(
                        step_id=step.id, passed=True, evidence=f"在 {len(files)} 个文件中找到 '{pattern}'"
                    )
                return VerificationResult(step_id=step.id, passed=False, failure_reason=f"未在代码中找到 '{pattern}'")
            except FileNotFoundError:
                # rg 不可用时退化为 Python 搜索
                return self._verify_grep_fallback(pattern)

        # 策略 4: LLM 评估
        if method == "llm":
            try:
                eval_prompt = (
                    f"评估以下任务是否完成。\n"
                    f"目标: {step.success_criteria}\n"
                    f"实际结果: {result[:2000]}\n"
                    f'只返回 JSON: {{"passed": true/false, "reason": "..."}}'
                )
                response = self.llm(eval_prompt)
                data = json.loads(response.strip())
                return VerificationResult(
                    step_id=step.id,
                    passed=data.get("passed", False),
                    evidence=data.get("reason", ""),
                )
            except (json.JSONDecodeError, Exception) as e:
                return VerificationResult(step_id=step.id, passed=False, failure_reason=f"LLM 评估失败: {e}")

        return VerificationResult(step_id=step.id, passed=False, failure_reason=f"未知验证方法: {method}")

    def _verify_grep_fallback(self, pattern: str) -> VerificationResult:
        """rg 不可用时的 Python 搜索回退。"""
        found_files = []
        for sd in (ROOT / "core", ROOT / "engines"):
            if sd.exists():
                for pf in sd.rglob("*.py"):
                    try:
                        content = pf.read_text(encoding="utf-8")
                        if pattern in content:
                            found_files.append(str(pf.relative_to(ROOT)))
                    except (UnicodeDecodeError, OSError):
                        pass
        if found_files:
            return VerificationResult(
                step_id="grep_fallback", passed=True, evidence=f"在 {len(found_files)} 个文件中找到 '{pattern}'"
            )
        return VerificationResult(step_id="grep_fallback", passed=False, failure_reason=f"未在代码中找到 '{pattern}'")

    def _replan(self, original_plan: Plan, failed_verifications: list[VerificationResult], last_result: dict) -> Plan:
        """基于失败的验证结果重新规划。"""
        failure_context = []
        for v in failed_verifications:
            failure_context.append(f"步骤 {v.step_id}: {v.failure_reason}. 建议: {v.suggestion}")

        prompt = (
            f"你是计划重规划引擎。原计划执行失败，请分析失败原因并制定新计划。\n\n"
            f"原目标: {original_plan.goal}\n"
            f"完成标准: {original_plan.finish_line}\n\n"
            f"失败信息:\n{''.join(failure_context)}\n\n"
            f"上次执行结果摘要:\n{json.dumps(last_result, ensure_ascii=False, indent=2)[:2000]}\n\n"
            f"请生成新的计划（JSON 数组格式），重点关注：\n"
            f"1. 先诊断失败根因\n"
            f"2. 采用不同于上次的方法\n"
            f'3. 每个步骤必须有 success_criteria 和 verify_method\n\n'
            f'返回格式:\n'
            f'[{{"id":"s1","description":"...","action":"explore","tool":"read_file",'
            f'"args":{{"path":"..."}},"depends_on":[],"success_criteria":"...","verify_method":null}}, ...]'
        )

        response = self.llm(prompt)
        json_str = response.strip()
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            json_str = "\n".join(lines[1:-1]) if len(lines) > 2 else json_str
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()

        step_data = json.loads(json_str)
        steps = [PlanStep(**s) for s in step_data]

        return Plan(
            goal=original_plan.goal,
            finish_line=original_plan.finish_line,
            steps=steps,
            max_replans=original_plan.max_replans,
            current_attempt=original_plan.current_attempt,
        )
