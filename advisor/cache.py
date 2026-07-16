"""
Advisor 查询缓存
================
基于 query + context 的 SHA256 哈希去重。
只缓存成功结果，TTL 默认 10 分钟。
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from advisor.base import AdvisorResult


@dataclass
class _CacheItem:
    result: AdvisorResult
    expires_at: float


class AdvisorCache:
    """简单的 TTL 缓存，线程不安全（调用方负责加锁）。"""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, _CacheItem] = {}

    def get(self, query: str, context: str = "") -> AdvisorResult | None:
        """查询缓存，过期返回 None。"""
        key = self._make_key(query, context)
        item = self._items.get(key)
        if item is None:
            return None
        if time.time() > item.expires_at:
            self._items.pop(key, None)
            return None
        return item.result

    def set(self, query: str, context: str, result: AdvisorResult) -> None:
        """存入缓存。只缓存成功结果。"""
        if not result.ok:
            return
        key = self._make_key(query, context)
        self._items[key] = _CacheItem(
            result=result,
            expires_at=time.time() + self.ttl_seconds,
        )

    def clear(self) -> None:
        """清空缓存。"""
        self._items.clear()

    @property
    def size(self) -> int:
        return len(self._items)

    # ── 内部 ──────────────────────────────────────

    @staticmethod
    def _make_key(query: str, context: str) -> str:
        raw = f"{query}\n{context}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
