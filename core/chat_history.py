"""Session history I/O for ChatSession — snapshot save/restore + message sanitization.

Extracted from core/chat.py (refactor P3). This module is intentionally free of
ChatSession internals: functions take explicit inputs (messages, snapshot dir,
interval) so they are pure/testable and the snapshot directory can be overridden
at runtime (e.g. in tests). ChatSession keeps thin delegating methods for
backward compatibility.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Default snapshot location: <repo>/output/sessions
DEFAULT_SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "output" / "sessions"
DEFAULT_SNAPSHOT_INTERVAL = 5  # snapshot every N turns


def sanitize_messages(messages: list[dict]) -> list[dict]:
    """Strip trailing incomplete tool-call sequences from restored messages.

    API requirement: every assistant message with ``tool_calls`` must be
    immediately followed by one tool-role message per call.  If a session
    crashes mid-call the restored snapshot may contain:
    - An assistant with tool_calls but no following tool results
    - Consecutive assistant messages both carrying tool_calls
    - Assistant with N tool_calls but < N tool results

    This function replays the sequence from the start and truncates at the
    first invalid message, guaranteeing a clean API boundary.
    """
    if not messages:
        return messages

    sanitized: list[dict] = []
    pending_tool_ids: set[str] = set()

    for msg in messages:
        role = msg.get("role", "")

        if role == "system":
            sanitized.append(msg)
            continue

        if role == "user":
            # User message while tool calls are pending → invalid,
            # truncate here (the incomplete sequence ends before this user msg)
            if pending_tool_ids:
                break
            sanitized.append(msg)
            continue

        if role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                # Assistant with tool_calls while previous tool_calls still
                # pending → consecutive assistant tool_calls → invalid
                if pending_tool_ids:
                    break
                sanitized.append(msg)
                pending_tool_ids = {tc["id"] for tc in tool_calls if tc.get("id")}
            else:
                # Regular assistant message (text response) → always valid
                sanitized.append(msg)
            continue

        if role == "tool":
            tc_id = msg.get("tool_call_id", "")
            if tc_id and tc_id in pending_tool_ids:
                sanitized.append(msg)
                pending_tool_ids.discard(tc_id)
            else:
                # Tool result for unknown / already-consumed call id → invalid
                break
            continue

        # Unknown role → keep conservatively
        sanitized.append(msg)

    # If we ended with pending tool calls, strip back to before the
    # incomplete assistant message
    if pending_tool_ids:
        # Find the last assistant with tool_calls and strip everything from
        # the user message that triggered it
        while sanitized:
            last = sanitized[-1]
            if last.get("role") == "assistant" and last.get("tool_calls"):
                sanitized.pop()
                # Remove the triggering user message too
                if sanitized and sanitized[-1].get("role") == "user":
                    sanitized.pop()
                break
            sanitized.pop()

    return sanitized


def save_snapshot(
    snapshot_dir: Path,
    model: str,
    turn: int,
    messages: list[dict],
) -> None:
    """Write a best-effort session snapshot to ``snapshot_dir/latest.json``.

    Failures are swallowed — snapshotting must never break the main flow.
    """
    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "model": model,
            "turn": turn,
            "messages": messages[-50:],  # last 50
            "saved_at": datetime.now().isoformat(),
        }
        path = snapshot_dir / "latest.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError, TypeError):
        logger.debug("snapshot save failed", exc_info=True)


def restore_latest_snapshot(snapshot_dir: Path) -> dict | None:
    """Load an unrestored session snapshot, if any. Returns dict with ``messages`` or None."""
    try:
        path = snapshot_dir / "latest.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text("utf-8"))
        if data.get("messages"):
            data["messages"] = sanitize_messages(data["messages"])
            if not data["messages"]:
                os.remove(path)
                return None
            # Discard snapshots with no assistant messages — user-only content
            # (e.g. pasted crash logs) is not a real session.
            has_assistant = any(m.get("role") == "assistant" for m in data["messages"])
            if not has_assistant:
                os.remove(path)
                return None
        return data if data.get("messages") else None
    except (OSError, json.JSONDecodeError, KeyError):
        return None
