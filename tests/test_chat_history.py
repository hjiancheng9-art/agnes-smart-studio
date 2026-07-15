"""Guardrail tests for ChatSession message-history sanitization.

These pin the exact truncation behavior of sanitize_messages BEFORE the logic
is moved out of core/chat.py into core/chat_history.py (refactor P3). They must
keep passing byte-for-byte through the migration.

API contract being enforced: every assistant message carrying ``tool_calls``
must be immediately followed by one ``tool``-role result per call id. Any
incomplete trailing sequence is truncated so the restored history is a clean
API boundary.
"""

from core.chat import ChatSession

sanitize = ChatSession.sanitize_messages


class TestSanitizeMessagesBasics:
    def test_empty_returns_empty(self):
        assert sanitize([]) == []

    def test_plain_conversation_untouched(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "bye"},
            {"role": "assistant", "content": "cya"},
        ]
        assert sanitize(msgs) == msgs

    def test_complete_tool_call_sequence_kept(self):
        msgs = [
            {"role": "user", "content": "read it"},
            {"role": "assistant", "tool_calls": [{"id": "a1"}, {"id": "a2"}]},
            {"role": "tool", "tool_call_id": "a1", "content": "r1"},
            {"role": "tool", "tool_call_id": "a2", "content": "r2"},
            {"role": "assistant", "content": "done"},
        ]
        assert sanitize(msgs) == msgs


class TestSanitizeMessagesTruncation:
    def test_assistant_tool_calls_without_results_stripped(self):
        # Crash mid-call: assistant with tool_calls, no tool results, ends here.
        msgs = [
            {"role": "user", "content": "do it"},
            {"role": "assistant", "tool_calls": [{"id": "x1"}]},
        ]
        # Both the dangling assistant AND its triggering user msg are removed.
        assert sanitize(msgs) == []

    def test_partial_tool_results_stripped(self):
        # N tool_calls but < N results → whole incomplete block removed.
        msgs = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "tool_calls": [{"id": "x1"}, {"id": "x2"}]},
            {"role": "tool", "tool_call_id": "x1", "content": "only one"},
        ]
        assert sanitize(msgs) == []

    def test_keeps_prior_complete_turn_then_strips_incomplete(self):
        msgs = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "tool_calls": [{"id": "y1"}]},  # dangling
        ]
        assert sanitize(msgs) == [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "answer"},
        ]

    def test_user_message_while_pending_truncates(self):
        # A user message arriving while tool calls are pending is invalid.
        msgs = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "tool_calls": [{"id": "z1"}]},
            {"role": "user", "content": "premature"},
        ]
        assert sanitize(msgs) == []

    def test_consecutive_assistant_tool_calls_truncate(self):
        msgs = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "tool_calls": [{"id": "c1"}]},
            {"role": "assistant", "tool_calls": [{"id": "c2"}]},  # invalid
        ]
        assert sanitize(msgs) == []

    def test_orphan_tool_result_truncates(self):
        # Tool result with unknown/already-consumed id → truncate at that point.
        msgs = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
            {"role": "tool", "tool_call_id": "ghost", "content": "orphan"},
        ]
        assert sanitize(msgs) == [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]

    def test_system_message_always_kept(self):
        msgs = [{"role": "system", "content": "rules"}]
        assert sanitize(msgs) == msgs
