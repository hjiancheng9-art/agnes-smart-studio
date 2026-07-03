"""Recovery playbooks — automated responses to common failure scenarios.

Each playbook is a function that:
1. Detects a specific failure pattern
2. Attempts a predefined recovery action
3. Returns (success: bool, message: str)

Playbooks:
    provider_down      — switch to fallback provider
    config_corrupt     — restore from backup
    disk_low           — clean old output files
    model_error        — retry with degraded params
"""

import json
import shutil
import time
from pathlib import Path

__all__ = ["ROOT", "RecoveryEngine", "recover"]

ROOT = Path(__file__).resolve().parent.parent


class RecoveryEngine:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.log: list[dict] = []

    def run(self, scenario: str, **ctx) -> dict:
        playbooks = {
            "provider_down": self._provider_down,
            "config_corrupt": self._config_corrupt,
            "disk_low": self._disk_low,
            "model_error": self._model_error,
            "rate_limit": self._rate_limit,
            "history_corrupt": self._history_corrupt,
        }
        handler = playbooks.get(scenario)
        if not handler:
            return {"success": False, "message": f"Unknown scenario: {scenario}"}
        result = handler(**ctx)
        self.log.append(
            {"ts": time.time(), "scenario": scenario, "success": result["success"], "message": result["message"]}
        )
        return result

    def _provider_down(self, **ctx) -> dict:
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            mgr.load()
            current = mgr.state.active
            priority = mgr.fallback_priority if hasattr(mgr, "fallback_priority") else ["deepseek", "zhipu"]
            for alt in priority:
                if alt in mgr.providers and alt != current:
                    mgr.set_active(alt)
                    mgr.save_active()
                    return {"success": True, "message": f"Switched from {current} to {alt}"}
            return {"success": False, "message": f"No fallback available for {current}"}
        except (ImportError, AttributeError) as e:
            return {"success": False, "message": str(e)}

    def _config_corrupt(self, file: str = "models.json", **ctx) -> dict:
        target = self.root / file
        backup = self.root / f"{file}.bak"
        if not backup.exists():
            return {"success": False, "message": f"No backup found for {file}"}
        try:
            shutil.copy2(backup, target)
            json.loads(target.read_text(encoding="utf-8"))
            return {"success": True, "message": f"Restored {file} from backup"}
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            return {"success": False, "message": str(e)}

    def _disk_low(self, threshold_mb: int = 500, **ctx) -> dict:
        import shutil as _shutil

        # P3-fix: 先检查磁盘剩余空间，低于阈值才清理（而非无脑删文件）
        try:
            usage = _shutil.disk_usage(self.root)
            free_mb = usage.free / (1024 * 1024)
            if free_mb >= threshold_mb:
                return {"success": True, "message": f"Disk space OK ({free_mb:.0f} MB free > {threshold_mb} MB threshold)"}
        except OSError:
            # disk_usage 失败时保守清理（如网络文件系统不支持 statvfs）
            pass

        freed = 0
        # Clean old browser sessions
        bs = self.root / "output" / "browser_sessions"
        if bs.exists():
            try:
                _shutil.rmtree(bs)
                freed += 1
            except (OSError, PermissionError):
                pass
        # Clean old backups
        for bak in sorted(self.root.rglob("*.bak"), key=lambda p: p.stat().st_mtime):
            try:
                bak.unlink()
                freed += 1
                if freed >= 5:
                    break
            except (OSError, PermissionError):
                pass
        return {"success": True, "message": f"Disk space low (<{threshold_mb} MB) — cleaned {freed} items"}

    def _model_error(self, error_msg: str = "", **ctx) -> dict:
        hints = []
        el = error_msg.lower()
        if "503" in el:
            hints.append("Model may be unavailable — try switching provider")
        if "401" in el or "403" in el:
            hints.append("Authentication failed — check API key")
        if "timeout" in el:
            hints.append("Request timed out — reduce prompt size or increase timeout")
        if "rate" in el:
            hints.append("Rate limited — wait and retry")
        return {"success": len(hints) > 0, "message": "; ".join(hints) or "Unknown model error"}

    def _rate_limit(self, provider: str = "", retry_after: int = 5, **ctx) -> dict:
        """Handle rate limiting (429) — wait and try fallback provider."""
        hints = []
        if provider:
            from core.provider import get_provider_manager
            mgr = get_provider_manager()
            mgr.state.mark_down(provider)
            hints.append(f"Provider {provider} temporarily marked down (cooldown)")

            # Try switching to another available provider
            available = mgr.state.available(list(mgr.providers.keys()))
            alt = next((p for p in available if p != provider), None)
            if alt:
                mgr.state.active = alt
                hints.append(f"Switched to {alt}")

        hints.append(f"Rate limited — retry after {retry_after}s")
        return {"success": True, "message": "; ".join(hints)}

    def _history_corrupt(self, session_id: str = "", **ctx) -> dict:
        """Handle corrupted chat history — truncate and rebuild."""
        history_path = self.root / "output" / "history.json"
        backup_path = self.root / "output" / "history.json.bak"

        if history_path.exists():
            shutil.copy2(history_path, backup_path)

            # Attempt to load and sanitize
            try:
                import json as _json
                with open(history_path, encoding="utf-8") as f:
                    data = _json.load(f)
                # Trim to last valid session
                if isinstance(data, list) and len(data) > 0:
                    data = data[-1:]  # keep only most recent
                    with open(history_path, "w", encoding="utf-8") as f:
                        _json.dump(data, f, ensure_ascii=False)
                    return {"success": True, "message": "Chat history truncated to last session"}
            except (_json.JSONDecodeError, KeyError, TypeError):
                # Severely corrupted — wipe and restart
                with open(history_path, "w", encoding="utf-8") as f:
                    _json.dump([], f)
                return {"success": True, "message": "Corrupted history reset to empty"}

        return {"success": False, "message": "No history file to recover"}


def recover(scenario: str, **ctx) -> dict:
    return RecoveryEngine().run(scenario, **ctx)
