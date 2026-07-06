"""Seed Policy for Self-Heal Cold Start — 防止低价值自愈消耗资源

基于 GPT 架构审计建议：
- Seed policy 拦截已知不可自愈的错误（CUDA OOM、ModuleNotFound 等）
- 不做一刀切封死，而是降级和限流
- 与 fake_fix_detector.py 的 quarantine 双轨运行

策略层级（从严到宽）：
  quarantine            — 完全禁止重试，需用户手动解除
  downgrade_to_diagnosis — 不自愈，降级为诊断模式
  requires_user_action   — 需用户确认后才重试
  requires_new_evidence  — 需要新的上下文证据才允许重试
  limited_retry          — 允许有限次重试（比默认少）
  allow_retry            — 完全允许，不做限制
"""

import re
from dataclasses import dataclass, field
from typing import Any, Literal

PolicyAction = Literal[
    "allow_retry",
    "limited_retry",
    "requires_new_evidence",
    "requires_user_action",
    "downgrade_to_diagnosis",
    "quarantine",
]


@dataclass
class PolicyDecision:
    """Seed policy 对自愈重试的裁决。"""
    action: PolicyAction
    max_retries: int = 0
    requires_new_evidence: bool = False
    reason: str = ""
    cooldown_seconds: int = 0  # 冷却时间（秒），0 表示沿用全局默认

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "max_retries": self.max_retries,
            "requires_new_evidence": self.requires_new_evidence,
            "reason": self.reason,
            "cooldown_seconds": self.cooldown_seconds,
        }


# ── Seed Rules ─────────────────────────────────────────────
#
# 每条规则: (pattern, tool_filter, policy, max_retries, reason)
# pattern 匹配 error_type（支持 regex）
# tool_filter: "*" = 所有工具，或工具名集合

SEED_RULES: list[tuple[str, str | set, PolicyAction, int, str]] = [
    # ── 资源不足：不可自愈 ──
    (
        r"CUDA out of memory|OutOfMemoryError|OOM|memory.*exceeded",
        "*",
        "downgrade_to_diagnosis",
        0,
        "资源不足通常不能通过代码补丁修复，需人工扩容或减负",
    ),
    (
        r"DiskFull|no space left|ENOSPC|disk.*full",
        "*",
        "requires_user_action",
        0,
        "磁盘空间不足需人工清理",
    ),

    # ── 环境缺失：需人工操作 ──
    (
        r"ModuleNotFoundError|ImportError|No module named",
        "*",
        "requires_user_action",
        1,
        "可能需要安装依赖或修正 Python 环境",
    ),
    (
        r"pip install.*permission|Permission denied.*pip|EACCES.*install",
        "*",
        "requires_user_action",
        0,
        "pip 权限不足需人工处理（sudo/venv）",
    ),
    (
        r"command not found|not recognized as.*command|No such file or directory.*executable",
        "*",
        "requires_user_action",
        1,
        "可执行文件缺失，可能需要安装或配置 PATH",
    ),

    # ── 模型/文件缺失：环境问题 ──
    (
        r"model.*(not found|missing|doesn.t exist)|checkpoint.*not found|safetensors.*not found",
        "*",
        "requires_user_action",
        0,
        "模型文件缺失，需手动下载或配置路径",
    ),
    (
        r"ComfyUI.*node.*(missing|not found|custom node.*not installed)",
        "*",
        "requires_user_action",
        0,
        "ComfyUI 自定义节点缺失，需通过 ComfyUI Manager 安装",
    ),
    (
        r"LoRA.*(not found|missing)|lora.*weight.*missing",
        "*",
        "requires_user_action",
        0,
        "LoRA 权重文件缺失，需手动下载",
    ),

    # ── 网络/超时：重试有限 ──
    (
        r"timeout|timed out|ETIMEDOUT|Connection timed out|TimeoutError",
        "*",
        "limited_retry",
        2,
        "网络超时可有限重试，但不宜反复",
    ),
    (
        r"404.*Not Found|HTTP 404|status.*404",
        "*",
        "limited_retry",
        1,
        "HTTP 404 通常不是临时错误，最多重试 1 次",
    ),
    (
        r"Connection refused|ECONNREFUSED|connect.*refused",
        "*",
        "limited_retry",
        3,
        "连接被拒可能服务未启动，有限重试",
    ),
    (
        r"DNS|Name or service not known|getaddrinfo|ENOTFOUND",
        "*",
        "limited_retry",
        1,
        "DNS 解析失败多为配置问题",
    ),

    # ── 文件锁（Windows 特有） ──
    (
        r"WinError 32|being used by another process|file.*locked|PermissionError.*WinError",
        "*",
        "limited_retry",
        3,
        "Windows 文件锁可能为瞬态，有限重试",
    ),

    # ── 语法/格式错误：可有限尝试修复 ──
    (
        r"SyntaxError|IndentationError|TabError",
        {"patch_file", "execute_plan", "self_heal"},
        "limited_retry",
        2,
        "语法错误可能通过补丁修复，但有限次",
    ),
    (
        r"JSONDecodeError|json.*decode|Invalid JSON|YAML.*error|TOML.*error",
        {"patch_file", "execute_plan"},
        "limited_retry",
        2,
        "格式错误可尝试修复",
    ),

    # ── 权限/沙箱：不可自愈 ──
    (
        r"Sandbox rejected|sandbox.*deny|permission.*denied.*sandbox",
        "*",
        "quarantine",
        0,
        "沙箱拒绝不可通过代码修复绕过",
    ),
    (
        r"Operation not permitted|EPERM|not allowed",
        "*",
        "requires_user_action",
        0,
        "操作被系统拒绝，需检查权限配置",
    ),

    # ── 自愈工具自身错误 ──
    (
        r"self_heal.*(failed|recursion|loop)|infinite.*loop|recursion.*detected",
        {"self_heal"},
        "quarantine",
        0,
        "自愈递归/循环 — 可能 self_heal 在修复自己",
    ),
    (
        r"fake_fix.*detected|spurious.*fix|fix-spurious",
        {"self_heal"},
        "quarantine",
        0,
        "已检测到假修复，停止该方向的自愈",
    ),

    # ── API 限流/认证 ──
    (
        r"rate.?limit|429|Too Many Requests|quota.*exceeded",
        "*",
        "downgrade_to_diagnosis",
        0,
        "API 限流，应等待而非重试（cooldown 由规则控制）",
    ),
    (
        r"401|Unauthorized|403|Forbidden|auth.*(failed|invalid|expired)",
        "*",
        "requires_user_action",
        0,
        "认证失败需用户更新凭据",
    ),
]


class FakeFixSeedPolicy:
    """冷启动种子策略 — 在 quarantine 之前先过 seeds。

    用法：
        policy = FakeFixSeedPolicy()
        decision = policy.classify("self_heal", "CUDA out of memory", {})
        if decision.action == "downgrade_to_diagnosis":
            return  # 不重试，降级为诊断
    """

    def __init__(self, custom_rules: list | None = None):
        self._rules = list(SEED_RULES)
        if custom_rules:
            self._rules.extend(custom_rules)

        # 用户白名单：允许用户手动解除对特定签名的限制
        self._whitelist: set[str] = set()
        # 项目级 override：{signature_pattern_hash: PolicyDecision}
        self._overrides: dict[str, PolicyDecision] = {}

    # ── 公共 API ───────────────────────────────────────

    def classify(
        self,
        tool: str,
        error_type: str,
        context: dict | None = None,
    ) -> PolicyDecision:
        """对给定的错误进行分类，返回策略裁决。

        Args:
            tool: 工具名（如 "self_heal", "patch_file"）
            error_type: 错误类型字符串
            context: 额外上下文（可选）

        Returns:
            PolicyDecision: 默认为 allow_retry（不放行任何限制）
        """
        ctx = context or {}
        signature_key = self._make_key(tool, error_type)

        # 1. 用户白名单
        if signature_key in self._whitelist:
            return PolicyDecision(
                action="allow_retry",
                max_retries=999,
                reason="用户已加入白名单",
            )

        # 2. 项目级 override
        if signature_key in self._overrides:
            return self._overrides[signature_key]

        # 3. 匹配种子规则（按规则顺序，首个匹配即返回）
        for pattern, tool_filter, action, max_retries, reason in self._rules:
            if not self._match_tool(tool, tool_filter):
                continue
            if not re.search(pattern, error_type, re.IGNORECASE):
                continue

            requires_new_evidence = action in (
                "requires_new_evidence",
                "downgrade_to_diagnosis",
                "quarantine",
            )

            # 对 limited_retry: 取种子规则和全局 MAX_RETRIES_24H 的最小值
            return PolicyDecision(
                action=action,
                max_retries=max_retries,
                requires_new_evidence=requires_new_evidence,
                reason=reason,
                cooldown_seconds=self._cooldown_for_action(action),
            )

        # 4. 无匹配 → 默认放行（交给 quarantine 在线学习）
        return PolicyDecision(
            action="allow_retry",
            max_retries=999,
            reason="无种子规则匹配，交由在线 quarantine 学习",
        )

    def whitelist(self, tool: str, error_type: str) -> None:
        """将某个错误签名加入白名单（用户手动解除）。"""
        key = self._make_key(tool, error_type)
        self._whitelist.add(key)

    def remove_whitelist(self, tool: str, error_type: str) -> None:
        """从白名单中移除。"""
        key = self._make_key(tool, error_type)
        self._whitelist.discard(key)

    def set_override(
        self, tool: str, error_type: str, decision: PolicyDecision
    ) -> None:
        """设置项目级策略覆盖。"""
        key = self._make_key(tool, error_type)
        self._overrides[key] = decision

    def remove_override(self, tool: str, error_type: str) -> None:
        """移除项目级覆盖。"""
        key = self._make_key(tool, error_type)
        self._overrides.pop(key, None)

    def list_rules(self) -> list[dict]:
        """列出所有种子规则（供诊断/驾驶舱展示）。"""
        return [
            {
                "pattern": pat,
                "tool_filter": tf if isinstance(tf, str) else list(tf),
                "action": action,
                "max_retries": max_r,
                "reason": reason,
            }
            for pat, tf, action, max_r, reason in self._rules
        ]

    # ── 内部 ───────────────────────────────────────────

    @staticmethod
    def _make_key(tool: str, error_type: str) -> str:
        return f"{tool}::{error_type[:120]}"

    @staticmethod
    def _match_tool(tool: str, tool_filter: str | set) -> bool:
        if tool_filter == "*":
            return True
        if isinstance(tool_filter, set):
            return tool in tool_filter
        return tool == tool_filter

    @staticmethod
    def _cooldown_for_action(action: PolicyAction) -> int:
        """根据策略等级返回建议冷却时间（秒）。"""
        cooldowns = {
            "allow_retry": 0,
            "limited_retry": 5,
            "requires_new_evidence": 30,
            "requires_user_action": 60,
            "downgrade_to_diagnosis": 120,
            "quarantine": 3600,
        }
        return cooldowns.get(action, 0)


# ── 全局单例 ─────────────────────────────────────────────────
_seed_policy: FakeFixSeedPolicy | None = None


def get_seed_policy() -> FakeFixSeedPolicy:
    """获取全局种子策略实例。"""
    global _seed_policy
    if _seed_policy is None:
        _seed_policy = FakeFixSeedPolicy()
    return _seed_policy


def reset_seed_policy() -> None:
    """重置全局种子策略（测试用）。"""
    global _seed_policy
    _seed_policy = None
