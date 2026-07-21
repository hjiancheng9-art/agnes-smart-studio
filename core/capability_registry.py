"""Capability Registry — 玄武的骨架表。

所有能力用 Schema 声明，运行时动态注册和校验。
激活/停用/降级全自动，替代 tools.json 的硬编码。

Usage:
  from core.capability_registry import registry
  registry.register("generate_image", permissions=["gpu"], rate_limit=10)
  registry.check("generate_image")  # → (True, "") or (False, "rate_limited")
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CAPABILITY_FILE = ROOT / "output" / "capability_state.json"

SCHEMA_VERSION = "crux.capability.v1"


# ── Data ─────────────────────────────────────────────────────────


@dataclass
class Capability:
    """一个能力节点。玄武 Schema 声明。"""

    name: str
    permissions: list[str] = field(default_factory=list)
    rate_limit: int = 0  # 每分钟最大调用次数，0=不限
    fallback: str = ""  # 降级能力名
    provider: str = ""  # 实现提供者
    sandbox_mode: str = "workspace-write"
    enabled: bool = True

    # 运行时状态
    call_count: int = 0
    last_call: float = 0.0
    failure_count: int = 0
    max_failures: int = 3

    def can_call(self) -> tuple[bool, str]:
        """玄武守卫：调用前检查权限、频率、健康。"""
        if not self.enabled:
            return False, "disabled"

        if self.failure_count >= self.max_failures:
            return False, f"unhealthy: {self.failure_count}/{self.max_failures} failures"

        if self.rate_limit > 0:
            elapsed = time.time() - self.last_call
            if elapsed < 60.0:
                window_remaining = self.rate_limit - self.call_count
                if window_remaining <= 0:
                    return False, f"rate_limited: {self.rate_limit}/min"

        return True, "ok"

    def record_success(self) -> None:
        now = time.time()
        if now - self.last_call >= 60.0:
            self.call_count = 0
        self.call_count += 1
        self.last_call = now
        self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.max_failures:
            self.enabled = False
            logger.error("Capability auto-disabled: %s (%d failures)", self.name, self.failure_count)


# ── Registry ─────────────────────────────────────────────────────


class CapabilityRegistry:
    """能力注册表。每个能力都是可声明的、可校验的、可降级的。"""

    def __init__(self) -> None:
        self._caps: dict[str, Capability] = {}
        self._load_state()

    # ── register ──────────────────────────────────────────────

    def register(
        self,
        name: str,
        *,
        permissions: list[str] | None = None,
        rate_limit: int = 0,
        fallback: str = "",
        provider: str = "",
        sandbox_mode: str = "workspace-write",
    ) -> Capability:
        """注册一个能力。"""
        cap = Capability(
            name=name,
            permissions=permissions or [],
            rate_limit=rate_limit,
            fallback=fallback,
            provider=provider,
            sandbox_mode=sandbox_mode,
        )
        self._caps[name] = cap
        return cap

    def register_from_tools_json(self, tools_json_path: Path | None = None) -> int:
        """从 tools.json 批量注册能力（兼容现有硬编码）。"""
        path = tools_json_path or (ROOT / "tools.json")
        if not path.exists():
            return 0

        try:
            tools = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0

        count = 0
        for tool in tools if isinstance(tools, list) else tools.get("tools", []):
            name = tool.get("name", "")
            if not name or name in self._caps:
                continue
            self.register(
                name=name,
                permissions=self._infer_permissions(name),
                rate_limit=self._infer_rate_limit(name),
                provider="core",
            )
            count += 1

        logger.debug("Registered %d capabilities from tools.json", count)
        return count

    # ── check / record ────────────────────────────────────────

    def check(self, name: str) -> tuple[bool, str]:
        """检查能力是否可用。返回 (ok, reason)。"""
        cap = self._caps.get(name)
        if cap is None:
            return True, ""  # 未注册的能力默认放行（后向兼容）
        return cap.can_call()

    def record(self, name: str, success: bool) -> None:
        """记录调用结果。"""
        cap = self._caps.get(name)
        if cap is None:
            return
        if success:
            cap.record_success()
        else:
            cap.record_failure()
            if cap.fallback and cap.fallback in self._caps:
                logger.info("Capability %s degraded → %s", name, cap.fallback)

    def get_fallback(self, name: str) -> str:
        cap = self._caps.get(name)
        return cap.fallback if cap else ""

    def record_incident(self, tool_name: str, reason: str) -> None:
        """Record a tool incident for observability / recovery tracking."""
        logger.warning("[Capability] incident: %s — %s", tool_name, reason)

    # ── query ─────────────────────────────────────────────────

    def list_all(self) -> list[Capability]:
        return list(self._caps.values())

    def list_enabled(self) -> list[Capability]:
        return [c for c in self._caps.values() if c.enabled]

    def list_disabled(self) -> list[Capability]:
        return [c for c in self._caps.values() if not c.enabled]

    # ── persist ───────────────────────────────────────────────

    def _load_state(self) -> None:
        if not CAPABILITY_FILE.exists():
            return
        try:
            state = json.loads(CAPABILITY_FILE.read_text(encoding="utf-8"))
            for name, s in state.get("caps", {}).items():
                if name in self._caps:
                    self._caps[name].failure_count = s.get("failure_count", 0)
                    self._caps[name].enabled = s.get("enabled", True)
        except (json.JSONDecodeError, OSError):
            pass

    def save_state(self) -> None:
        state = {
            "schema_version": SCHEMA_VERSION,
            "caps": {name: {"failure_count": c.failure_count, "enabled": c.enabled} for name, c in self._caps.items()},
        }
        CAPABILITY_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _infer_permissions(name: str) -> list[str]:
        mapping = {
            "read_file": ["fs"],
            "write_file": ["fs"],
            "edit_file": ["fs"],
            "run_bash": ["process"],
            "run_python": ["process"],
            "run_test": ["process"],
            "web_fetch": ["network"],
            "web_search": ["network"],
            "generate_image": ["gpu"],
            "generate_video": ["gpu"],
            "browser_screenshot": ["browser"],
            "pw_navigate": ["browser"],
            "cdp_ask_chatgpt": ["browser", "network"],
            "text_to_speech": ["audio"],
        }
        return mapping.get(name, [])

    @staticmethod
    def _infer_rate_limit(name: str) -> int:
        """昂贵操作有频率限制。"""
        limits = {"generate_video": 5, "generate_image": 20, "text_to_speech": 30}
        return limits.get(name, 0)

    def summary(self) -> str:
        total = len(self._caps)
        active = len(self.list_enabled())
        degraded = len(self.list_disabled())
        return f"\n## 能力注册表\n  共计 {total} 能力 · {active} 可用 · {degraded} 降级"

    def reset(self) -> None:
        """Drop all registered capabilities (test isolation / hot reload).

        Clears the in-memory registry. The on-disk state file is left intact
        (it only carries failure_count/enabled overrides, repopulated by the
        next register() + _load_state() cycle). Callers must re-register any
        default capabilities they rely on after reset.
        """
        self._caps.clear()


# ── global ────────────────────────────────────────────────────────

registry = CapabilityRegistry()


def reset_capability_registry() -> None:
    """Reset the global capability registry singleton in place.

    ``registry`` is a module-level singleton imported by name elsewhere, so we
    reset its internal state in place rather than rebinding the name.
    """
    registry.reset()
