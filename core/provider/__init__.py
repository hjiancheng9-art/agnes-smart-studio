"""Provider & client layer (17 modules).

Handles API clients, streaming, model routing, and fallback chains.
"""

__all__ = [
    # Core provider infrastructure
    "provider",  # provider manager — load, switch, create clients
    "provider_adapter",  # adapter layer for provider API differences
    "provider_history",  # track provider switching for analytics
    "provider_policy",  # policy-driven provider selection
    # Clients
    "client",  # synchronous CruxClient (HTTP + SSE streaming)
    "async_client",  # async CruxClient (aiohttp)
    "async_runtime",  # async runtime helpers
    # Streaming
    "stream_adapter",  # unified stream consumption/transformation
    "stream_protocol",  # stream event type contracts
    "streaming_executor",  # tool execution during streaming
    # Model routing
    "model_router",  # tier-based model selection (light/pro/heavy)
    "model_worker",  # worker pool for model inference
    "routing_service",  # fallback chain builder and routing decisions
    "routing_signals",  # signals that influence routing (cost, latency)
    "routing_state",  # persistent routing state
    "router",  # unified router (commands + NL classification)
    "router_replay",  # replay router decisions for debugging
]
