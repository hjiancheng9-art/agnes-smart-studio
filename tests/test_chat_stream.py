"""Tests for core.chat_stream — extracted send_stream implementation."""

from unittest.mock import MagicMock

from core.chat_stream import _send_stream_impl


class TestSendStreamImportAndSignature:
    """Verify the extracted module is importable and correctly wired."""

    def test_module_importable(self):
        """The chat_stream module should be importable."""
        import core.chat_stream

        assert hasattr(core.chat_stream, "_send_stream_impl")

    def test_is_generator_function(self):
        """_send_stream_impl should be a generator function."""
        import inspect

        assert inspect.isgeneratorfunction(_send_stream_impl)

    def test_chat_session_has_thin_wrapper(self):
        """ChatSession.send_stream should delegate to _send_stream_impl."""
        import inspect

        from core.chat import ChatSession

        source = inspect.getsource(ChatSession.send_stream)
        assert "_send_stream_impl" in source


class TestSendStreamSmoke:
    """Smoke tests with minimal ChatSession mock — verify no crashes."""

    def _make_minimal_session(self):
        """Build the absolute minimum mock needed for _send_stream_impl to initialize."""
        session = MagicMock()
        # Basic attrs that send_stream preamble touches
        session._last_user_text = ""
        session._last_turn_had_errors = False
        session._temp_input_files = set()
        session.client = MagicMock()
        session.model = "test-model"
        session.vision_client = MagicMock()
        session.vision_model = "test-vision"
        session.cfg = MagicMock()
        session.cfg.model = "test-model"
        session.tools = MagicMock()
        session.tools.get_filtered_definitions = MagicMock(return_value=[])
        session.skills = MagicMock()
        session.messages = [{"role": "system", "content": "system prompt"}]
        session.ctx_mgr = MagicMock()
        session.ctx_mgr.needs_compression = MagicMock(return_value=False)
        session.routing = MagicMock()
        session._budget = None
        session._vote_enabled = False
        session.vision_ctx = MagicMock()
        session.vision_ctx.active = False
        session.supports_tools = False
        session._text_fallback_chain = MagicMock(return_value=[("test-model", MagicMock())])
        session._auto_route = MagicMock()
        session._intelligence_hook = MagicMock()
        session._intelligence_hook.analyze = MagicMock(return_value={"mode": "BALANCED"})
        session._inject_memory = MagicMock()
        session._deliberate = MagicMock(return_value=None)
        session._check_budget = MagicMock()
        session._rebuild_ctx_mgr = MagicMock()
        session._consume_stream_delta = MagicMock()
        session._consume_stream_delta.return_value = iter([("text", "hello"), ("text", " world")])
        # Need to return (buffer, tool_calls, stream_error, last_usage) from generator
        session._consume_stream_delta.side_effect = None

        # Make it a real generator
        def fake_consume(client, model, tools, *, _retry_empty=False):
            yield ("text", "hello world")
            return ("hello world", [], False, None)

        session._consume_stream_delta = fake_consume
        session._is_stream_error = MagicMock(return_value=False)
        session._finalize_outcome = MagicMock()
        session._try_adversarial_bypass = MagicMock()

        def fake_bypass(*args):
            yield from []
            return False

        session._try_adversarial_bypass = fake_bypass
        session._trigger_reflection = MagicMock()
        session._auto_remember = MagicMock()
        session._record_trace_failure = MagicMock()
        session._record_outcome_promptlab = MagicMock()
        session._append_assistant_with_tools = MagicMock(return_value="buffer with tools")
        session._run_tool_calls = MagicMock()

        def fake_run_tools(*args):
            yield from []

        session._run_tool_calls = fake_run_tools
        return session

    def test_simple_text_no_tools(self):
        """Simple text input without tools should complete successfully."""
        session = self._make_minimal_session()

        gen = _send_stream_impl(session, "hello")
        results = list(gen)

        # Should have yielded at least some text
        text_yields = [r for r in results if r[0] == "text"]
        assert len(text_yields) > 0

    def test_short_question_no_multi_agent(self):
        """Short question should not trigger agent mode."""
        session = self._make_minimal_session()

        gen = _send_stream_impl(session, "what is 2+2?")
        list(gen)

        # Should complete normally
        session._finalize_outcome.assert_called()

    def test_large_input_truncation(self):
        """Input > 4000 chars should be truncated to temp file."""
        session = self._make_minimal_session()
        long_text = "x" * 5000

        gen = _send_stream_impl(session, long_text)
        results = list(gen)

        # Should have yielded an info about truncation
        info_yields = [r for r in results if r[0] == "info" and "截断" in str(r[1])]
        assert len(info_yields) > 0

    def test_empty_input_completes(self):
        """Empty input should complete without errors."""
        session = self._make_minimal_session()

        gen = _send_stream_impl(session, "")
        list(gen)

        # Should complete
        session._finalize_outcome.assert_called()
