"""Model alias resolution helpers — extracted from chat.py.

Pure functions for building model aliases and info maps from the provider registry.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_model_aliases() -> dict[str, str]:
    """从 models.json active provider 的 models 字段动态构建别名映射。
    "light" → active 供应商的 light 模型, "pro" → pro 模型。
    """
    try:
        from core.provider import get_provider_manager

        mgr = get_provider_manager()
        mgr.load()
        pmap = mgr.get_active_models()
        return {k: v for k, v in pmap.items() if k in ("light", "pro")}
    except Exception as e:
        logger.debug("model lookup failed: %s", e)
        return {}


def build_model_info() -> dict[str, str]:
    """从 MODEL_REGISTRY 构建模型 ID → 描述 映射。"""
    try:
        from core.provider import MODEL_REGISTRY

        return {mid: info.description for mid, info in MODEL_REGISTRY.items() if info.description}
    except Exception as e:
        logger.debug("model lookup failed: %s", e)
        return {}


_MODEL_ALIASES: dict[str, str] = {}
_MODEL_INFO: dict[str, str] = {}


def refresh_aliases_and_info() -> tuple[dict[str, str], dict[str, str]]:
    """惰性初始化 MODEL_ALIASES 和 MODEL_INFO（含模块缓存）。"""
    global _MODEL_ALIASES, _MODEL_INFO
    if not _MODEL_ALIASES:
        _MODEL_ALIASES = build_model_aliases()
    if not _MODEL_INFO:
        _MODEL_INFO = build_model_info()
    return (_MODEL_ALIASES, _MODEL_INFO)


def get_model_aliases() -> dict[str, str]:
    return _MODEL_ALIASES


def get_model_info() -> dict[str, str]:
    return _MODEL_INFO
