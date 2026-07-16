"""Unified error types — single Failure protocol consumed by all subsystems."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class FailureKind(StrEnum):
    VALIDATION = "validation"
    POLICY = "policy"
    AUTH = "auth"
    NOT_FOUND = "not_found"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"
    PROTOCOL = "protocol"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class Failure:
    code: str
    kind: FailureKind
    message: str
    retryable: bool = False
    source: str = ""
    stage: str = ""
    user_message: str | None = None
    details: Mapping[str, object] = field(default_factory=dict)
