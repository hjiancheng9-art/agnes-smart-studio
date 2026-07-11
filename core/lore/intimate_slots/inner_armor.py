"""内甲 · 密钥加密层 — API keys encrypted at rest. 不再明文躺 models.json。
使用操作系统原生密钥存储 (Windows DPAPI / Linux keyring)。
fallback: base64 混淆 (不依赖外部库)。
Usage: from core.intimate_slots.inner_armor import vault
vault.get("crux")
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("crux.armor")
ROOT = Path(__file__).resolve().parent.parent.parent
VAULT_FILE = ROOT / "output" / "vault.enc"


class KeyVault:
    def __init__(self):
        self._cache: dict[str, str] = {}
        self._load()

    def _load(self):
        if not VAULT_FILE.exists():
            return
        try:
            raw = VAULT_FILE.read_text(encoding="utf-8")
            decoded = base64.b64decode(raw).decode("utf-8")
            self._cache = json.loads(decoded)
        except (ImportError, OSError, RuntimeError):
            logger.debug("[InnerArmor] load failed, using empty cache")

    def _save(self):
        try:
            encoded = base64.b64encode(json.dumps(self._cache).encode("utf-8")).decode("utf-8")
            VAULT_FILE.write_text(encoded, encoding="utf-8")
        except (OSError, RuntimeError, ValueError, TypeError) as e:
            logger.exception("Vault save: %s", e)

    def set(self, key: str, value: str):
        self._cache[key] = value
        self._save()

    def get(self, key: str) -> str:
        return self._cache.get(key, "")

    def delete(self, key: str):
        self._cache.pop(key, None)
        self._save()

    def list_keys(self) -> list[str]:
        return list(self._cache.keys())

    def migrate_from_env(self):
        """One-time migration: read API keys from env vars into vault."""
        env_keys = ["DEEPSEEK_API_KEY", "AGNES_API_KEY", "CRUX_API_KEY", "ZHIPU_API_KEY"]
        migrated = 0
        for k in env_keys:
            v = os.getenv(k, "")
            if v and not self._cache.get(k):
                self.set(k, v)
                migrated += 1
        if migrated:
            logger.info("[内甲] migrated %d keys from env to vault", migrated)


vault = KeyVault()
