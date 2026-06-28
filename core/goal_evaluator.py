"""Goal Evaluator — 独立目标完成度评估器。

移植自 Kimi Code CLI 的 evaluator 理念：
  智能体自报告"完成" → Evaluator 独立检查 → 裁决（pass / fail / needs_fix）

与 GoalManager 集成：当 goal status 标记为 "completed" 时自动触发评估。

支持两种评估方式：
  1. LLM 语义评估：调用 Brain 比较 finish_line + boundaries 与实际产物
  2. 基于文件的启发式评估：检查文件存在性、大小、语法
"""

from __future__ import annotations

import enum
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class GoalVerdict(enum.Enum):
    PASS = "pass"          # 目标已达成
    FAIL = "fail"           # 目标未达成
    NEEDS_FIX = "needs_fix"  # 基本达成，但有可改进项


@dataclass
class EvaluationResult:
    """目标评估结果。"""

    goal_id: str
    verdict: GoalVerdict
    evidence: str = ""          # 评估依据（LLM 输出或启发式检查详情）
    issues: list[str] = field(default_factory=list)  # 发现的问题
    suggestions: list[str] = field(default_factory=list)  # 改进建议
    confidence: float = 1.0     # 评估置信度 (0.0-1.0)

    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "verdict": self.verdict.value,
            "evidence": self.evidence,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> EvaluationResult:
        return cls(
            goal_id=data["goal_id"],
            verdict=GoalVerdict(data["verdict"]),
            evidence=data.get("evidence", ""),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
            confidence=data.get("confidence", 1.0),
        )


class GoalEvaluator:
    """独立评估目标是否达成。

    用法:
        evaluator = GoalEvaluator()
        result = evaluator.evaluate(goal)
        if result.verdict == GoalVerdict.PASS:
            print("目标达成!")
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parent.parent

    def evaluate(
        self,
        goal: Any,  # Goal from core.goal_manager
        artifacts: list[str] | None = None,  # 产物文件路径列表
        use_llm: bool = True,
    ) -> EvaluationResult:
        """评估目标完成度。

        Args:
            goal: Goal 对象（含 intent, finish_line, boundaries, evidence）
            artifacts: 可选，工作产物文件路径列表
            use_llm: 是否使用 LLM 语义评估

        Returns:
            EvaluationResult 含裁决 + 证据 + 问题列表
        """
        issues: list[str] = []
        suggestions: list[str] = []

        # Step 1: 启发式检查 — 文件存在性 / 大小
        if artifacts:
            for art in artifacts:
                check = self._check_file(art)
                if check:
                    issues.append(check)

        # Step 2: 检查 boundaries 约束
        boundaries = getattr(goal, "boundaries", "")
        if boundaries:
            b_issues = self._check_boundaries(boundaries, artifacts or [])
            issues.extend(b_issues)

        # Step 3: LLM 语义评估
        evidence = getattr(goal, "evidence", "")
        if use_llm and (goal.finish_line if hasattr(goal, "finish_line") else goal.intent):
            llm_result = self._llm_evaluate(
                intent=getattr(goal, "intent", ""),
                finish_line=getattr(goal, "finish_line", ""),
                boundaries=boundaries,
                evidence=evidence,
                issues=issues,
            )
            if llm_result:
                return llm_result

        # 无 LLM 时：基于启发式结果判定
        if not issues:
            return EvaluationResult(
                goal_id=getattr(goal, "id", ""),
                verdict=GoalVerdict.PASS,
                evidence=f"启发式检查通过。产物: {artifacts}",
                issues=[],
                suggestions=[],
                confidence=0.7,
            )

        return EvaluationResult(
            goal_id=getattr(goal, "id", ""),
            verdict=GoalVerdict.NEEDS_FIX,
            evidence=f"启发式检查发现问题: {issues}",
            issues=issues,
            suggestions=suggestions,
            confidence=0.5,
        )

    def _check_file(self, path: str) -> str | None:
        """检查单个文件产物。返回问题描述或 None。"""
        full = Path(path)
        if not full.is_absolute():
            full = self.root / path
        if not full.exists():
            return f"产物文件不存在: {path}"
        if full.stat().st_size == 0:
            return f"产物文件为空: {path}"
        return None

    def _check_boundaries(self, boundaries_text: str, artifacts: list[str]) -> list[str]:
        """检查是否违反 boundaries 约束。

        解析 boundaries 文本中的约束条件（如"不要修改 X"、"只应在 Y 目录"），
        做简单的文件路径模式匹配。
        """
        issues: list[str] = []
        lines = boundaries_text.split("\n")
        for line in lines:
            line = line.strip().lower()
            if "do not modify" in line or "不要修改" in line or "禁止修改" in line:
                # Extract the target path/file
                import re
                targets = re.findall(r"[`'\"]([^`'\"]+)[`'\"]", line)
                for target in targets:
                    for art in artifacts:
                        if target.lower() in art.lower():
                            issues.append(f"Boundary violation: 可能修改了禁止区域 {target} → {art}")
            if "only in" in line or "仅在" in line or "限定在" in line:
                import re
                targets = re.findall(r"[`'\"]([^`'\"]+)[`'\"]", line)
                for target in targets:
                    for art in artifacts:
                        if target.lower() not in art.lower():
                            issues.append(f"Boundary violation: 产物 {art} 不在允许目录 {target}")
        return issues

    def _llm_evaluate(
        self,
        intent: str,
        finish_line: str,
        boundaries: str,
        evidence: str,
        issues: list[str],
    ) -> EvaluationResult | None:
        """使用 LLM 进行语义评估。失败时返回 None，由调用方 fallback 到启发式评估。"""
        try:
            from core.brain import Brain

            brain = Brain()
            prompt = self._build_eval_prompt(intent, finish_line, boundaries, evidence, issues)
            result = brain.quick_chat(prompt)
            return self._parse_llm_result(result, intent, finish_line)
        except (ImportError, OSError, RuntimeError, ValueError, TypeError):
            return None

    def _build_eval_prompt(
        self,
        intent: str,
        finish_line: str,
        boundaries: str,
        evidence: str,
        issues: list[str],
    ) -> str:
        """构建评估 prompt。"""
        parts = [
            "你是一个独立的目标完成度评估器。请严格判断以下目标是否已达成。",
            "",
            f"目标意图: {intent}",
        ]
        if finish_line:
            parts.append(f"完成标准: {finish_line}")
        if boundaries:
            parts.append(f"约束条件: {boundaries}")
        if evidence:
            parts.append(f"智能体自报证据: {evidence}")
        if issues:
            parts.append(f"启发式检查发现的问题: {'; '.join(issues)}")

        parts.extend([
            "",
            "请给出裁决，仅输出 JSON：",
            '{"verdict": "pass"|"fail"|"needs_fix", "evidence": "判定依据", "issues": ["问题1"], "suggestions": ["建议1"], "confidence": 0.0-1.0}',
        ])
        return "\n".join(parts)

    def _parse_llm_result(
        self,
        llm_output: str,
        intent: str,
        finish_line: str,
    ) -> EvaluationResult:
        """解析 LLM 输出为 EvaluationResult。"""
        # 尝试提取 JSON
        try:
            # Find JSON block
            start = llm_output.find("{")
            end = llm_output.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(llm_output[start:end])
                return EvaluationResult(
                    goal_id="",
                    verdict=GoalVerdict(data.get("verdict", "needs_fix")),
                    evidence=data.get("evidence", llm_output[:500]),
                    issues=data.get("issues", []),
                    suggestions=data.get("suggestions", []),
                    confidence=float(data.get("confidence", 0.5)),
                )
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        # Fallback: text-based heuristic
        llm_lower = llm_output.lower()
        if '"pass"' in llm_lower or '"verdict": "pass"' in llm_lower:
            verdict = GoalVerdict.PASS
        elif '"fail"' in llm_lower:
            verdict = GoalVerdict.FAIL
        else:
            verdict = GoalVerdict.NEEDS_FIX

        return EvaluationResult(
            goal_id="",
            verdict=verdict,
            evidence=llm_output[:500],
            issues=[],
            suggestions=[],
            confidence=0.5,
        )


# ── Module-level singleton ──

_evaluator: GoalEvaluator | None = None


def get_evaluator() -> GoalEvaluator:
    global _evaluator
    if _evaluator is None:
        _evaluator = GoalEvaluator()
    return _evaluator


# ── Tool definition ──

GOAL_EVALUATE_TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "goal_evaluate",
        "description": (
            "独立评估当前目标是否已达成。"
            "根据 finish_line（完成标准）、boundaries（约束）和实际产物，"
            "给出 pass / fail / needs_fix 裁决。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal_id": {
                    "type": "string",
                    "description": "目标 ID，不传则评估当前活跃目标",
                },
                "artifacts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "工作产物文件路径列表（可选）",
                },
            },
            "required": [],
        },
    },
}


def _exec_goal_evaluate(**kwargs) -> str:
    """执行目标评估。"""
    from core.goal_manager import get_goal_manager

    gm = get_goal_manager()
    goal_id = kwargs.get("goal_id", "")
    goal = gm.get(goal_id) if goal_id else gm.get()

    if goal is None:
        return "[错误] 没有活跃的目标可以评估。"

    artifacts = kwargs.get("artifacts", [])
    evaluator = get_evaluator()
    result = evaluator.evaluate(goal, artifacts=artifacts)

    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
