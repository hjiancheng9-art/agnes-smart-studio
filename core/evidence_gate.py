"""
Evidence Gate — CRUX 最终答案前的证据门禁
==========================================
确保复杂任务的最终答案必须有证据支撑才能通过。

规则:
1. 每个结论必须有 evidence 引用（代码行/文件/日志/测试结果）
2. 无证据的结论被拦截
3. 证据不足（只有泛泛引用）给出警告
4. 门禁结果记录到 trace

使用方法:
    gate = EvidenceGate()
    result = gate.check(question="是否修复了", evidence=["src/auth.py:42 已添加判空"])
    # result.passed = True/False, result.reason = 原因
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """门禁检查结果"""

    passed: bool
    reason: str = ""
    evidence_count: int = 0
    evidence_quality: str = ""  # strong / weak / none
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "evidence_count": self.evidence_count,
            "evidence_quality": self.evidence_quality,
            "suggestions": self.suggestions[:3],
        }


class EvidenceGate:
    """证据门禁 — 验证最终答案的证据充分性"""

    # ── 高质量证据模式 ──
    HIGH_QUALITY_PATTERNS = [
        r"\w+\.\w+:\d+",  # file.py:42
        r"src/[\w/.]+:\d+",  # src/auth/handler.py:42
        r"第\s*\d+\s*行",  # 第 42 行
        r"line\s*\d+",  # line 42
        r"`[\w/.]+\.\w+`",  # `src/auth.py`
        r"```[\s\S]{10,}```",  # 代码块（至少10字符）
        r"test.*pass|测试.*通过",  # 测试通过
        r"exit.*code.*0",  # exit code 0
    ]

    # ── 弱证据模式（泛泛引用） ──
    LOW_QUALITY_PATTERNS = [
        r"如上所述|如前所述|根据分析|综上所述",
        r"as mentioned|as described|as analyzed|in conclusion",
        r"我认为|我觉得|看起来|可能好像",
        r"i think|i believe|it seems|probably|maybe",
    ]

    def check_text(self, answer: str, question: str = "") -> GateResult:
        """检查答案文本的证据充分性"""
        evidence = self._extract_evidence(answer)
        return self._evaluate_evidence(evidence, answer, question)

    def check_evidence_list(self, evidence_list: list[str], question: str = "", answer: str = "") -> GateResult:
        """检查显式提供的证据列表"""
        return self._evaluate_evidence(evidence_list, answer, question)

    def _extract_evidence(self, text: str) -> list[str]:
        """从文本中自动提取证据引用"""
        evidence: list[str] = []

        # 1. 找高质量证据
        for pattern in self.HIGH_QUALITY_PATTERNS:
            matches = re.findall(pattern, text)
            for m in matches:
                cleaned = m.strip()
                if cleaned and cleaned not in evidence:
                    evidence.append(cleaned)

        # 2. 找文件名 + 行号组合
        file_line = re.findall(r"([\w/]+\.\w+):(\d+)", text)
        for f, ln in file_line:
            ref = f"{f}:{ln}"
            if ref not in evidence:
                evidence.append(ref)

        return evidence

    def _evaluate_evidence(self, evidence: list[str], answer: str, question: str) -> GateResult:
        """评估证据"""
        if not evidence:
            return GateResult(
                passed=False,
                reason="无证据引用。必须引用具体代码行、文件位置或测试结果。",
                evidence_count=0,
                evidence_quality="none",
                suggestions=["添加具体文件:行号引用", "添加测试结果引用", "添加代码片段"],
            )

        # 统计高质量证据
        high_quality_count = 0
        for ev in evidence:
            if any(re.match(p, ev) for p in self.HIGH_QUALITY_PATTERNS):
                high_quality_count += 1

        # 统计弱证据
        low_quality_count = 0
        for ev in evidence:
            if any(re.search(p, ev) for p in self.LOW_QUALITY_PATTERNS):
                low_quality_count += 1

        total_valid = len(evidence) - low_quality_count

        if total_valid == 0:
            return GateResult(
                passed=False,
                reason=f"有 {len(evidence)} 条引用但都是泛泛之谈，需要更具体的证据",
                evidence_count=len(evidence),
                evidence_quality="weak",
                suggestions=["使用具体文件:行号", "引用测试输出", "引用实际日志"],
            )

        if high_quality_count < 1:
            return GateResult(
                passed=False,
                reason="没有高质量证据，至少需要 1 个",
                evidence_count=len(evidence),
                evidence_quality="weak",
                suggestions=["提供具体文件:行号引用", "如果涉及代码修改，必须引用修改的文件"],
            )

        # 通过
        quality = "strong" if high_quality_count >= 3 else "medium"
        return GateResult(
            passed=True,
            reason=f"通过: {high_quality_count} 个高质量证据",
            evidence_count=high_quality_count,
            evidence_quality=quality,
        )


# ── 快捷检查函数 ──


def check_answer(text: str) -> dict[str, Any]:
    """快捷检查答案文本"""
    gate = EvidenceGate()
    result = gate.check_text(text)
    return result.to_dict()


def check_evidence(evidence: list[str], question: str = "") -> dict[str, Any]:
    """快捷检查证据列表"""
    gate = EvidenceGate()
    result = gate.check_evidence_list(evidence, question)
    return result.to_dict()
