"""
Human-in-the-Loop 确认节点（v5.0→v6.0 升级）
==============================================
Gemini 评审核心建议：在复杂工作流关键分叉口，弹出确认卡片让用户"一键确认/重定向"。

用途：
  1. 高风险操作确认（删除/部署/批量修改）
  2. 复杂任务的路由方向确认（"你是指A还是B？"）
  3. 多步骤操作中的中间结果确认
  4. 收集用户偏好反馈用于 TRM 优化

设计：
  无需 UI 弹窗，通过 CRUX 消息系统与用户交互。
  返回 (approved: bool, user_feedback: str | None)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
import time


class ConfirmLevel(Enum):
    LOW = "low"               # 信息确认，跳过不影响
    MEDIUM = "medium"         # 建议确认，可自动通过
    HIGH = "high"             # 必须确认
    CRITICAL = "critical"     # 必须确认 + 需人工解释原因


@dataclass
class ConfirmCheckpoint:
    """确认检查点"""
    id: str
    title: str
    description: str
    level: ConfirmLevel
    options: list[str] = field(default_factory=lambda: ["确认", "取消"])
    context: dict = field(default_factory=dict)
    timeout: int = 60                  # 超时秒数
    auto_approve: bool = False         # 超时是否自动通过
    created_at: float = 0.0
    resolved_at: Optional[float] = None
    approved: Optional[bool] = None
    user_feedback: Optional[str] = None

    def to_message(self) -> str:
        """生成发给用户的确认消息"""
        icon = {
            "low": "ℹ️", "medium": "⚠️",
            "high": "🔴", "critical": "🚨"
        }
        lines = [
            f"{icon[self.level.value]} 需要确认: {self.title}",
            f"  {self.description}",
        ]
        if self.options:
            lines.append(f"  选项: {' / '.join(self.options)}")
        if self.level == ConfirmLevel.CRITICAL:
            lines.append("  ⚠️ 此操作不可逆，请谨慎确认")
        return "\n".join(lines)


class ConfirmManager:
    """确认管理器 — 跟踪待确认节点、超时处理、历史记录"""

    def __init__(self):
        self._pending: dict[str, ConfirmCheckpoint] = {}
        self._history: list[ConfirmCheckpoint] = []

    def request(self, checkpoint: ConfirmCheckpoint) -> ConfirmCheckpoint:
        """发起确认请求"""
        checkpoint.created_at = time.time()
        self._pending[checkpoint.id] = checkpoint
        return checkpoint

    def resolve(self, checkpoint_id: str, approved: bool, feedback: str = "") -> Optional[ConfirmCheckpoint]:
        """处理确认结果"""
        cp = self._pending.pop(checkpoint_id, None)
        if not cp:
            return None
        cp.approved = approved
        cp.user_feedback = feedback
        cp.resolved_at = time.time()
        self._history.append(cp)
        return cp

    def auto_resolve_expired(self) -> list[ConfirmCheckpoint]:
        """自动处理超时确认"""
        resolved = []
        now = time.time()
        expired_ids = [
            cid for cid, cp in self._pending.items()
            if now - cp.created_at > cp.timeout
        ]
        for cid in expired_ids:
            cp = self._pending.pop(cid, None)
            if cp:
                cp.approved = cp.auto_approve
                cp.user_feedback = "timeout"
                cp.resolved_at = now
                self._history.append(cp)
                resolved.append(cp)
        return resolved

    def get_pending(self) -> list[ConfirmCheckpoint]:
        return list(self._pending.values())

    def get_history(self, limit: int = 20) -> list[ConfirmCheckpoint]:
        return self._history[-limit:]

    def stats(self) -> dict:
        return {
            "pending": len(self._pending),
            "total": len(self._history),
            "approved": sum(1 for c in self._history if c.approved),
            "rejected": sum(1 for c in self._history if c.approved is False),
            "timed_out": sum(1 for c in self._history if c.user_feedback == "timeout"),
        }


# ─── 预置检查点工厂 ──────────────────────────────────────

def destructive_action_checkpoint(action: str, target: str) -> ConfirmCheckpoint:
    """高风险操作确认（删除/清理/重置）"""
    return ConfirmCheckpoint(
        id=f"destructive_{int(time.time())}",
        title=f"即将执行高风险操作: {action}",
        description=f"操作目标: {target}\n此操作可能不可逆，请确认是否继续。",
        level=ConfirmLevel.HIGH,
        options=["确认执行", "取消"],
        timeout=30,
        context={"action": action, "target": target},
    )


def deploy_checkpoint(target_env: str, changes: list[str]) -> ConfirmCheckpoint:
    """部署确认"""
    return ConfirmCheckpoint(
        id=f"deploy_{int(time.time())}",
        title=f"部署到 {target_env}",
        description="变更内容:\n" + "\n".join(f"  • {c}" for c in changes),
        level=ConfirmLevel.CRITICAL,
        options=["确认部署", "取消"],
        timeout=120,
        context={"environment": target_env, "changes": changes},
    )


def ambiguous_intent_checkpoint(intent: str, options: list[str]) -> ConfirmCheckpoint:
    """模糊意图澄清确认"""
    return ConfirmCheckpoint(
        id=f"clarify_{int(time.time())}",
        title="任务意图不明确，请确认方向",
        description=f"你的请求: \"{intent[:80]}\"\n请选择最接近的意图:",
        level=ConfirmLevel.MEDIUM,
        options=options,
        timeout=30,
        auto_approve=True,
        context={"original_intent": intent},
    )


def multi_step_checkpoint(step_name: str, step_result: str, next_step: str) -> ConfirmCheckpoint:
    """多步骤中间结果确认"""
    return ConfirmCheckpoint(
        id=f"step_{int(time.time())}",
        title=f"步骤完成: {step_name}",
        description=f"结果:\n{step_result[:200]}\n\n下一步: {next_step}\n是否继续？",
        level=ConfirmLevel.LOW,
        options=["继续", "暂停并修改", "重新执行"],
        timeout=60,
        auto_approve=True,
        context={"step": step_name, "next": next_step},
    )
