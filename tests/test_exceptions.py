"""Tests for core.exceptions — hierarchy, attributes, __all__."""

import pytest


class TestExceptionHierarchy:
    """All custom exceptions inherit from AgnesError."""

    def test_base_is_exception(self):
        from core.exceptions import AgnesError
        assert issubclass(AgnesError, Exception)

    def test_infrastructure_subclasses(self):
        from core.exceptions import (
            AgnesError, ConfigError, ProviderError, NetworkError, EncodingError,
        )
        for cls in (ConfigError, ProviderError, NetworkError, EncodingError):
            assert issubclass(cls, AgnesError)

    def test_tool_subclasses(self):
        from core.exceptions import (
            AgnesError, ToolError, ToolTimeoutError, EngineError, GenerationError,
        )
        assert issubclass(ToolError, AgnesError)
        assert issubclass(ToolTimeoutError, ToolError)
        assert issubclass(EngineError, AgnesError)
        assert issubclass(GenerationError, EngineError)

    def test_agent_subclasses(self):
        from core.exceptions import AgnesError, AgentError, SessionError, MessageError
        for cls in (AgentError, SessionError, MessageError):
            assert issubclass(cls, AgnesError)

    def test_self_subclasses(self):
        from core.exceptions import AgnesError, AuditError, EvolutionError, FixError
        for cls in (AuditError, EvolutionError, FixError):
            assert issubclass(cls, AgnesError)

    def test_skill_subclasses(self):
        from core.exceptions import AgnesError, SkillError, MarketplaceError
        assert issubclass(SkillError, AgnesError)
        assert issubclass(MarketplaceError, AgnesError)

    def test_security_subclasses(self):
        from core.exceptions import AgnesError, SandboxError, SecurityError
        assert issubclass(SandboxError, AgnesError)
        assert issubclass(SecurityError, AgnesError)


class TestExceptionAttributes:
    """AgnesError carries optional code and message."""

    def test_message_only(self):
        from core.exceptions import AgnesError
        e = AgnesError("something broke")
        assert str(e) == "something broke"
        assert e.message == "something broke"
        assert e.code is None

    def test_message_with_code(self):
        from core.exceptions import ToolError
        e = ToolError("ffmpeg not found", code="TOOL_MISSING")
        assert "[TOOL_MISSING]" in str(e)
        assert "ffmpeg not found" in str(e)
        assert e.code == "TOOL_MISSING"

    def test_subclass_inherits_code(self):
        from core.exceptions import ProviderError
        e = ProviderError("bad key", code="AUTH_FAIL")
        assert e.code == "AUTH_FAIL"
        assert isinstance(e, Exception)

    def test_empty_message(self):
        from core.exceptions import AgnesError
        e = AgnesError()
        assert str(e) == ""
        assert e.message == ""

    def test_catch_by_base(self):
        from core.exceptions import AgnesError, ToolError
        with pytest.raises(AgnesError):
            raise ToolError("boom")

    def test_catch_specific(self):
        from core.exceptions import GenerationError, ToolError
        with pytest.raises(GenerationError):
            raise GenerationError("img failed")
        # Does NOT catch as ToolError
        try:
            raise GenerationError("img failed")
        except ToolError:
            pytest.fail("GenerationError should not match ToolError")
        except GenerationError:
            pass  # expected


class TestAllExports:
    """__all__ is defined and contains all public names."""

    def test_all_defined(self):
        import core.exceptions as mod
        assert hasattr(mod, "__all__")
        assert len(mod.__all__) > 15

    def test_all_names_exist(self):
        import core.exceptions as mod
        for name in mod.__all__:
            assert hasattr(mod, name), f"__all__ lists {name!r} but it's missing"

    def test_all_are_exception_classes(self):
        import core.exceptions as mod
        for name in mod.__all__:
            obj = getattr(mod, name)
            assert isinstance(obj, type), f"{name!r} should be a class"
            assert issubclass(obj, Exception), f"{name!r} should be an Exception subclass"
