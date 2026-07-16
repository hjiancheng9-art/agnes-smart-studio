"""
Security Runtime — 安全审查运行时
====================================
专门处理：安全审计、权限检查、敏感信息泄露、漏洞扫描。

特性:
- 输出: vulnerabilities / risk_level / remediation_steps
- 步骤: 识别暴露面 → 分析风险 → 生成修复建议
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .base_runtime import BaseRuntime, RuntimeContext, RuntimeStatus

logger = logging.getLogger(__name__)


class SecurityRuntime(BaseRuntime):
    """安全审查运行时"""

    SEC_KEYWORDS = [
        r"安全|漏洞|权限|密码|token|secret|密钥|凭证|加密",
        r"security|vulnerability|permission|auth|encrypt|decrypt",
        r"删除.*密码|重置.*token|泄露|注入|xss|csrf|sql注入",
    ]

    def __init__(self):
        super().__init__(name="security")

    def can_handle(self, request: str, mode: str) -> bool:
        text = request.lower()
        score = 0
        for pattern in self.SEC_KEYWORDS:
            if re.search(pattern, text):
                score += 1
        return score >= 2 or mode == "SAFE"

    async def execute(self, ctx: RuntimeContext) -> dict[str, Any]:
        self._status = RuntimeStatus.RUNNING
        logger.info(f"SecurityRuntime: 安全审查 '{ctx.request[:60]}...'")

        vulns = self._scan_vulnerabilities(ctx.request)
        risk_level = self._assess_risk(ctx.request)

        result = {
            "status": "success",
            "runtime": self.name,
            "risk_level": risk_level,
            "vulnerabilities": vulns,
            "remediation_steps": self._generate_remediation(vulns),
            "requires_approval": risk_level in ("high", "critical"),
        }

        self._status = RuntimeStatus.SUCCESS
        return result

    def _scan_vulnerabilities(self, request: str) -> list[dict[str, str]]:
        vulns = []
        text = request.lower()
        if "密码" in text or "password" in text:
            vulns.append({"type": "credential_exposure", "severity": "critical", "detail": "密码硬编码或明文传输风险"})
        if "token" in text or "secret" in text:
            vulns.append({"type": "secret_leakage", "severity": "high", "detail": "密钥/token 泄露风险"})
        if "注入" in text or "sql" in text:
            vulns.append({"type": "injection", "severity": "critical", "detail": "SQL 注入风险"})
        if "权限" in text or "permission" in text:
            vulns.append({"type": "auth_bypass", "severity": "high", "detail": "权限绕过风险"})
        if "删除" in text or "delete" in text or "drop" in text:
            vulns.append({"type": "data_loss", "severity": "critical", "detail": "数据删除/丢失风险"})
        if not vulns:
            vulns.append({"type": "general_review", "severity": "medium", "detail": "建议进行完整安全审查"})
        return vulns

    def _assess_risk(self, request: str) -> str:
        text = request.lower()
        critical_kw = ["删除.*所有", "drop.*database", "rm -rf", "重置.*所有", "清空.*数据库"]
        for kw in critical_kw:
            if re.search(kw, text):
                return "critical"
        if re.search(r"密码|secret|token|注入|漏洞", text):
            return "high"
        return "medium"

    def _generate_remediation(self, vulns: list[dict[str, str]]) -> list[str]:
        return [f"[{v['severity']}] {v['detail']}" for v in vulns]
