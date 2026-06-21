"""Capability registry — structured self-knowledge for Agnes.

Answers: what skills, tools, providers, engines do I have? What's their status?
Usable by both /self commands and agent-mode tool calls.
"""

import json
import logging
import sys
import time
from pathlib import Path

__all__ = ['CapabilityRegistry', 'ROOT', 'capability_snapshot', 'logger']

logger = logging.getLogger("agnes.capability")

ROOT = Path(__file__).resolve().parent.parent


class CapabilityRegistry:
    """Single source of truth for all Agnes capabilities."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self._cache: dict | None = None
        self._cache_time: float = 0
        self._cache_ttl: float = 30.0

    def snapshot(self) -> dict:
        """Return a complete capability snapshot (cached for 30s)."""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache
        snap = {
            "timestamp": now,
            "skills": self._list_skills(),
            "tools": self._list_tools(),
            "providers": self._list_providers(),
            "engines": self._list_engines(),
            "models": self._list_models(),
            "environment": self._check_env(),
            "health": self._quick_health(),
        }
        self._cache = snap
        self._cache_time = now
        return snap

    def _list_skills(self) -> dict:
        sd = self.root / "skills"
        if not sd.exists():
            return {"count": 0, "items": []}
        items = []
        for sf in sorted(sd.glob("*.skill.json")):
            try:
                data = json.loads(sf.read_text(encoding="utf-8"))
                items.append({
                    "name": data.get("name", sf.stem),
                    "description": data.get("description", "")[:80],
                    "version": data.get("version", "?"),
                    "file": sf.name,
                    "size": sf.stat().st_size,
                })
            except (json.JSONDecodeError, OSError, KeyError) as e:
                logger.debug("Invalid skill file %s: %s", sf.name, e)
                items.append({"name": sf.stem, "error": "invalid JSON", "file": sf.name})
        return {"count": len(items), "items": items}

    def _list_tools(self) -> dict:
        tp = self.root / "tools.json"
        if not tp.exists():
            return {"count": 0, "items": []}
        try:
            data = json.loads(tp.read_text(encoding="utf-8"))
            tools = data.get("tools", [])
            items = []
            for t in tools:
                items.append({
                    "name": t.get("name", "?"),
                    "type": t.get("type", "?"),
                    "description": t.get("description", "")[:80],
                })
            return {"count": len(items), "items": items}
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("tools.json read error: %s", e)
            return {"count": 0, "error": "tools.json invalid"}
    def _list_providers(self) -> dict:
        mp = self.root / "models.json"
        if not mp.exists():
            return {"active": "?", "count": 0, "items": []}
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
            active = data.get("active", "?")
            providers = data.get("providers", {})
            items = []
            for name, cfg in providers.items():
                items.append({
                    "name": name,
                    "display": cfg.get("name", name),
                    "base_url": cfg.get("base_url", "")[:60],
                    "is_active": name == active,
                })
            return {"active": active, "count": len(items), "items": items}
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("models.json read error: %s", e)
            return {"active": "?", "count": 0, "error": "models.json invalid"}

    def _list_engines(self) -> dict:
        engines = {}
        for name in ("text_to_image", "image_to_image", "video"):
            engines[name] = "available"
        # Check comfyui

        try:
            from core.config import SETTINGS

            if getattr(SETTINGS, "comfyui_enabled", False):
                engines["comfyui"] = "enabled"
        except (AttributeError, ImportError, NameError):
            pass
        if False:  # was comfyui check
            engines["comfyui"] = "enabled"
        return {"count": len(engines), "items": engines}

    def _list_models(self) -> dict:
        from core.config import MODELS
        items = {}
        for key, cfg in MODELS.items():
            items[key] = {"id": cfg.get("id", "?"), "type": cfg.get("type", "?")}
        return {"count": len(items), "items": items}

    def _check_env(self) -> dict:
        import sys
        from core.config import SETTINGS

        return {
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "encoding": sys.getdefaultencoding(),
            "api_key_set": bool(SETTINGS.api_key),
            "api_base": SETTINGS.base_url[:60] if SETTINGS.base_url else "not set",
        }

    def _quick_health(self) -> dict:
        results = {}
        # Provider reachability (quick check)
        try:
            from core.provider import get_provider_manager
            mgr = get_provider_manager()
            mgr.load()
            results["provider"] = f"active={mgr.state.active}, providers={len(mgr.providers)}"
        except (ImportError, AttributeError, OSError) as e:
            results["provider"] = f"error: {e}"
        # Test suite status (核心契约快检，非全量)
        # 旧实现跑全量 tests/ + timeout=15 → 必超时 → parse 返回 (0,0)
        # → 显示 "0 passed, 0 failed" 被误读成"没问题"，是假自检。
        # 现改为只跑渲染契约 + chat 核心（<2s），且 parse 有点号 fallback。
        try:
            from core.pytest_runner import run_pytest_safe, parse_test_summary
            r = run_pytest_safe(
                test_target="tests/test_render.py tests/test_chat.py",
                timeout=15, cwd=self.root,
            )
            out = (r.stdout or "") + (r.stderr or "")
            passed, failed = parse_test_summary(out)
            results["tests"] = f"{passed} passed, {failed} failed (render+chat 快检)"
        except (OSError, ValueError) as e:
            results["tests"] = f"error: {e}"
        # Rendering invariants (显示层"输出不重复"DNA 自检)
        # 真反射检测：实际 import + 构造 renderer 取样 Live 验证 transient=True，
        # 而非写死 True（否则 renderer 被删/被改时自检仍撒谎）。
        try:
            from rich.console import Console as _C
            from ui.render import StreamingRenderer as _SR
            _probe = _SR(_C())  # 真构造，触发真实配置路径
            live = _probe._new_live("")
            transient_ok = getattr(live, "transient", False) is True
            # single_commit：commit 方法存在 + 实例确有 _flushed_len 字段（实例属性，非类属性）
            results["rendering.invariants"] = {
                "renderer_present": True,
                "transient_preview": transient_ok,
                "single_commit": callable(getattr(_probe, "commit", None))
                                  and hasattr(_probe, "_flushed_len"),
                "renderer": "ui/render.py:StreamingRenderer",
            }
        except ImportError as e:
            results["rendering.invariants"] = {"renderer_present": False, "error": f"import: {e}"}
        except Exception as e:
            results["rendering.invariants"] = {"renderer_present": False, "error": f"{type(e).__name__}: {e}"}
        return results


def capability_snapshot() -> dict:
    return CapabilityRegistry().snapshot()