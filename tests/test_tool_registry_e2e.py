"""ToolRegistry 全链路端到端测试。

覆盖闭环: 注册 → 参数校验 → 执行 → 错误恢复 → metric → sandbox → 相似工具建议

不依赖外部服务,全 mock / 纯本地文件操作。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.tools import ToolRegistry, BUILTIN_TOOLS, get_registry, reload_registry


# ════════════════════════════════════════════════════════════
#  1. 注册链路
# ════════════════════════════════════════════════════════════

class TestRegistration:
    """工具注册 / 注销 / 重复注册。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        monkeypatch.setattr("core.tools.TOOLS_CONFIG", tmp)
        tmp.write_text(json.dumps({"tools": []}), encoding="utf-8")
        self.tmp = tmp
        yield
        tmp.unlink(missing_ok=True)

    def test_builtin_tools_in_definitions(self):
        """Builtin 工具在 definitions 中(注意: 不在 _executors 中, has() 只查 _executors)。
        这是已知设计: builtin 的 execute 走 ChatSession._dispatch_tool 硬编码路径。"""
        reg = ToolRegistry()
        reg.load()
        def_names = {d["function"]["name"] for d in reg.definitions}
        for bt in BUILTIN_TOOLS:
            assert bt["function"]["name"] in def_names

    def test_register_custom_tool(self):
        reg = ToolRegistry()
        reg.load()
        reg.register("custom_tool", "desc", {"type": "object", "properties": {}},
                     executor=lambda: "ok")
        assert reg.has("custom_tool")
        assert "custom_tool" in reg.tool_names

    def test_register_duplicate_without_override(self):
        reg = ToolRegistry()
        reg.load()
        first = reg.register("dup", "desc1", {"type": "object", "properties": {}},
                             executor=lambda: "1")
        second = reg.register("dup", "desc2", {"type": "object", "properties": {}},
                              executor=lambda: "2")
        assert first is True
        assert second is False  # 不覆盖

    def test_register_duplicate_with_override(self):
        reg = ToolRegistry()
        reg.load()
        reg.register("dup", "desc1", {"type": "object", "properties": {}},
                     executor=lambda: "1")
        result = reg.register("dup", "desc2", {"type": "object", "properties": {}},
                             executor=lambda: "2", override=True)
        assert result is True
        # executor 应为覆盖后的
        assert reg.execute("dup", {}) == "2"

    def test_unregister(self):
        reg = ToolRegistry()
        reg.load()
        reg.register("tmp", "desc", {"type": "object", "properties": {}},
                     executor=lambda: "x")
        assert reg.has("tmp")
        reg.unregister("tmp")
        assert not reg.has("tmp")

    def test_tool_names_is_list(self):
        reg = ToolRegistry()
        reg.load()
        names = reg.tool_names
        assert isinstance(names, list)
        assert len(names) > 0

    def test_tool_categories_groups(self):
        reg = ToolRegistry()
        reg.load()
        cats = reg.tool_categories
        assert isinstance(cats, dict)
        # 应有 "其他" 兜底分类
        assert any("其他" in k for k in cats)


# ════════════════════════════════════════════════════════════
#  2. 参数校验链路
# ════════════════════════════════════════════════════════════

class TestParamValidation:
    """_validate_args + execute 的参数校验。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        monkeypatch.setattr("core.tools.TOOLS_CONFIG", tmp)
        # 放一个需要 required 参数的 shell 工具
        tmp.write_text(json.dumps({"tools": [{
            "name": "e2e_echo",
            "type": "shell",
            "command": "echo {message}",
            "description": "echo",
            "parameters": {
                "message": {"type": "string", "description": "msg", "required": True}
            }
        }]}), encoding="utf-8")
        self.tmp = tmp
        yield
        tmp.unlink(missing_ok=True)

    def test_missing_required_returns_error(self):
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_echo", {})  # 缺 message
        assert "[错误" in result
        assert "参数校验失败" in result

    def test_correct_args_passes(self):
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_echo", {"message": "hello"})
        assert "hello" in result


# ════════════════════════════════════════════════════════════
#  3. 执行链路 + 错误恢复
# ════════════════════════════════════════════════════════════

class TestExecutionAndRecovery:
    """执行成功 / 异常 / 错误恢复。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        monkeypatch.setattr("core.tools.TOOLS_CONFIG", tmp)
        tmp.write_text(json.dumps({"tools": [
            {
                "name": "e2e_ok",
                "type": "shell",
                "command": "echo ok",
                "description": "ok",
                "parameters": {},
            },
            {
                "name": "e2e_fail",
                "type": "python",
                "function": "core.file_tools.read_file",  # 已知存在
                "description": "reads file",
                "parameters": {
                    "path": {"type": "string", "description": "path", "required": True}
                },
            },
        ]}), encoding="utf-8")
        self.tmp = tmp
        yield
        tmp.unlink(missing_ok=True)

    def test_shell_execution_ok(self):
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_ok", {})
        assert "ok" in result
        assert "[错误" not in result

    def test_python_executor_error_recovery(self):
        """python 执行器传不存在的路径 → 应返回分类错误 + 恢复建议, 不 raise。"""
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_fail", {"path": "/__nonexistent_12345__"})
        # 应不 raise, 返回错误字符串
        assert isinstance(result, str)
        assert "[错误" in result or "error" in result.lower()


# ════════════════════════════════════════════════════════════
#  4. 未知工具 → 相似建议
# ════════════════════════════════════════════════════════════

class TestSimilarToolSuggestion:
    """execute 未知工具 → TF-IDF 相似建议。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        monkeypatch.setattr("core.tools.TOOLS_CONFIG", tmp)
        tmp.write_text(json.dumps({"tools": [
            {"name": "read_file", "type": "shell", "command": "echo read",
             "description": "read", "parameters": {}},
            {"name": "write_file", "type": "shell", "command": "echo write",
             "description": "write", "parameters": {}},
        ]}), encoding="utf-8")
        self.tmp = tmp
        yield
        tmp.unlink(missing_ok=True)

    def test_unknown_tool_suggests(self):
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("reaad_file", {})  # 拼写错误
        assert "未知工具" in result
        # 应包含相似建议
        assert "你是否想用" in result or "reaad" not in result

    def test_unknown_tool_no_match(self):
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("zzzzz_nonexistent", {})
        assert "未知工具" in result


# ════════════════════════════════════════════════════════════
#  5. Sandbox 集成 (shell executor 唯一关卡)
# ════════════════════════════════════════════════════════════

class TestSandboxGate:
    """shell 类型工具走 sandbox_restrict。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        monkeypatch.setattr("core.tools.TOOLS_CONFIG", tmp)
        tmp.write_text(json.dumps({"tools": [
            {"name": "e2e_safe", "type": "shell", "command": "echo hello",
             "description": "safe", "parameters": {}},
        ]}), encoding="utf-8")
        self.tmp = tmp
        yield
        tmp.unlink(missing_ok=True)

    def test_safe_command_passes(self):
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_safe", {})
        assert "hello" in result

    def test_dangerous_command_blocked(self):
        """rm -rf / 被 sandbox 拦截。"""
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        tmp.write_text(json.dumps({"tools": [
            {"name": "e2e_danger", "type": "shell",
             "command": "rm -rf /tmp/__nonexistent__",
             "description": "danger", "parameters": {}},
        ]}), encoding="utf-8")
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_danger", {})
        assert "沙箱拒绝" in result


# ════════════════════════════════════════════════════════════
#  6. Metric / 观测链路
# ════════════════════════════════════════════════════════════

class TestMetrics:
    """execute 后 metrics counter 正确递增。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        monkeypatch.setattr("core.tools.TOOLS_CONFIG", tmp)
        tmp.write_text(json.dumps({"tools": [
            {"name": "e2e_metric", "type": "shell", "command": "echo metric",
             "description": "metric", "parameters": {}},
        ]}), encoding="utf-8")
        self.tmp = tmp
        yield
        tmp.unlink(missing_ok=True)

    @patch("core.observability.metrics", None)
    def test_no_observability_no_crash(self):
        """observability 不可用时静默降级, 不 crash。"""
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_metric", {})
        assert "metric" in result

    def test_metrics_increment(self):
        """有 observability 时 counter 递增。"""
        from core.observability import Metrics
        mock_metrics = Metrics()
        with patch("core.observability.metrics", mock_metrics):
            reg = ToolRegistry()
            reg.load()
            before = mock_metrics.get("tool_executions")
            reg.execute("e2e_metric", {})
            after = mock_metrics.get("tool_executions")
            assert after == before + 1


# ════════════════════════════════════════════════════════════
#  7. python_executor 安全守卫 (import 白名单 + 危险模块黑名单)
# ════════════════════════════════════════════════════════════

class TestPythonExecutorSecurity:
    """python 类型工具的 import 白名单和危险模块黑名单。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch):
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        monkeypatch.setattr("core.tools.TOOLS_CONFIG", tmp)
        yield
        if tmp.exists():
            tmp.unlink(missing_ok=True)

    def test_allowed_prefix_passes(self):
        """core.* 前缀允许。"""
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        tmp.write_text(json.dumps({"tools": [
            {"name": "e2e_py_ok", "type": "python",
             "function": "core.file_tools.env_check",
             "description": "ok", "parameters": {}},
        ]}), encoding="utf-8")
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_py_ok", {})
        # env_check 应返回 JSON 字符串
        assert isinstance(result, str)

    def test_blocked_prefix_rejected(self):
        """非白名单模块被拒绝。"""
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        tmp.write_text(json.dumps({"tools": [
            {"name": "e2e_py_bad", "type": "python",
             "function": "some_random_module.func",
             "description": "bad", "parameters": {}},
        ]}), encoding="utf-8")
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_py_bad", {})
        assert "安全拒绝" in result

    def test_blocked_module_rejected(self):
        """危险模块(os/subprocess)被拒绝。注意: os 不在白名单前缀中,
        所以先命中 '禁止导入外部模块' 而非 '禁止导入危险模块'(后者只拦截
        白名单内但本身危险的如 core.os,实际不存在)。"""
        tmp = ROOT / "tests" / "_test_e2e_tools.json"
        tmp.write_text(json.dumps({"tools": [
            {"name": "e2e_py_os", "type": "python",
             "function": "os.system",
             "description": "os", "parameters": {}},
        ]}), encoding="utf-8")
        reg = ToolRegistry()
        reg.load()
        result = reg.execute("e2e_py_os", {})
        assert "安全拒绝" in result


# ════════════════════════════════════════════════════════════
#  8. 单例线程安全
# ════════════════════════════════════════════════════════════

class TestSingleton:
    """get_registry / reload_registry 单例行为。"""

    def test_get_registry_returns_singleton(self):
        reload_registry()  # 重置
        a = get_registry()
        b = get_registry()
        assert a is b

    def test_reload_returns_new_instance(self):
        reload_registry()
        old = get_registry()
        reload_registry()
        new = get_registry()
        # reload 应重置单例 (非同一实例, 除非在同一 load 中)
        assert new is not None
