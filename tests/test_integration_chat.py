"""Integration tests for chat.py Phase hooks (P1-P13).

Verifies that all hooks are properly injected into ChatSession
without breaking existing functionality.
"""

import py_compile


class TestChatSyntax:
    """Phase hooks don't break syntax."""

    def test_chat_py_compiles(self):
        py_compile.compile("core/chat.py", doraise=True)

    def test_chat_py_has_validation_layer(self):
        with open("core/chat.py", encoding="utf-8") as f:
            content = f.read()
        assert "from core.tool_validation_integration import" in content
        assert "self.tvl" in content

    def test_chat_py_has_p8_flag(self):
        with open("core/chat.py", encoding="utf-8") as f:
            content = f.read()
        assert "_p8_policy_hooked" in content

    def test_chat_py_has_p9_flag(self):
        with open("core/chat.py", encoding="utf-8") as f:
            content = f.read()
        assert "_p9_project_hooked" in content

    def test_chat_py_has_p10_flag(self):
        with open("core/chat.py", encoding="utf-8") as f:
            content = f.read()
        assert "_p10_trace_hooked" in content

    def test_chat_py_has_p11_flag(self):
        with open("core/chat.py", encoding="utf-8") as f:
            content = f.read()
        assert "_p11_failure_learning_hooked" in content

    def test_chat_py_has_p12_flag(self):
        with open("core/chat.py", encoding="utf-8") as f:
            content = f.read()
        assert "_p12_benchmark_hooked" in content

    def test_chat_py_has_p13_flag(self):
        with open("core/chat.py", encoding="utf-8") as f:
            content = f.read()
        assert "_p13_field_arena_hooked" in content

    def test_chat_imports_cleanly(self):
        """Importing chat module doesn't crash at syntax level."""
        import ast
        with open("core/chat.py", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        # Just verify it parses — will find classes, functions etc
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert "ChatSession" in classes


class TestTvlIntegration:
    """ValidationLayer hooks are accessible through the module."""

    def test_validation_layer_imports(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        assert vl is not None

    def test_validation_layer_has_all_phases(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()

        # P1
        assert hasattr(vl, "validate")
        assert hasattr(vl, "validate_tool_call")

        # P2
        assert hasattr(vl, "validate_result")
        assert hasattr(vl, "check_consistency")

        # P3
        assert hasattr(vl, "context_memory")

        # P4
        assert hasattr(vl, "multi_agent")

        # P5
        assert hasattr(vl, "compile_prompt")

        # P6
        assert hasattr(vl, "telemetry")
        assert hasattr(vl, "config")

        # P8
        assert hasattr(vl, "policy_router")

        # P9
        assert hasattr(vl, "ensure_project_index")

        # P10
        assert hasattr(vl, "decision_recorder")

        # P11
        assert hasattr(vl, "learning_loop")

        # P12
        assert hasattr(vl, "_bench_suite")
        assert hasattr(vl, "run_benchmark")

        # P13
        assert hasattr(vl, "_field_arena")

    def test_p1_validation_works(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        issues = vl.validate_tool_call("read_file", {"path": "test.txt"})
        assert isinstance(issues, list)

    def test_p4_multi_agent_accessible(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        assert vl.multi_agent is not None
        rep = vl.multi_agent.review_turn("Hello", "Hi!", [])
        assert rep is not None

    def test_p8_policy_routes(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        policy = vl.route_policy("Hello")
        assert policy.mode in ("fast", "balanced")

    def test_p10_trace_recording(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        session = vl.start_trace_session("integ-test-session")
        assert session.session_id == "integ-test-session"
        vl.record_decision("test", "decision", "reason", outcome="ok")
        vl.close_trace_session()

    def test_p11_capture_and_analyze(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        s = vl.capture_failure("tool_validation_blocked", user_message="test")
        result = vl.analyze_failure(s)
        assert len(result.root_cause) > 0

    def test_p12_benchmark_accessible(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        assert vl.benchmark_suite.total >= 15

    def test_p13_field_arena_accessible(self):
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()
        assert vl._field_arena is not None


class TestAllPhasesNonBreaking:
    """Running all hooks doesn't crash the system."""

    def test_validation_layer_init_safe(self):
        for _ in range(5):
            from core.tool_validation_integration import ValidationLayer
            vl = ValidationLayer()
            assert vl is not None

    def test_chain_p1_p8_p10(self):
        """P1 validate → P8 route → P10 record — all work together."""
        from core.tool_validation_integration import ValidationLayer
        vl = ValidationLayer()

        # Start trace (P10)
        vl.start_trace_session("chain-test")

        # Route policy (P8)
        policy = vl.route_policy("Read file core/auth.py and fix the bug")
        assert policy is not None

        # Validate tool call (P1)
        issues = vl.validate_tool_call("read_file", {"path": "core/auth.py"})
        assert isinstance(issues, list)

        # Record decision (P10)
        vl.record_decision("tool_validation", "read_file",
                           f"Validated: {len(issues)} issues", outcome="pass")

        vl.close_trace_session()
