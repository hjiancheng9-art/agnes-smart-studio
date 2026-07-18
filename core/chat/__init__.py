"""Chat & session layer (19 modules).

Manages the conversation loop, system prompts, tool dispatch, and session state.
"""

__all__ = [
    # Core chat
    "chat",  # ChatSession — the main conversation engine
    "chat_prompt",  # system prompt builder
    "chat_routing",  # routing decisions during chat
    "chat_model_helpers",  # model-specific prompt adjustment
    "chat_toggle_mixin",  # feature toggle support (code_mode, agent_mode)
    "chat_tool_dispatch",  # tool call dispatch during chat
    "chat_tool_helpers",  # tool helper functions
    "chat_vision",  # vision model integration for chat
    "chat_history",  # conversation history management
    "chat_hooks_setup",  # hook registration for chat lifecycle
    # Session management
    "session_config",  # SessionConfig — extracted session state
    "session_lifecycle",  # session creation, activation, teardown
    "session_mgr",  # multi-session management
    "session_tracker",  # session activity tracking
    "session_wire",  # session wiring/injection
    # Ancillary
    "gpt_tool_result",  # GPT/OpenAI tool result handling
    "cost_tracker",  # token cost tracking and budgeting
    "context_memory",  # conversation context memory
    "context_memory_hooks",  # hook integration for context memory
]
