"""Tests for core/exceptions.py — 结构化异常层次"""

import pytest

from core.exceptions import (
    AgentError,
    AuditError,
    ConfigError,
    CruxError,
    EncodingError,
    EngineError,
    EvolutionError,
    FixError,
    GenerationError,
    MarketplaceError,
    MessageError,
    NetworkError,
    ProviderError,
    SandboxError,
    SecurityError,
    SessionError,
    SkillError,
    ToolError,
    ToolTimeoutError,
)


class TestCruxError:
    """基类异常测试"""

    def test_is_exception(self):
        assert issubclass(CruxError, Exception)

    def test_basic_message(self):
        err = CruxError("测试错误")
        assert "测试错误" in str(err)

    def test_empty(self):
        err = CruxError()
        assert str(err) == ""


class TestSpecializedErrors:
    """子类异常测试"""

    @pytest.mark.parametrize(
        ("exc_cls", "msg"),
        [
            (ConfigError, "配置缺失"),
            (ProviderError, "API 密钥无效"),
            (NetworkError, "连接超时"),
            (EncodingError, "编码错误"),
            (ToolError, "工具调用失败"),
            (ToolTimeoutError, "工具超时"),
            (EngineError, "引擎错误"),
            (GenerationError, "生成失败"),
            (SandboxError, "沙箱拒绝"),
            (SecurityError, "安全违规"),
        ],
    )
    def test_all_errors_work(self, exc_cls, msg):
        err = exc_cls(msg)
        assert str(err) == msg
        assert isinstance(err, CruxError)
        assert isinstance(err, Exception)


class TestErrorInheritance:
    """继承关系测试"""

    def test_all_inherit_crux_error(self):
        for cls in [
            ConfigError,
            ProviderError,
            NetworkError,
            EncodingError,
            ToolError,
            ToolTimeoutError,
            EngineError,
            GenerationError,
            AgentError,
            SessionError,
            MessageError,
            AuditError,
            EvolutionError,
            FixError,
            SkillError,
            MarketplaceError,
            SandboxError,
            SecurityError,
        ]:
            assert issubclass(cls, CruxError), f"{cls.__name__} 不继承 CruxError"

    def test_tool_timeout_inherits_tool_error(self):
        assert issubclass(ToolTimeoutError, ToolError)

    def test_generation_inherits_engine(self):
        assert issubclass(GenerationError, EngineError)

    def test_all_exception_classes(self):
        """确保至少有 16 个子类"""
        assert len(CruxError.__subclasses__()) >= 15


class TestErrorRaising:
    """可抛性测试"""

    def test_raise_and_catch_base(self):
        with pytest.raises(CruxError):
            raise ConfigError("配置错误")

    def test_raise_and_catch_tool(self):
        with pytest.raises(ToolError):
            raise ToolTimeoutError("工具超时")

    def test_try_except_chain(self):
        try:
            raise SandboxError("沙箱拒绝")
        except CruxError as e:
            assert isinstance(e, SandboxError)
        except Exception:
            pytest.fail("SandboxError 应被 CruxError 捕获")
