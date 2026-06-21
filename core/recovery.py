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

__all__ = ['ROOT', 'RecoveryEngine', 'recover']

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
        }
        handler = playbooks.get(scenario)
        if not handler:
            return {"success": False, "message": f"Unknown scenario: {scenario}"}
        result = handler(**ctx)
        self.log.append({"ts": time.time(), "scenario": scenario,
                         "success": result["success"], "message": result["message"]})
        return result

    def _provider_down(self, **ctx) -> dict:
        try:
            from core.provider import get_provider_manager
            mgr = get_provider_manager()
            mgr.load()
            current = mgr.state.active
            priority = mgr.fallback_priority if hasattr(mgr, 'fallback_priority') else ["deepseek", "siliconflow"]
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
        return {"success": True, "message": f"Cleaned {freed} items"}

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


def recover(scenario: str, **ctx) -> dict:
    return RecoveryEngine().run(scenario, **ctx)
