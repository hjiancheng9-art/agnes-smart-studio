"""Session manager -- named, persistent sessions across Agnes restarts.

Saves full message history with metadata. Supports save, list, restore, delete.
"""

import json
import logging
import time
from pathlib import Path

__all__ = [
    'ROOT', 'SESSIONS_DIR', 'SessionManager', 'logger', 'session_delete', 'session_list', 'session_restore', 'session_save',
]

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = ROOT / "output" / "sessions_data"

logger = logging.getLogger("agnes.session_mgr")


class SessionManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.dir = self.root / "output" / "sessions_data"
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, messages: list[dict], meta: dict | None = None) -> str:
        safe_name = name.replace("/", "_").replace("\\", "_")[:80]
        data = {
            "name": safe_name,
            "saved_at": time.time(),
            "message_count": len(messages),
            "meta": meta or {},
            "messages": messages,
        }
        path = self.dir / f"{safe_name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return safe_name

    def restore(self, name: str) -> dict | None:
        path = self.dir / f"{name}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[dict]:
        sessions = []
        for f in sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append({
                    "name": data["name"],
                    "saved_at": data["saved_at"],
                    "message_count": data["message_count"],
                    "meta": data.get("meta", {}),
                    "size": f.stat().st_size,
                })
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.debug("Skipping corrupted session file %s: %s", f.name, e)
        return sessions

    def delete(self, name: str) -> bool:
        path = self.dir / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False


# Global
_session_mgr = SessionManager()


def session_save(name: str, messages: list[dict], meta: dict | None = None) -> str:
    return _session_mgr.save(name, messages, meta)

def session_restore(name: str) -> dict | None:
    return _session_mgr.restore(name)

def session_list() -> list[dict]:
    return _session_mgr.list_sessions()

def session_delete(name: str) -> bool:
    return _session_mgr.delete(name)
