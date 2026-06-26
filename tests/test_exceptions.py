"""Tests for core.exceptions — hierarchy, attributes, __all__."""

import pytest


class TestExceptionHierarchy:
    """All custom exceptions inherit from CruxError."""

    def test_base_is_exception(self):
        from core.exceptions import CruxError

        assert issubclass(CruxError, Exception)

    def test_infrastructure_subclasses(self):
        from core.exceptions import (
            ConfigError,
            CruxError,
            EncodingError,
            NetworkError,
            ProviderError,
        )

        for cls in (ConfigError, ProviderError, NetworkError, EncodingError):
            assert issubclass(cls, CruxError)

    def test_tool_subclasses(self):
        from core.exceptions import (
            CruxError,
            EngineError,
            GenerationError,
            ToolError,
            ToolTimeoutError,
        )

        assert issubclass(ToolError, CruxError)
        assert issubclass(ToolTimeoutError, ToolError)
        assert issubclass(EngineError, CruxError)
        assert issubclass(GenerationError, EngineError)

    def test_agent_subclasses(self):
        from core.exceptions import AgentError, CruxError, MessageError, SessionError

        for cls in (AgentError, SessionError, MessageError):
            assert issubclass(cls, CruxError)

    def test_self_subclasses(self):
        from core.exceptions import AuditError, CruxError, EvolutionError, FixError

        for cls in (AuditError, EvolutionError, FixError):
            assert issubclass(cls, CruxError)

    def test_skill_subclasses(self):
        from core.exceptions import CruxError, MarketplaceError, SkillError

        assert issubclass(SkillError, CruxError)
        assert issubclass(MarketplaceError, CruxError)

    def test_security_subclasses(self):
        from core.exceptions import CruxError, SandboxError, SecurityError

        assert issubclass(SandboxError, CruxError)
        assert issubclass(SecurityError, CruxError)


class TestExceptionAttributes:
    """CruxError carries optional code and message."""

    def test_message_only(self):
        from core.exceptions import CruxError

        e = CruxError("something broke")
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
        from core.exceptions import CruxError

        e = CruxError()
        assert str(e) == ""
        assert e.message == ""

    def test_catch_by_base(self):
        from core.exceptions import CruxError, ToolError

        with pytest.raises(CruxError):
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
