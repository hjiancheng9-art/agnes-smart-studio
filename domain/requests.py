"""User request and session snapshot types."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class UserRequest:
    request_id: str
    session_id: str
    text: str
    command: str = ""


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    session_id: str
    recent_messages: tuple[dict, ...] = ()
    mode: str = "chat"
    pinned_provider: str = ""
    pinned_model: str = ""
    turn_number: int = 0
