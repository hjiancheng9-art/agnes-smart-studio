"""Provider-aware adapter layer — encapsulates per-provider API differences.

ProviderAdapter knows each provider's max_tokens, thinking format,
stream format, auth scheme. Model metadata is delegated to core.provider
(MODEL_REGISTRY as single source of truth).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ═══════════════════════════════════════════════════════════════
# Provider adapter — per-provider API differences
# ═══════════════════════════════════════════════════════════════

@dataclass
class ProviderAdapter:
    """Encapsulates all provider-specific API behaviors."""

    provider_id: str
    # Streaming
    sse_data_prefix: str = "data: "  # OpenAI standard
    sse_done_marker: str = "[DONE]"
    sse_strip_prefix: bool = True  # strip the prefix before JSON parse
    # Thinking / reasoning
    thinking_param_style: str = "chat_template_kwargs"
    # "chat_template_kwargs" for AGNES/DeepSeek
    # "thinking" for Anthropic-style {"thinking": {"type": "enabled"}}
    # "none" for models without thinking support
    thinking_response_field: str = "reasoning_content"
    # field name in stream delta for thinking tokens
    # Auth
    auth_scheme: str = "Bearer"  # "Bearer" for OpenAI-compatible, "ApiKey" etc.
    # URL construction
    chat_path: str = "/chat/completions"  # appended to base_url
    models_path: str = "/models"
    # Defaults
    default_max_tokens: int = 16384
    default_temperature: float = 0.7

    def build_thinking_params(self) -> dict[str, Any]:
        """Build provider-specific thinking/推理 parameter dict."""
        if self.thinking_param_style == "chat_template_kwargs":
            return {"chat_template_kwargs": {"enable_thinking": True}}
        elif self.thinking_param_style == "thinking":
            return {"thinking": {"type": "enabled"}}
        return {}

    def build_stream_kwargs(self) -> dict[str, Any]:
        """Build provider-specific streaming parameters."""
        return {"stream": True, "stream_options": {"include_usage": True}}

    @property
    def max_output_tokens(self) -> int:
        return self.default_max_tokens


# ═══════════════════════════════════════════════════════════════
# Provider registry — source of truth for all adapters
# ═══════════════════════════════════════════════════════════════

PROVIDER_ADAPTERS: dict[str, ProviderAdapter] = {
    "deepseek": ProviderAdapter(
        provider_id="deepseek",
        thinking_param_style="chat_template_kwargs",
        thinking_response_field="reasoning_content",
        default_max_tokens=8192,
    ),
    "zhipu": ProviderAdapter(
        provider_id="zhipu",
        sse_data_prefix="data: ",
        thinking_param_style="chat_template_kwargs",
        thinking_response_field="reasoning_content",
        default_max_tokens=1024,
    ),
    "crux": ProviderAdapter(
        provider_id="crux",
        thinking_param_style="chat_template_kwargs",
        thinking_response_field="reasoning_content",
        default_max_tokens=16384,
    ),
}


def get_adapter(provider_id: str) -> ProviderAdapter:
    """Get the adapter for a given provider, with fallback to generic."""
    return PROVIDER_ADAPTERS.get(provider_id, ProviderAdapter(provider_id="generic"))


# ═══════════════════════════════════════════════════════════════
# Model metadata queries — delegated to core.provider
# ═══════════════════════════════════════════════════════════════

def get_capability(model_id: str):
    """Look up model capability by ID or alias. Returns ModelInfo or None.

    Delegated to core.provider.MODEL_REGISTRY (single source of truth).
    """
    from core.provider import get_capability_info
    return get_capability_info(model_id)


def get_max_tokens(model_id: str, is_tool_call: bool = False) -> int:
    """Get appropriate max_tokens for a model, considering tool use.

    Delegated to core.provider.get_max_tokens_for_model.
    """
    from core.provider import get_max_tokens_for_model
    return get_max_tokens_for_model(model_id, is_tool_call)


def get_thinking_params(model_id: str) -> dict[str, Any]:
    """Get thinking-enable params suitable for this model's provider.

    Delegated to core.provider.get_thinking_params_for_model.
    """
    from core.provider import get_thinking_params_for_model
    return get_thinking_params_for_model(model_id)


# Backward-compat alias
ModelCapability = None  # type: ignore — replaced by provider.ModelInfo
MODEL_CAPABILITIES: dict = {}  # deprecated, use provider.MODEL_REGISTRY
