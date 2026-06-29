"""模型路由矩阵 — 从 ZCode models_catalog 吸收。

10 提供者 × 119 模型 × 双协议 (anthropic/openai-compatible) × 推理级别 × 模态追踪。

能力来源: ZCode resources/model-providers/models_catalog_china_llm_zcode_2026-06-03.json
吸收日期: 2026-06-29
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ── 类型定义 ──────────────────────────────────────────────────────

ProtocolKind = Literal["anthropic", "openai-compatible"]
ReasoningLevel = Literal["off", "enabled", "high", "max"]
ModalityType = Literal["text", "image", "audio", "video"]


@dataclass(frozen=True)
class ReasoningConfig:
    """模型推理配置。"""
    default_level: ReasoningLevel
    available_levels: tuple[ReasoningLevel, ...]


@dataclass(frozen=True)
class ModelSpec:
    """单模型规格。"""
    id: str
    name: str
    kinds: tuple[ProtocolKind, ...]
    modalities: tuple[tuple[ModalityType, ...], tuple[ModalityType, ...]]  # (input, output)
    context_window: int
    max_output_tokens: int
    reasoning: ReasoningConfig | None = None


@dataclass(frozen=True)
class ProviderSpec:
    """提供者规格。"""
    id: str
    name: str
    base_url: str
    paths: dict[ProtocolKind, str]
    default_kind: ProtocolKind
    models: tuple[ModelSpec, ...]


# ── 模型路由数据（完整从 ZCode 提取）────────────────────────────

PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="moonshot-kimi",
        name="Moonshot AI / Kimi",
        base_url="https://api.moonshot.cn",
        paths={
            "anthropic": "/anthropic/v1/messages",
            "openai-compatible": "/v1/chat/completions",
        },
        default_kind="anthropic",
        models=(
            ModelSpec("kimi-k2.6", "kimi-k2.6", ("anthropic", "openai-compatible"),
                      (("text", "image", "video"), ("text",)), 262144, 98304,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("kimi-k2.5", "kimi-k2.5", ("anthropic", "openai-compatible"),
                      (("text", "image"), ("text",)), 262144, 98304,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("moonshot-v1-8k", "moonshot-v1-8k", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 8192, 0, None),
            ModelSpec("moonshot-v1-32k", "moonshot-v1-32k", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 32768, 0, None),
            ModelSpec("moonshot-v1-128k", "moonshot-v1-128k", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 131072, 0, None),
            ModelSpec("moonshot-v1-8k-vision-preview", "moonshot-v1-8k-vision-preview",
                      ("anthropic", "openai-compatible"), (("text", "image"), ("text",)), 8192, 0, None),
            ModelSpec("moonshot-v1-32k-vision-preview", "moonshot-v1-32k-vision-preview",
                      ("anthropic", "openai-compatible"), (("text", "image"), ("text",)), 32768, 0, None),
            ModelSpec("moonshot-v1-128k-vision-preview", "moonshot-v1-128k-vision-preview",
                      ("anthropic", "openai-compatible"), (("text", "image"), ("text",)), 131072, 0, None),
        ),
    ),
    ProviderSpec(
        id="minimax",
        name="MiniMax",
        base_url="https://api.minimaxi.com",
        paths={
            "anthropic": "/anthropic/v1/messages",
            "openai-compatible": "/v1/chat/completions",
        },
        default_kind="anthropic",
        models=(
            ModelSpec("MiniMax-M3", "MiniMax-M3", ("anthropic", "openai-compatible"),
                      (("text", "image", "video"), ("text",)), 1000000, 0, None),
            ModelSpec("MiniMax-M2.7", "MiniMax-M2.7", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 204800, 0, None),
            ModelSpec("MiniMax-M2.7-highspeed", "MiniMax-M2.7-highspeed",
                      ("anthropic", "openai-compatible"), (("text",), ("text",)), 204800, 0, None),
            ModelSpec("MiniMax-M2.5", "MiniMax-M2.5", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 204800, 0, None),
            ModelSpec("MiniMax-M2.5-highspeed", "MiniMax-M2.5-highspeed",
                      ("anthropic", "openai-compatible"), (("text",), ("text",)), 204800, 0, None),
            ModelSpec("MiniMax-M2.1", "MiniMax-M2.1", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 204800, 0, None),
            ModelSpec("MiniMax-M2.1-highspeed", "MiniMax-M2.1-highspeed",
                      ("anthropic", "openai-compatible"), (("text",), ("text",)), 204800, 0, None),
            ModelSpec("MiniMax-M2", "MiniMax-M2", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 204800, 131072, None),
        ),
    ),
    ProviderSpec(
        id="deepseek",
        name="DeepSeek",
        base_url="https://api.deepseek.com",
        paths={
            "anthropic": "/anthropic/v1/messages",
            "openai-compatible": "/chat/completions",
        },
        default_kind="anthropic",
        models=(
            ModelSpec("deepseek-v4-flash", "deepseek-v4-flash", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 1000000, 384000,
                      ReasoningConfig("max", ("off", "high", "max"))),
            ModelSpec("deepseek-v4-pro", "deepseek-v4-pro", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 1000000, 384000,
                      ReasoningConfig("max", ("off", "high", "max"))),
        ),
    ),
    ProviderSpec(
        id="qwen-alibaba-model-studio-cn",
        name="Qwen / Alibaba Cloud Model Studio (China)",
        base_url="https://dashscope.aliyuncs.com",
        paths={
            "anthropic": "/apps/anthropic/v1/messages",
            "openai-compatible": "/compatible-mode/v1/chat/completions",
        },
        default_kind="anthropic",
        models=(
            ModelSpec("qwen3.5-plus", "qwen3.5-plus", ("anthropic", "openai-compatible"),
                      (("text", "image", "video"), ("text",)), 1000000, 65536,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("qwen3.5-flash", "qwen3.5-flash", ("anthropic", "openai-compatible"),
                      (("text", "image", "video"), ("text",)), 1000000, 65536,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("qwen3-max", "qwen3-max", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 262144, 65536, None),
            ModelSpec("qwen-plus", "qwen-plus", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 1000000, 32768,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("qwen-flash", "qwen-flash", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 1000000, 32768,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("qwen3-vl-plus", "qwen3-vl-plus", ("anthropic", "openai-compatible"),
                      (("text", "image", "video"), ("text",)), 262144, 32768,
                      ReasoningConfig("enabled", ("off", "enabled"))),
        ),
    ),
    ProviderSpec(
        id="qwen-alibaba-model-studio-intl",
        name="Qwen / Alibaba Cloud Model Studio (International)",
        base_url="https://dashscope-intl.aliyuncs.com",
        paths={
            "openai-compatible": "/compatible-mode/v1/chat/completions",
        },
        default_kind="openai-compatible",
        models=(
            ModelSpec("qwen3.5-plus", "qwen3.5-plus", ("openai-compatible",),
                      (("text", "image", "video"), ("text",)), 1000000, 65536,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("qwen3.5-flash", "qwen3.5-flash", ("openai-compatible",),
                      (("text", "image", "video"), ("text",)), 1000000, 65536,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("qwen3-max", "qwen3-max", ("openai-compatible",),
                      (("text",), ("text",)), 262144, 65536, None),
            ModelSpec("qwen-plus", "qwen-plus", ("openai-compatible",),
                      (("text",), ("text",)), 1000000, 32768,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("qwen-flash", "qwen-flash", ("openai-compatible",),
                      (("text",), ("text",)), 1000000, 32768,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("qwen3-vl-plus", "qwen3-vl-plus", ("openai-compatible",),
                      (("text", "image", "video"), ("text",)), 262144, 32768,
                      ReasoningConfig("enabled", ("off", "enabled"))),
        ),
    ),
    ProviderSpec(
        id="xiaomi-mimo",
        name="Xiaomi MiMo",
        base_url="https://api.xiaomimimo.com",
        paths={
            "anthropic": "/anthropic/v1/messages",
            "openai-compatible": "/v1/chat/completions",
        },
        default_kind="anthropic",
        models=(
            ModelSpec("mimo-v2.5-pro", "mimo-v2.5-pro", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 1000000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("mimo-v2.5", "mimo-v2.5", ("anthropic", "openai-compatible"),
                      (("text", "image", "audio", "video"), ("text",)), 1000000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("mimo-v2-pro", "mimo-v2-pro", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 1000000, 131072, None),
            ModelSpec("mimo-v2-omni", "mimo-v2-omni", ("anthropic", "openai-compatible"),
                      (("text", "image", "audio", "video"), ("text",)), 262144, 131072, None),
            ModelSpec("mimo-v2-flash", "mimo-v2-flash", ("anthropic", "openai-compatible"),
                      (("text",), ("text",)), 262144, 65536,
                      ReasoningConfig("enabled", ("off", "enabled"))),
        ),
    ),
    ProviderSpec(
        id="zai",
        name="Z.AI",
        base_url="https://api.z.ai",
        paths={"anthropic": "/anthropic/v1/messages"},
        default_kind="anthropic",
        models=(
            ModelSpec("glm-5.1", "glm-5.1", ("anthropic",), (("text",), ("text",)), 200000, 64000,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-5.1-highspeed", "glm-5.1-highspeed", ("anthropic",),
                      (("text",), ("text",)), 200000, 64000,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-5", "glm-5", ("anthropic",), (("text",), ("text",)), 200000, 64000,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-5-turbo", "glm-5-turbo", ("anthropic",), (("text",), ("text",)), 200000, 64000,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.7", "glm-4.7", ("anthropic",), (("text",), ("text",)), 200000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.7-flashx", "glm-4.7-flashx", ("anthropic",),
                      (("text",), ("text",)), 200000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.7-flash", "glm-4.7-flash", ("anthropic",),
                      (("text",), ("text",)), 200000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.6", "glm-4.6", ("anthropic",), (("text",), ("text",)), 200000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.5-air", "glm-4.5-air", ("anthropic",),
                      (("text",), ("text",)), 131072, 98304,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.5", "glm-4.5", ("anthropic",), (("text",), ("text",)), 131072, 98304,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.6v", "glm-4.6v", ("anthropic",), (("text", "image"), ("text",)),
                      131072, 32768, None),
            ModelSpec("glm-4.6v-flash", "glm-4.6v-flash", ("anthropic",),
                      (("text", "image"), ("text",)), 131072, 32768, None),
            ModelSpec("glm-4.6v-flashx", "glm-4.6v-flashx", ("anthropic",),
                      (("text", "image"), ("text",)), 131072, 32768, None),
            ModelSpec("glm-4.1v-thinking-flashx", "glm-4.1v-thinking-flashx", ("anthropic",),
                      (("text", "image"), ("text",)), 65536, 32768, None),
            ModelSpec("glm-4.1v-thinking-flash", "glm-4.1v-thinking-flash", ("anthropic",),
                      (("text", "image"), ("text",)), 65536, 32768, None),
            ModelSpec("glm-4-flashx-250414", "glm-4-flashx-250414", ("anthropic",),
                      (("text",), ("text",)), 131072, 16384, None),
            ModelSpec("glm-4-flash-250414", "glm-4-flash-250414", ("anthropic",),
                      (("text",), ("text",)), 131072, 16384, None),
            ModelSpec("glm-4v-flash", "glm-4v-flash", ("anthropic",),
                      (("text", "image"), ("text",)), 16384, 1024, None),
            ModelSpec("codegeex-4", "codegeex-4", ("anthropic",), (("text",), ("text",)),
                      131072, 32768, None),
            ModelSpec("charglm-4", "charglm-4", ("anthropic",), (("text",), ("text",)),
                      8192, 4096, None),
            ModelSpec("emohaa", "emohaa", ("anthropic",), (("text",), ("text",)),
                      8192, 4096, None),
        ),
    ),
    ProviderSpec(
        id="bigmodel",
        name="BigModel / 智谱",
        base_url="https://open.bigmodel.cn",
        paths={"anthropic": "/anthropic/v1/messages"},
        default_kind="anthropic",
        models=(  # Same model set as zai, different base_url
            ModelSpec("glm-5.1", "glm-5.1", ("anthropic",), (("text",), ("text",)), 200000, 64000,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-5.1-highspeed", "glm-5.1-highspeed", ("anthropic",),
                      (("text",), ("text",)), 200000, 64000,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-5", "glm-5", ("anthropic",), (("text",), ("text",)), 200000, 64000,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-5-turbo", "glm-5-turbo", ("anthropic",), (("text",), ("text",)), 200000, 64000,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.7", "glm-4.7", ("anthropic",), (("text",), ("text",)), 200000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.7-flashx", "glm-4.7-flashx", ("anthropic",),
                      (("text",), ("text",)), 200000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.7-flash", "glm-4.7-flash", ("anthropic",),
                      (("text",), ("text",)), 200000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.6", "glm-4.6", ("anthropic",), (("text",), ("text",)), 200000, 131072,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.5-air", "glm-4.5-air", ("anthropic",),
                      (("text",), ("text",)), 131072, 98304,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.5", "glm-4.5", ("anthropic",), (("text",), ("text",)), 131072, 98304,
                      ReasoningConfig("enabled", ("off", "enabled"))),
            ModelSpec("glm-4.6v", "glm-4.6v", ("anthropic",), (("text", "image"), ("text",)),
                      131072, 32768, None),
            ModelSpec("glm-4.6v-flash", "glm-4.6v-flash", ("anthropic",),
                      (("text", "image"), ("text",)), 131072, 32768, None),
            ModelSpec("glm-4.6v-flashx", "glm-4.6v-flashx", ("anthropic",),
                      (("text", "image"), ("text",)), 131072, 32768, None),
            ModelSpec("glm-4.1v-thinking-flashx", "glm-4.1v-thinking-flashx", ("anthropic",),
                      (("text", "image"), ("text",)), 65536, 32768, None),
            ModelSpec("glm-4.1v-thinking-flash", "glm-4.1v-thinking-flash", ("anthropic",),
                      (("text", "image"), ("text",)), 65536, 32768, None),
            ModelSpec("glm-4-flashx-250414", "glm-4-flashx-250414", ("anthropic",),
                      (("text",), ("text",)), 131072, 16384, None),
            ModelSpec("glm-4-flash-250414", "glm-4-flash-250414", ("anthropic",),
                      (("text",), ("text",)), 131072, 16384, None),
            ModelSpec("glm-4v-flash", "glm-4v-flash", ("anthropic",),
                      (("text", "image"), ("text",)), 16384, 1024, None),
            ModelSpec("codegeex-4", "codegeex-4", ("anthropic",), (("text",), ("text",)),
                      131072, 32768, None),
            ModelSpec("charglm-4", "charglm-4", ("anthropic",), (("text",), ("text",)),
                      8192, 4096, None),
            ModelSpec("emohaa", "emohaa", ("anthropic",), (("text",), ("text",)),
                      8192, 4096, None),
        ),
    ),
    ProviderSpec(
        id="zai-coding-plan",
        name="Z.AI Coding Plan",
        base_url="https://api.z.ai",
        paths={"anthropic": "/anthropic/v1/messages"},
        default_kind="anthropic",
        models=(),  # Same GLM models as zai provider, routed via Coding Plan endpoint
    ),
    ProviderSpec(
        id="bigmodel-coding-plan",
        name="BigModel / 智谱 Coding Plan",
        base_url="https://open.bigmodel.cn",
        paths={"anthropic": "/anthropic/v1/messages"},
        default_kind="anthropic",
        models=(),  # Same GLM models as bigmodel provider, routed via Coding Plan endpoint
    ),
)

# ── 索引与查询函数 ──────────────────────────────────────────────

_MODEL_INDEX: dict[str, ModelSpec] = {}
_PROVIDER_INDEX: dict[str, ProviderSpec] = {}

for _p in PROVIDERS:
    _PROVIDER_INDEX[_p.id] = _p
    for _m in _p.models:
        _MODEL_INDEX[_m.id] = _m


def resolve_model(model_id: str) -> ModelSpec | None:
    """按模型 ID 查找规格。"""
    return _MODEL_INDEX.get(model_id)


def resolve_provider(provider_id: str) -> ProviderSpec | None:
    """按提供者 ID 查找规格。"""
    return _PROVIDER_INDEX.get(provider_id)


def find_models_by_capability(
    *, min_context: int = 0, supports_image: bool = False, supports_video: bool = False,
    supports_reasoning: bool = False, protocols: tuple[ProtocolKind, ...] | None = None,
) -> list[tuple[str, str]]:
    """按能力筛选模型，返回 [(provider_id, model_id), ...]。"""
    results: list[tuple[str, str]] = []
    for p in PROVIDERS:
        for m in p.models:
            if m.context_window < min_context:
                continue
            if supports_image and "image" not in m.modalities[0]:
                continue
            if supports_video and "video" not in m.modalities[0]:
                continue
            if supports_reasoning and m.reasoning is None:
                continue
            if protocols and not any(k in m.kinds for k in protocols):
                continue
            results.append((p.id, m.id))
    return results


def pick_best_model(
    provider_id: str | None = None, *, min_context: int = 0,
    prefer_reasoning: bool = False, prefer_vision: bool = False,
) -> str | None:
    """选取最合适的模型 ID。"""
    candidates: list[tuple[int, str, str]] = []
    for p in PROVIDERS:
        if provider_id and p.id != provider_id:
            continue
        for m in p.models:
            score = 0
            if m.context_window >= min_context:
                score += 1
            if prefer_reasoning and m.reasoning:
                score += 2
            if prefer_vision and "image" in m.modalities[0]:
                score += 1
            candidates.append((score, p.id, m.id))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (-x[0], -resolve_model(x[2]).context_window))
    return candidates[0][2]


def get_provider_url(provider_id: str, kind: ProtocolKind = "anthropic") -> str | None:
    """获取提供者的完整 API URL。"""
    p = _PROVIDER_INDEX.get(provider_id)
    if not p:
        return None
    path = p.paths.get(kind)
    if not path:
        return None
    return f"{p.base_url}{path}"


def get_protocol_path(provider_id: str, model_id: str, kind: ProtocolKind) -> dict | None:
    """生成协议层转换路径（仿 ZCode 的 reasoning level path 模式）。

    返回示例:
    {
      "base_url": "https://api.deepseek.com/anthropic/v1/messages",
      "thinking": {"budgetTokens": 1024, "type": "enabled"},
      "output_config": {"effort": "max"}
    }
    """
    p = _PROVIDER_INDEX.get(provider_id)
    m = _MODEL_INDEX.get(model_id)
    if not p or not m:
        return None
    if kind not in m.kinds:
        return None

    url = get_provider_url(provider_id, kind)
    result: dict = {"base_url": url, "kind": kind}

    # Add reasoning config if available
    if m.reasoning:
        result["reasoning_default"] = m.reasoning.default_level
        if kind == "anthropic":
            result["thinking"] = {"budgetTokens": 1024, "type": "enabled"}
        elif kind == "openai-compatible":
            result["extra_body"] = {"thinking": {"type": "enabled"}}

    return result


# ── 统计 ─────────────────────────────────────────────────────────

def count_models() -> dict:
    """返回模型统计信息。"""
    total_models = sum(len(p.models) for p in PROVIDERS)
    with_reasoning = sum(1 for m in _MODEL_INDEX.values() if m.reasoning)
    with_vision = sum(1 for m in _MODEL_INDEX.values() if "image" in m.modalities[0])

    return {
        "providers": len(PROVIDERS),
        "models": total_models,
        "with_reasoning": with_reasoning,
        "with_vision": with_vision,
        "protocols": ["anthropic", "openai-compatible"],
    }


__all__ = [
    "ModelSpec", "ProviderSpec", "ReasoningConfig", "ReasoningLevel", "ProtocolKind",
    "PROVIDERS",
    "resolve_model", "resolve_provider", "find_models_by_capability",
    "pick_best_model", "get_provider_url", "get_protocol_path", "count_models",
]
