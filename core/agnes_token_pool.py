"""AgnesCode Token Pool — read JWTs from AgnesCode localStorage LevelDB.

Provides round-robin access to multiple free-tier accounts for budget pooling.
Each account gets ~1200 credits/day; with N accounts, total pool = N × 1200.

Usage:
    from core.agnes_token_pool import get_pool
    token = get_pool().next()
    # Use token as Bearer auth to api-agnes-code.agnes-ai.com/v1

If a token gets rate-limited or credit-exhausted (HTTP 429 / subscription_required),
call pool.mark_bad(token) and grab a fresh one.

Tokens are refreshed automatically by AgnesCode when the desktop app runs.
JWTs live ~27 days — no manual refresh needed as long as AgnesCode is opened occasionally.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
from pathlib import Path

logger = logging.getLogger("crux.agnes_pool")

# LevelDB path relative to AgnesCode app data
_AGNES_DB_DIR = os.path.expandvars(r"%APPDATA%\AgnesCode\Partitions\agnes\Local Storage\leveldb")


def _extract_tokens_from_leveldb(db_dir: str) -> list[dict]:
    """Parse LevelDB log files for JWT tokens and userinfo.

    Electron's localStorage is backed by LevelDB (snappy-compressed log files).
    We scrape the raw bytes for JWT patterns (eyJ...) and userinfo JSON blobs,
    then pair them by user ID (sub claim).
    """
    tokens: dict[str, tuple[str, int]] = {}  # user_id -> (token, iat)
    userinfos: dict[str, dict] = {}

    db_path = Path(db_dir)
    if not db_path.exists():
        logger.warning("AgnesCode LevelDB not found at %s", db_dir)
        return []

    for log_file in sorted(db_path.glob("*.log"), reverse=True):
        try:
            data = log_file.read_bytes()
        except OSError:
            continue

        # Extract JWTs (eyJ... pattern)
        for m in re.finditer(rb"eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+", data):
            token = m.group().decode("ascii", errors="ignore")
            if len(token) < 100:
                continue
            parts = token.split(".")
            if len(parts) != 3:
                continue
            try:
                payload = json.loads(base64.b64decode(parts[1] + "==").decode("utf-8", errors="ignore"))
            except Exception:
                continue
            sub = payload.get("sub", "")
            iat = payload.get("iat", 0)
            if sub and (sub not in tokens or iat > tokens[sub][1]):
                tokens[sub] = (token, iat)

        # Extract userinfo JSON blobs
        for m in re.finditer(rb'\{[^{}]*"id"\s*:\s*"[a-f0-9-]+"[^}]*\}', data):
            try:
                ui = json.loads(m.group())
                uid = ui.get("id", "")
                if uid and "email" in ui and uid not in userinfos:
                    userinfos[uid] = ui
            except json.JSONDecodeError:
                continue

    # Pair tokens with userinfo
    result = []
    for sub, (token, iat) in sorted(tokens.items(), key=lambda x: x[1][1], reverse=True):
        ui = userinfos.get(sub, {})
        result.append(
            {
                "user_id": sub,
                "token": token,
                "email": ui.get("email", "?"),
                "username": ui.get("username", "?"),
                "iat": iat,
            }
        )
    return result


class AgnesTokenPool:
    """Thread-safe round-robin token pool backed by AgnesCode localStorage."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._accounts: list[dict] = []
        self._index: int = 0
        self._bad_tokens: set[str] = set()
        self._reload()

    def _reload(self) -> None:
        """Rescan LevelDB for fresh tokens."""
        accounts = _extract_tokens_from_leveldb(_AGNES_DB_DIR)
        with self._lock:
            # Preserve bad-token list across reloads
            self._accounts = accounts
            if self._index >= len(accounts):
                self._index = 0
        if accounts:
            logger.info("Token pool: %d accounts loaded", len(accounts))
        else:
            logger.warning("Token pool: no accounts found")

    @property
    def count(self) -> int:
        return len(self._accounts)

    @property
    def total_daily_credits(self) -> int:
        """Estimated total daily credits (1200 per account)."""
        return len(self._accounts) * 1200

    def next(self) -> str | None:
        """Return the next usable token, rotating past known-bad ones."""
        if not self._accounts:
            self._reload()
        if not self._accounts:
            return None
        with self._lock:
            for _ in range(len(self._accounts)):
                acct = self._accounts[self._index]
                self._index = (self._index + 1) % len(self._accounts)
                if acct["token"] not in self._bad_tokens:
                    return acct["token"]
        # All marked bad — reset and retry
        self._bad_tokens.clear()
        if self._accounts:
            return self._accounts[0]["token"]
        return None

    def mark_bad(self, token: str) -> None:
        """Mark a token as bad (rate-limited / credit exhausted / expired)."""
        with self._lock:
            self._bad_tokens.add(token)
        logger.info(
            "Token marked bad: %s... (pool: %d/%d healthy)", token[:16], self.healthy_count, len(self._accounts)
        )

    def clear_bad(self) -> None:
        """Reset bad-token list (e.g. after midnight credit reset)."""
        with self._lock:
            self._bad_tokens.clear()

    @property
    def healthy_count(self) -> int:
        return len(self._accounts) - len(self._bad_tokens)

    def list_accounts(self) -> list[dict]:
        """Return all accounts with status."""
        result = []
        with self._lock:
            for a in self._accounts:
                result.append(
                    {
                        **a,
                        "bad": a["token"] in self._bad_tokens,
                    }
                )
        return result


# Singleton
_pool: AgnesTokenPool | None = None


def get_pool() -> AgnesTokenPool:
    global _pool
    if _pool is None:
        _pool = AgnesTokenPool()
    return _pool
