"""Session manager -- named, persistent sessions across CRUX restarts.

ZCode EventBridge: save/restore/delete 自动触发 EventBus 事件，
使 Session 生命周期可追踪 (session:created / resumed / closed)。

Saves full message history with metadata. Supports save, list, restore, delete.
"""

import json
import logging
import os
import time
from pathlib import Path

from core.event_bus import SESSION_CLOSED, SESSION_CREATED, SESSION_RESUMED, bus

__all__ = [
    "ROOT",
    "SESSIONS_DIR",
    "SessionManager",
    "logger",
    "session_delete",
    "session_list",
    "session_restore",
    "session_save",
]

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = ROOT / "output" / "sessions_data"

logger = logging.getLogger("crux.session_mgr")


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
        # 原子写: tmp -> replace。防止写盘中途崩溃导致既有会话文件被截断丢失。
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            # tmp 残留不影响正式文件;清理后再向上抛,让调用方知道保存失败。
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise
        # ZCode EventBridge: 会话创建事件
        bus.emit(SESSION_CREATED, name=safe_name, message_count=len(messages), meta=meta or {})
        return safe_name

    def restore(self, name: str) -> dict | None:
        path = self.dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # ZCode EventBridge: 会话恢复事件
            bus.emit(SESSION_RESUMED, name=name, message_count=data.get("message_count", 0))
            return data
        except (json.JSONDecodeError, OSError) as e:
            # 容错:损坏/半写文件不应让 restore 崩溃调用方。
            # 与 list_sessions 行为一致(后者早有同类容错)。
            logger.debug("Skipping corrupted session file %s: %s", path.name, e)
            return None

    def list_sessions(self) -> list[dict]:
        sessions = []
        for f in sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append(
                    {
                        "name": data["name"],
                        "saved_at": data["saved_at"],
                        "message_count": data["message_count"],
                        "meta": data.get("meta", {}),
                        "size": f.stat().st_size,
                    }
                )
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.debug("Skipping corrupted session file %s: %s", f.name, e)
        return sessions

    def delete(self, name: str) -> bool:
        path = self.dir / f"{name}.json"
        if path.exists():
            # ZCode EventBridge: 会话关闭事件
            bus.emit(SESSION_CLOSED, name=name, reason="deleted")
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
