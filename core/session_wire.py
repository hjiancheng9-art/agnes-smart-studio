"""Kimi-style session persistence with wire.jsonl protocol.

Directory structure (mirrors Kimi Code CLI):
    output/sessions/wd_{hash}/
      index.jsonl                     # sessionId → sessionDir → workDir
      session_{uuid}/
        state.json                    # title, createdAt, updatedAt, agents
        agents/
          main/
            wire.jsonl                # protocol wire log

wire.jsonl record types:
    1. metadata       — protocol_version, created_at
    2. config.update  — systemPrompt / thinkingLevel
    3. tools.set_active_tools — tool name list
    4. user / assistant / tool_result — conversation turns

Coexists with core.session_mgr.SessionManager (full .json snapshots).
This module provides Kimi-protocol wire.jsonl incremental logging.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.config import OUTPUT_DIR

__all__ = [
    "SESSIONS_ROOT",
    "SessionWire",
    "compute_wd_hash",
    "load_index",
]

SESSIONS_ROOT = OUTPUT_DIR / "sessions"

# Protocol version for wire.jsonl
PROTOCOL_VERSION = "1.0.0"


def compute_wd_hash(work_dir: Path | str) -> str:
    """Compute the work-dir hash used as the bucket directory name."""
    wd = str(Path(work_dir).resolve())
    return hashlib.sha256(wd.encode()).hexdigest()[:16]


# ── Index management ────────────────────────────────────────


def _index_path() -> Path:
    return SESSIONS_ROOT / "index.jsonl"


def load_index() -> list[dict]:
    """Load the session index (sessionId → sessionDir → workDir)."""
    ipath = _index_path()
    if not ipath.exists():
        return []
    entries: list[dict] = []
    try:
        for line in ipath.read_text(encoding="utf-8").strip().split("\n"):
            line = line.strip()
            if line:
                with contextlib.suppress(json.JSONDecodeError):
                    entries.append(json.loads(line))
    except OSError:
        pass
    return entries


def save_index_entry(entry: dict) -> None:
    """Append an entry to the session index."""
    ipath = _index_path()
    ipath.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(ipath, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def update_index_entry(session_id: str, updates: dict) -> None:
    """Update an existing entry in-place (by rewriting the index)."""
    entries = load_index()
    found = False
    for e in entries:
        if e.get("sessionId") == session_id:
            e.update(updates)
            found = True
            break
    if found:
        ipath = _index_path()
        try:
            with open(ipath, "w", encoding="utf-8") as fh:
                for e in entries:
                    fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        except OSError:
            pass


# ── SessionWire ──────────────────────────────────────────────


class SessionWire:
    """Kimi-protocol session wire: manages wire.jsonl for a single session.

    Usage:
        wire = SessionWire(Path.cwd())
        wire.start_session()
        wire.record_turn("user", "hello")
        wire.record_turn("assistant", "hi there")
        wire.end_session()
    """

    def __init__(self, work_dir: Path | str) -> None:
        self.work_dir = Path(work_dir).resolve()
        self._wd_hash = compute_wd_hash(self.work_dir)
        self._session_id: str = ""
        self._session_dir: Path | None = None
        self._wire_path: Path | None = None
        self._started_at: str = ""

    # ── Properties ─────────────────────────────────────────

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    # ── Lifecycle ──────────────────────────────────────────

    def start_session(self, session_id: str = "", title: str = "") -> str:
        """Start a new session: create directory, write state.json + metadata.

        Returns the session_id.
        """
        self._session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"
        self._started_at = datetime.now(timezone.utc).isoformat()

        # Directory layout
        self._session_dir = SESSIONS_ROOT / f"wd_{self._wd_hash}" / self._session_id
        agents_dir = self._session_dir / "agents" / "main"
        agents_dir.mkdir(parents=True, exist_ok=True)

        # state.json
        state = {
            "createdAt": self._started_at,
            "updatedAt": self._started_at,
            "title": title or "New Session",
            "isCustomTitle": bool(title),
            "agents": {
                "main": {
                    "homedir": str(agents_dir),
                    "type": "main",
                    "parentAgentId": None,
                }
            },
        }
        (self._session_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        # wire.jsonl — metadata record
        self._wire_path = agents_dir / "wire.jsonl"
        self._write_wire_record(
            {
                "type": "metadata",
                "protocol_version": PROTOCOL_VERSION,
                "created_at": self._started_at,
            }
        )

        # Index entry
        save_index_entry(
            {
                "sessionId": self._session_id,
                "sessionDir": str(self._session_dir),
                "workDir": str(self.work_dir),
                "createdAt": self._started_at,
                "title": title or "New Session",
            }
        )

        return self._session_id

    def end_session(self) -> None:
        """Finalize session: update updatedAt in state.json."""
        if not self._session_dir or not self._session_dir.exists():
            return
        now = datetime.now(timezone.utc).isoformat()
        state_path = self._session_dir / "state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state["updatedAt"] = now
                state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            except (json.JSONDecodeError, OSError):
                pass
        update_index_entry(self._session_id, {"updatedAt": now})

    # ── Recording ──────────────────────────────────────────

    def record_config_update(self, key: str, value: object) -> None:
        """Record a config.update event (e.g., systemPrompt change)."""
        self._write_wire_record(
            {
                "type": "config.update",
                "key": key,
                "value": value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def record_tools_active(self, tool_names: list[str]) -> None:
        """Record the active tool set."""
        self._write_wire_record(
            {
                "type": "tools.set_active_tools",
                "tools": tool_names,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def record_turn(self, role: str, content: str) -> None:
        """Record a conversation turn (user / assistant / tool_result)."""
        if role not in ("user", "assistant", "tool_result"):
            return
        self._write_wire_record(
            {
                "type": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _write_wire_record(self, record: dict) -> None:
        """Append a JSON line to wire.jsonl."""
        if not self._wire_path:
            return
        try:
            with open(self._wire_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ── Query ──────────────────────────────────────────────

    @staticmethod
    def list_sessions(work_dir: Path | str | None = None) -> list[dict]:
        """List all sessions. If work_dir is given, filter by work dir hash."""
        entries = load_index()
        if work_dir:
            wd_hash = compute_wd_hash(work_dir)
            entries = [e for e in entries if wd_hash in e.get("sessionDir", "")]
        return sorted(entries, key=lambda e: e.get("createdAt", ""), reverse=True)

    @staticmethod
    def load_history(session_id: str) -> list[dict] | None:
        """Load wire.jsonl records for a given session."""
        entries = load_index()
        for e in entries:
            if e.get("sessionId") == session_id:
                sdir = Path(e["sessionDir"])
                wire_path = sdir / "agents" / "main" / "wire.jsonl"
                if wire_path.exists():
                    try:
                        records: list[dict] = []
                        for line in wire_path.read_text(encoding="utf-8").strip().split("\n"):
                            line = line.strip()
                            if line:
                                records.append(json.loads(line))
                        return records
                    except (json.JSONDecodeError, OSError):
                        pass
                return None
        return None
