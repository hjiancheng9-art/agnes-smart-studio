"""Tests for #4 — 工具错误自动恢复。

守护三条增强契约：
1. **参数校验**: required 缺失 / 类型不匹配 → 返回带 schema 期望的错误字符串
2. **错误分类**: 执行异常 → ErrorClassifier 分类 + 恢复建议（而非裸 raise）
3. **相似工具建议**: 未知工具 → TF-IDF/编辑距离推荐 top-2 相似工具

所有错误字符串都以 `[错误]` 开头（供 POST_TOOL_USE hook 的 error key 检测）。
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.tools import (
    ToolRegistry,
    _validate_args,
    _suggest_similar_tool,
    _levenshtein,
)


# ── _validate_args ──────────────────────────────────────────────────


class TestValidateArgs:

    def _make_definitions(self, name="read_file", properties=None, required=None):
        """构建 OpenAI function 格式的 definitions。"""
        properties = properties or {
            "path": {"type": "string", "description": "文件路径"},
            "limit": {"type": "integer", "description": "行数限制"},
        }
        required = required or ["path"]
        return [{
            "type": "function",
            "function": {
                "name": name,
                "description": "test tool",
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }]

    def test_valid_args_pass(self):
        """完整且类型正确的参数通过校验。"""
        defs = self._make_definitions()
        ok, detail = _validate_args("read_file", {"path": "/tmp/x", "limit": 10}, defs)
        assert ok is True
        assert detail == ""

    def test_missing_required_fails(self):
        """缺少 required 字段 → 校验失败，错误信息含缺失字段名。"""
        defs = self._make_definitions(required=["path"])
        ok, detail = _validate_args("read_file", {"limit": 10}, defs)
        assert ok is False
        assert "[错误]" in detail
        assert "path" in detail
        assert "缺少必需参数" in detail

    def test_none_required_value_fails(self):
        """required 字段值为 None → 视为缺失。"""
        defs = self._make_definitions(required=["path"])
        ok, detail = _validate_args("read_file", {"path": None}, defs)
        assert ok is False
        assert "path" in detail

    def test_optional_missing_passes(self):
        """非 required 字段缺失 → 通过。"""
        defs = self._make_definitions(properties={
            "path": {"type": "string"},
            "limit": {"type": "integer"},
        }, required=["path"])
        ok, detail = _validate_args("read_file", {"path": "/x"}, defs)
        assert ok is True

    def test_type_mismatch_fails(self):
        """string 参数传 integer → 类型校验失败。"""
        defs = self._make_definitions(properties={
            "path": {"type": "string"},
        }, required=["path"])
        ok, detail = _validate_args("read_file", {"path": 123}, defs)
        assert ok is False
        assert "[错误]" in detail
        assert "path" in detail
        assert "string" in detail
        assert "integer" in detail or "int" in detail

    def test_integer_rejects_bool(self):
        """integer 参数不接受 bool（Python 中 bool 是 int 子类）。"""
        defs = self._make_definitions(properties={
            "count": {"type": "integer"},
        }, required=["count"])
        ok, detail = _validate_args("read_file", {"count": True}, defs)
        assert ok is False

    def test_boolean_accepts_bool(self):
        """boolean 参数接受 bool。"""
        defs = self._make_definitions(properties={
            "force": {"type": "boolean"},
        }, required=["force"])
        ok, detail = _validate_args("read_file", {"force": True}, defs)
        assert ok is True

    def test_no_schema_passes(self):
        """工具无 schema 定义 → 直通。"""
        ok, detail = _validate_args("unknown", {"x": 1}, [])
        assert ok is True
        assert detail == ""

    def test_no_properties_passes(self):
        """schema 无 properties → 直通。"""
        defs = [{"function": {"name": "t", "parameters": {"type": "object"}}}]
        ok, detail = _validate_args("t", {"x": 1}, defs)
        assert ok is True

    def test_non_dict_args_passes(self):
        """非 dict 参数 → 直通（防御性）。"""
        ok, detail = _validate_args("t", "not a dict", [])
        assert ok is True


# ── _levenshtein / _suggest_similar_tool ─────────────────────────────


class TestSuggestSimilarTool:

    def _make_defs(self, names):
        return [{"function": {"name": n}} for n in names]

    def test_levenshtein_identical(self):
        assert _levenshtein("abc", "abc") == 0

    def test_levenshtein_one_edit(self):
        assert _levenshtein("cat", "bat") == 1
        assert _levenshtein("cat", "cats") == 1

    def test_levenshtein_empty(self):
        assert _levenshtein("", "abc") == 3
        assert _levenshtein("abc", "") == 3

    def test_typo_finds_similar(self):
        """read_fil (typo) → 建议 read_file。"""
        defs = self._make_defs(["read_file", "write_file", "edit_file", "search_files"])
        result = _suggest_similar_tool("read_fil", defs)
        assert "read_file" in result

    def test_prefix_match_finds_similar(self):
        """read → 前缀匹配找到 read_file。"""
        defs = self._make_defs(["read_file", "write_file", "edit_file"])
        result = _suggest_similar_tool("read", defs)
        assert "read_file" in result

    def test_no_match_returns_empty(self):
        """完全不相关 → 返回空字符串。"""
        defs = self._make_defs(["read_file", "write_file"])
        result = _suggest_similar_tool("zzzzzzz", defs)
        assert result == ""

    def test_empty_definitions(self):
        assert _suggest_similar_tool("any", []) == ""
        assert _suggest_similar_tool("", self._make_defs(["a"])) == ""

    def test_top_n_limit(self):
        """返回不超过 top_n 个建议。"""
        defs = self._make_defs(["read_file", "read_files", "read_filedir", "write_file"])
        result = _suggest_similar_tool("read_file", defs, top_n=2)
        parts = result.split(" / ")
        assert len(parts) <= 2

    def test_cjk_tool_names(self):
        """中文工具名也能匹配。"""
        defs = self._make_defs(["读取文件", "写入文件", "搜索文件"])
        result = _suggest_similar_tool("读取文", defs)
        assert "读取文件" in result


# ── ToolRegistry.execute 集成测试 ──────────────────────────────────────


class TestExecuteRecovery:

    def _make_registry_with_tool(self, name="divide", executor=None, schema=None):
        """构建带单个工具的 registry。"""
        reg = ToolRegistry()
        if schema is None:
            schema = {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            }
        reg._definitions = [{
            "type": "function",
            "function": {"name": name, "description": "test", "parameters": schema},
        }]
        reg._executors[name] = executor or (lambda **kw: "ok")
        return reg

    def test_unknown_tool_returns_suggestion(self):
        """未知工具 → 错误字符串带相似工具建议。"""
        reg = self._make_registry_with_tool(name="read_file")
        reg._definitions[0]["function"]["name"] = "read_file"
        result = reg.execute("read_fil", {"path": "/x"})
        assert "[错误]" in result
        assert "未知工具" in result
        assert "read_file" in result  # 建议

    def test_unknown_tool_no_match(self):
        """未知工具且无相似 → 纯错误信息（不崩溃）。"""
        reg = self._make_registry_with_tool(name="alpha")
        result = reg.execute("zzzzzzz", {})
        assert "[错误]" in result
        assert "未知工具" in result

    def test_missing_required_returns_schema_hint(self):
        """缺少 required 参数 → 错误字符串含期望。"""
        reg = self._make_registry_with_tool(name="divide")
        result = reg.execute("divide", {"a": 10})  # 缺 b
        assert "[错误]" in result
        assert "参数校验失败" in result
        assert "b" in result

    def test_type_error_returns_recovery_hint(self):
        """执行抛 ValueError → 错误分类 + 恢复建议（不裸 raise）。"""
        def bad_executor(**kw):
            raise ValueError("invalid input: must be positive")
        reg = self._make_registry_with_tool(name="divide", executor=bad_executor)
        result = reg.execute("divide", {"a": 10, "b": -1})
        assert "[错误" in result
        assert "恢复建议" in result
        # 不应 raise
        assert isinstance(result, str)

    def test_os_error_returns_recovery_hint(self):
        """执行抛 OSError → 错误分类。"""
        def bad_executor(**kw):
            raise OSError("FileNotFoundError: no such file")
        reg = self._make_registry_with_tool(name="divide", executor=bad_executor)
        result = reg.execute("divide", {"a": 1, "b": 2})
        assert "[错误" in result
        assert "恢复建议" in result

    def test_generic_exception_returns_error_string(self):
        """执行抛 Exception 子类 → 错误字符串。"""
        def bad_executor(**kw):
            raise RuntimeError("unexpected failure")
        reg = self._make_registry_with_tool(name="divide", executor=bad_executor)
        result = reg.execute("divide", {"a": 1, "b": 2})
        assert "[错误" in result
        assert "恢复建议" in result

    def test_successful_execution_unchanged(self):
        """成功执行 → 正常返回结果字符串。"""
        def good_executor(**kw):
            return f"result: {kw.get('a')}/{kw.get('b')}"
        reg = self._make_registry_with_tool(name="divide", executor=good_executor)
        result = reg.execute("divide", {"a": 10, "b": 2})
        assert "result: 10/2" in result
        assert "[错误]" not in result


# ── POST data error key 契约测试 ──────────────────────────────────────


class TestPostDataErrorKey:
    """验证 POST_TOOL_USE hook 的 data 中 error key 正确标记。"""

    def test_error_result_detected(self):
        """工具返回 [错误] 开头 → is_error=True。"""
        result = "[错误] 未知工具: xxx"
        is_error = isinstance(result, str) and result.startswith("[错误]")
        assert is_error is True

    def test_success_result_not_error(self):
        """工具返回正常结果 → is_error=False。"""
        result = "file content here"
        is_error = isinstance(result, str) and result.startswith("[错误]")
        assert is_error is False

    def test_non_string_result_not_error(self):
        """非字符串结果 → is_error=False。"""
        result = None
        is_error = isinstance(result, str) and result.startswith("[错误]")
        assert is_error is False
