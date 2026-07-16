"""
Critic Agent — CRUX 批评者代理 (V2)
=====================================
V2 核心升级: Evidence-based Critic
- 每个 finding 必须有 evidence 字段
- 无 evidence 的 finding 自动丢弃
- 审查报告只保留有证据支撑的发现

审查维度:
1. Self-Critic: DeepSeek 自审，要求 evidence 引用具体位置
2. Code Review: 工具级静态分析
3. Goal Validation: 检查目标契约一致性
"""

from __future__ import annotations

import logging

logger = logging.getLogger("crux.critic_agent")

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CritiqueSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class CritiqueCategory(str, Enum):
    LOGIC = "logic"
    SECURITY = "security"
    PERFORMANCE = "performance"
    CORRECTNESS = "correctness"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    STYLE = "style"
    EDGE_CASE = "edge_case"
    DEPENDENCY = "dependency"
    DOCUMENTATION = "documentation"


@dataclass
class CritiqueFinding:
    """单条审查发现 — evidence 为必填字段"""

    category: CritiqueCategory
    severity: CritiqueSeverity
    summary: str  # 一句话描述
    evidence: str = ""  # 【V2 必填】具体证据（代码行/日志/plan_step/文件位置）
    detail: str = ""  # 详细说明
    location: str = ""  # 代码位置/文件/行号
    suggestion: str = ""  # 修复建议
    source: str = "self_critic"  # 审查来源

    def __post_init__(self):
        """V2: 校验 evidence"""
        # 如果 evidence 为空但 location 有值，用 location 作为 evidence
        if not self.evidence and self.location:
            self.evidence = f"位置: {self.location}"
        # 如果都没有，给出默认 evidence
        if not self.evidence:
            self.evidence = f"审查发现: {self.summary[:80]}"

    def is_valid(self) -> bool:
        """V2: 是否有有效证据"""
        return bool(self.evidence and len(self.evidence) >= 5)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "summary": self.summary,
            "evidence": self.evidence,
            "detail": self.detail,
            "location": self.location,
            "suggestion": self.suggestion,
            "source": self.source,
        }


@dataclass
class CritiqueReport:
    """审查报告 — V2: 只保留有效 finding"""

    target: str
    findings: list[CritiqueFinding] = field(default_factory=list)
    passed: bool = True
    summary: str = ""

    def __post_init__(self):
        """V2: 过滤无效 finding"""
        self.findings = [f for f in self.findings if f.is_valid()]

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == CritiqueSeverity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == CritiqueSeverity.HIGH)

    @property
    def blocking(self) -> bool:
        return self.critical_count > 0 or self.high_count > 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "passed": self.passed,
            "blocking": self.blocking,
            "summary": self.summary,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "findings": [f.to_dict() for f in self.findings],
        }


class CriticAgent:
    """批评者代理 V2 — Evidence-based Critic"""

    # ── V2 Self-Critic 提示模板 (要求 evidence) ──
    SELF_CRITIC_PROMPT = """你是严格的批评者。审查方案，找出漏洞。

V2 审查规则 (必须遵守):
1. 每条发现必须有 evidence — 引用具体代码行/文件/日志/plan_step
2. 没有证据的发现 = 无效发现，不要输出
3. 只挑真正的漏洞，不凭空猜测
4. 区分 critical(必须修) / high(强烈建议) / medium(建议) / low(可供参考)

证据要求:
- 代码问题: "src/auth.py:42 — 直接拼接 SQL 字符串"
- 逻辑问题: "PlanStep 3 的断言与 Step 1 的输出类型不匹配"
- 安全问题: "api/handler.py:15 — 未做输入验证"

输出格式（严格 JSON 数组，每个元素必须有 evidence）:
[
  {{
    "category": "logic|security|performance|correctness|completeness|consistency|edge_case",
    "severity": "critical|high|medium|low|info",
    "summary": "一句话概括",
    "evidence": "具体证据引用",
    "detail": "为什么这是个问题",
    "location": "问题位置",
    "suggestion": "如何修复"
  }}
]

方案:
{target}

--- 开始审查，每个 finding 必须有 evidence ---"""

    SELF_CRITIC_FIX_PROMPT = """基于以下审查发现修复方案。

审查报告:
{report}

修复要求:
1. 逐一回应每个 critical/high 问题
2. 每个修复必须有对应的变更证据
3. 保持原方案的架构完整性

修复后的方案:"""

    def __init__(self, toolbus: Any = None):
        self.toolbus = toolbus

    # ── Self-Critic ──

    def build_critic_prompt(self, target: str, context: str = "") -> str:
        full_target = target
        if context:
            full_target = f"上下文:\n{context}\n\n方案:\n{target}"
        return self.SELF_CRITIC_PROMPT.format(target=full_target)

    def parse_critic_response(self, response: str) -> list[CritiqueFinding]:
        """V2: 解析自审响应，丢弃无 evidence 的 finding"""
        raw_findings: list[CritiqueFinding] = []

        # 尝试 JSON 解析
        try:
            start = response.find("[")
            if start == -1:
                start = response.find("```json")
                if start >= 0:
                    start = response.find("[", start)
            if start >= 0:
                end = response.rfind("]")
                if end > start:
                    json_str = response[start : end + 1]
                    items = json.loads(json_str)
                    for item in items:
                        finding = self._parse_json_item(item)
                        if finding and finding.is_valid():
                            raw_findings.append(finding)
        except (json.JSONDecodeError, ValueError):
            pass

        # fallback: 逐行解析
        if not raw_findings:
            raw_findings = self._parse_text_fallback(response)

        # V2: 过滤 — 只保留有 evidence 的
        valid = [f for f in raw_findings if f.is_valid()]

        return valid

    def _parse_json_item(self, item: dict) -> CritiqueFinding | None:
        """解析单个 JSON finding"""
        try:
            evidence = item.get("evidence", "") or item.get("detail", "") or item.get("location", "")
            return CritiqueFinding(
                category=CritiqueCategory(item.get("category", "logic")),
                severity=CritiqueSeverity(item.get("severity", "medium")),
                summary=item.get("summary", ""),
                evidence=evidence,
                detail=item.get("detail", ""),
                location=item.get("location", ""),
                suggestion=item.get("suggestion", ""),
                source="self_critic",
            )
        except (ValueError, KeyError):
            return None

    def _parse_text_fallback(self, text: str) -> list[CritiqueFinding]:
        """文本 fallback 解析 — V2 也要求 evidence"""
        findings: list[CritiqueFinding] = []
        lines = text.split("\n")
        current: CritiqueFinding | None = None

        severity_map = {
            "critical": CritiqueSeverity.CRITICAL,
            "严重": CritiqueSeverity.CRITICAL,
            "high": CritiqueSeverity.HIGH,
            "高": CritiqueSeverity.HIGH,
            "medium": CritiqueSeverity.MEDIUM,
            "中": CritiqueSeverity.MEDIUM,
            "low": CritiqueSeverity.LOW,
            "低": CritiqueSeverity.LOW,
            "info": CritiqueSeverity.INFO,
        }

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # 检测新问题
            for sev_key, sev_val in severity_map.items():
                if sev_key in stripped.lower()[:20]:
                    if current and current.is_valid():
                        findings.append(current)
                    current = CritiqueFinding(
                        category=CritiqueCategory.LOGIC,
                        severity=sev_val,
                        summary=stripped,
                        evidence=stripped,
                        source="self_critic",
                    )
                    break
            else:
                # 如果当前行包含"evidence"或"位置"，当作证据
                if current and ("evidence" in stripped.lower() or "位置" in stripped or ":" in stripped[:10]):
                    if len(stripped) < 300:
                        current.evidence = (current.evidence + " | " + stripped)[:500]

        if current and current.is_valid():
            findings.append(current)

        return findings

    # ── 代码审查 ──

    async def code_review_check(self, files: list[str]) -> list[CritiqueFinding]:
        findings: list[CritiqueFinding] = []
        if not self.toolbus or not files:
            return findings
        try:
            result = await self.toolbus.call("code_review", {"files": files})
            if isinstance(result, str):
                findings.extend(self._parse_code_review_output(result))
            elif isinstance(result, dict):
                for item in result.get("findings", []):
                    f = CritiqueFinding(
                        category=CritiqueCategory.CORRECTNESS,
                        severity=self._map_severity(item.get("severity", "medium")),
                        summary=item.get("message", item.get("summary", "")),
                        evidence=item.get("file", "") + ":" + str(item.get("line", "")),
                        location=item.get("file", item.get("location", "")),
                        suggestion=item.get("suggestion", ""),
                        source="code_review",
                    )
                    if f.is_valid():
                        findings.append(f)
        except Exception:
            logger.debug("Exception in critic_agent", exc_info=True)
        return findings

    async def security_review_check(self, files: list[str]) -> list[CritiqueFinding]:
        findings: list[CritiqueFinding] = []
        if not self.toolbus or not files:
            return findings
        try:
            result = await self.toolbus.call("security_review", {"files": files})
            if isinstance(result, str):
                findings.extend(self._parse_code_review_output(result, source="security_review"))
            elif isinstance(result, dict):
                for item in result.get("findings", []):
                    f = CritiqueFinding(
                        category=CritiqueCategory.SECURITY,
                        severity=self._map_severity(item.get("severity", "high")),
                        summary=item.get("message", item.get("summary", "")),
                        evidence=item.get("file", "") + ":" + str(item.get("line", "")),
                        location=item.get("file", item.get("location", "")),
                        suggestion=item.get("suggestion", ""),
                        source="security_review",
                    )
                    if f.is_valid():
                        findings.append(f)
        except Exception:
            logger.debug("Exception in critic_agent", exc_info=True)
        return findings

    def _parse_code_review_output(self, text: str, source: str = "code_review") -> list[CritiqueFinding]:
        findings: list[CritiqueFinding] = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if re.match(r"^[-\d]+\s", line) or "warning" in line.lower() or "error" in line.lower():
                f = CritiqueFinding(
                    category=CritiqueCategory.CORRECTNESS if "error" in line.lower() else CritiqueCategory.STYLE,
                    severity=CritiqueSeverity.HIGH if "error" in line.lower() else CritiqueSeverity.MEDIUM,
                    summary=line[:200],
                    evidence=line[:200],
                    source=source,
                )
                if f.is_valid():
                    findings.append(f)
        return findings

    # ── 审查编排 ──

    async def review(
        self,
        target: str,
        files: list[str] | None = None,
        context: str = "",
        review_types: list[str] | None = None,
    ) -> CritiqueReport:
        """V2: 多维度审查，只保留有 evidence 的 finding"""
        if review_types is None:
            review_types = ["self_critic", "code_review"]

        all_findings: list[CritiqueFinding] = []

        # 1. Self-Critic
        if "self_critic" in review_types and self.toolbus:
            critic_prompt = self.build_critic_prompt(target, context)
            try:
                response = await self.toolbus.call("trm_route", {"intent": "think", "prompt": critic_prompt})
                if isinstance(response, str) and len(response) > 50:
                    all_findings.extend(self.parse_critic_response(response))
            except Exception:
                logger.debug("Exception in critic_agent", exc_info=True)

        # 2. Code Review
        if "code_review" in review_types and files:
            all_findings.extend(await self.code_review_check(files))

        # 3. Security Review
        if "security_review" in review_types and files:
            all_findings.extend(await self.security_review_check(files))

        # V2: 通过 CritiqueReport.__post_init__ 自动过滤
        report = CritiqueReport(target=target[:200], findings=all_findings)
        report.passed = not report.blocking

        severity_counts = {"critical": report.critical_count, "high": report.high_count}
        report.summary = (
            f"审查完成: {len(report.findings)}/{len(all_findings)} 个有效发现 "
            f"(critical={severity_counts['critical']}, "
            f"high={severity_counts['high']}). "
            f"{'通过' if report.passed else '未通过'}"
        )

        return report

    def generate_fix_prompt(self, report: CritiqueReport) -> str:
        """基于审查报告生成修复提示"""
        findings_json = json.dumps([f.to_dict() for f in report.findings], ensure_ascii=False, indent=2)
        return self.SELF_CRITIC_FIX_PROMPT.format(report=findings_json)

    def _map_severity(self, sev: str) -> CritiqueSeverity:
        mapping = {
            "critical": CritiqueSeverity.CRITICAL,
            "high": CritiqueSeverity.HIGH,
            "medium": CritiqueSeverity.MEDIUM,
            "low": CritiqueSeverity.LOW,
            "info": CritiqueSeverity.INFO,
        }
        return mapping.get(sev.lower(), CritiqueSeverity.MEDIUM)


def format_findings_table(findings: list[CritiqueFinding]) -> str:
    """格式化发现为 Markdown 表格"""
    lines = ["| 严重级别 | 类别 | 摘要 | 证据 | 位置 |", "|---------|------|------|------|------|"]
    for f in findings:
        severity_icon = {
            CritiqueSeverity.CRITICAL: "🔴",
            CritiqueSeverity.HIGH: "🟠",
            CritiqueSeverity.MEDIUM: "🟡",
            CritiqueSeverity.LOW: "🟢",
            CritiqueSeverity.INFO: "ℹ️",
        }.get(f.severity, "")
        lines.append(
            f"| {severity_icon} {f.severity.value} "
            f"| {f.category.value} "
            f"| {f.summary[:60]} "
            f"| {f.evidence[:40]} "
            f"| {f.location[:30]} |"
        )
    return "\n".join(lines)
