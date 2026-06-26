"""Unit tests for core/self_tool.py — 工具验证逻辑。

self_tool.py 的 create_tool 有多层验证（名称/语言/参数JSON/语法检查），
这些验证步骤在写文件/动态 import 之前，可通过 mock registry 和 monkeypatch
CUSTOM_TOOLS_DIR 来隔离测试。

覆盖：
- 名称校验（_NAME_RE 正则：数字开头、空格、连字符被拒）
- 参数 JSON 字符串解析 + 格式错误
- 语言检查（非 Python 被拒）
- 语法检查（compile 报错）
- 完整创建流程（名称唯一 + 语法合法 → 写文件 + 动态 import → 注册成功）
- 工具定义与执行器映射

⚠ list_custom_tools / delete_tool 需要真实文件系统 + registry unregister，
用 tmp_path + mock registry 做有限覆盖。
"""
# pyright: reportArgumentType=false

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.self_tool import (
    _NAME_RE,
    SELF_TOOL_EXECUTOR_MAP,
    SELF_TOOL_TOOL_DEFS,
    ToolBuilder,
)

# ── _NAME_RE 正则 ──────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["my_tool", "_private", "tool123", "CamelCase", "_"])
def test_name_re_accepts_valid(name):
    """合法名称应通过正则。"""
    assert _NAME_RE.match(name) is not None


@pytest.mark.parametrize("name", ["1tool", "-tool", "my tool", "my-tool", "tool.name", ""])
def test_name_re_rejects_invalid(name):
    """非法名称应被拒绝。"""
    assert _NAME_RE.match(name) is None


# ── ToolBuilder: 验证层（不触及文件系统） ────────────────────────


def _mock_registry(tool_names=None, has_result=True):
    """构造一个最小 mock registry。"""
    reg = MagicMock()
    reg.tool_names = tool_names or []
    reg.has.return_value = has_result
    return reg


def test_create_tool_rejects_empty_name():
    """空名称应被拒绝。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    result = builder.create_tool("", "desc", {}, "pass")
    assert result["success"] is False
    assert "Invalid tool name" in result["error"]


def test_create_tool_rejects_name_starting_with_digit():
    """数字开头的名称应被拒绝。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    result = builder.create_tool("1tool", "desc", {}, "pass")
    assert result["success"] is False
    assert "Invalid tool name" in result["error"]


def test_create_tool_rejects_name_with_hyphen():
    """含连字符的名称应被拒绝。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    result = builder.create_tool("my-tool", "desc", {}, "pass")
    assert result["success"] is False
    assert "Invalid tool name" in result["error"]


def test_create_tool_rejects_duplicate_name():
    """已存在的名称应被拒绝（冲突检测）。"""
    reg = _mock_registry(tool_names=["existing_tool"])
    builder = ToolBuilder(reg)
    result = builder.create_tool("existing_tool", "desc", {}, "pass")
    assert result["success"] is False
    assert "already exists" in result["error"]


def test_create_tool_rejects_non_python_language():
    """非 Python 语言应被拒绝。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    result = builder.create_tool("valid_name", "desc", {}, "pass", language="javascript")
    assert result["success"] is False
    assert "Unsupported language" in result["error"]
    assert "javascript" in result["error"]


def test_create_tool_rejects_invalid_parameters_json_string():
    """参数 JSON 字符串格式错误时应被拒绝。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    result = builder.create_tool("valid_name", "desc", "{not valid json}", "pass")
    assert result["success"] is False
    assert "Invalid parameters JSON" in result["error"]


def test_create_tool_rejects_non_dict_parameters():
    """参数不是 dict（如传了 list）应被拒绝。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    result = builder.create_tool("valid_name", "desc", ["not", "a", "dict"], "pass")
    assert result["success"] is False
    assert "JSON schema object" in result["error"]


def test_create_tool_rejects_syntax_error_in_code():
    """源码有语法错误时应被拒绝（compile 阶段）。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    result = builder.create_tool(
        "valid_name",
        "desc",
        {},
        "def valid_name(**kwargs):\n    return 0 /",  # 不完整语句
    )
    assert result["success"] is False
    assert "Syntax error" in result["error"]


def test_create_tool_accepts_valid_parameters_dict():
    """参数为合法 dict 时应通过参数验证（后续可能因文件/注册失败）。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    # 语法合法但函数名不匹配 → 会在动态 import 阶段失败（Function not found）
    result = builder.create_tool(
        "valid_name",
        "desc",
        {"type": "object", "properties": {"x": {"type": "number"}}},
        "return x",  # 语法合法
    )
    # 应通过名称/语言/参数/语法校验，失败发生在后续步骤
    # （可能是 Function not found 或写入/导入）
    if not result["success"]:
        assert "Invalid tool name" not in result["error"]
        assert "Unsupported language" not in result["error"]
        assert "Invalid parameters JSON" not in result["error"]
        assert "Syntax error" not in result["error"]


# ── 完整创建流程（tmp_path + mock registry） ─────────────────────


def test_create_tool_full_flow(tmp_path, monkeypatch):
    """合法工具应：写文件 → 动态 import → 注册成功。

    需要 tmp_path 作为 CUSTOM_TOOLS_DIR，mock registry 能注册。
    """
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)
    # 确保 custom_dir 的 parent 在 sys.path（动态 import 需要）
    monkeypatch.setattr("core.self_tool.OUTPUT_DIR", tmp_path)

    reg = MagicMock()
    reg.tool_names = []
    reg.has.return_value = False
    reg.register = MagicMock()  # 接收任何调用

    builder = ToolBuilder(reg)
    result = builder.create_tool(
        "echo_x",
        "Echo the x parameter",
        {"type": "object", "properties": {"x": {"type": "string"}}},
        'return kwargs.get("x", "")',
    )
    assert result["success"] is True, f"Expected success but got: {result}"
    assert result["tool_name"] == "echo_x"
    # 文件应已写入
    assert (custom_dir / "echo_x.py").exists()
    # register 应被调用
    reg.register.assert_called_once()


def test_create_tool_write_failure_returns_error(tmp_path, monkeypatch):
    """工具文件写入失败（如权限问题）时应返回错误。

    通过 monkeypatch CUSTOM_TOOLS_DIR 为一个不存在的深层路径来模拟写入失败。
    """
    # 一个不存在的深层路径（mkdir 不会自动创建）
    impossible = tmp_path / "a" / "b" / "c" / "custom_tools"
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", impossible)

    reg = MagicMock()
    reg.tool_names = []
    reg.register = MagicMock()

    builder = ToolBuilder(reg)
    result = builder.create_tool(
        "fail_tool",
        "desc",
        {},
        "return 1",
    )
    assert result["success"] is False
    assert "Failed to write" in result["error"]


# ── list_custom_tools ──────────────────────────────────────────────


def test_list_custom_tools_empty_dir(tmp_path, monkeypatch):
    """空目录返回空列表。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    reg = _mock_registry()
    builder = ToolBuilder(reg)
    tools = builder.list_custom_tools()
    assert tools == []


def test_list_custom_tools_discovers_files(tmp_path, monkeypatch):
    """应发现 .py 文件（跳过 _ 开头）并提取描述。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    (custom_dir / "good_tool.py").write_text(
        "# Auto-generated custom tool: good_tool\n# A useful description\ndef good_tool(**kwargs):\n    pass\n",
        encoding="utf-8",
    )
    (custom_dir / "_private.py").write_text("# skip me\ndef _private():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    reg = _mock_registry()
    builder = ToolBuilder(reg)
    tools = builder.list_custom_tools()
    names = [t["name"] for t in tools]
    assert "good_tool" in names
    assert "_private" not in names  # _ 开头跳过


# ── delete_tool ────────────────────────────────────────────────────


def test_delete_tool_removes_file(tmp_path, monkeypatch):
    """delete_tool 应删除文件并从 registry 注销。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    tool_file = custom_dir / "delme.py"
    tool_file.write_text("def delme(**kwargs):\n    pass\n", encoding="utf-8")
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    reg = MagicMock()
    reg.unregister.return_value = True

    builder = ToolBuilder(reg)
    result = builder.delete_tool("delme")
    assert result is True
    reg.unregister.assert_called_once_with("delme")
    assert not tool_file.exists()


def test_delete_tool_nonexistent_returns_false(tmp_path, monkeypatch):
    """删除不存在的工具应返回 False。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    reg = MagicMock()
    reg.unregister.return_value = False
    builder = ToolBuilder(reg)
    result = builder.delete_tool("ghost")
    assert result is False


# ── 工具定义与执行器映射 ──────────────────────────────────────────


def test_tool_defs_well_formed():
    """TOOL_DEFS 应是 function 工具定义列表。"""
    assert isinstance(SELF_TOOL_TOOL_DEFS, list)
    for td in SELF_TOOL_TOOL_DEFS:
        assert td["type"] == "function"
        assert "name" in td["function"]


def test_executor_map_keys_match_tool_def_names():
    """EXECUTOR_MAP key 应与 TOOL_DEFS function.name 一致。"""
    def_names = {td["function"]["name"] for td in SELF_TOOL_TOOL_DEFS}
    assert set(SELF_TOOL_EXECUTOR_MAP.keys()) == def_names


def test_executor_create_tool_returns_json_string():
    """_exec_create_tool 应返回可解析的 JSON 字符串。"""
    fn = SELF_TOOL_EXECUTOR_MAP["create_tool"]
    # 名称非法 → 快速返回错误 JSON
    out = fn(name="", description="", parameters="{}", code="", language="python")
    data = json.loads(out)
    assert data["success"] is False


# ── 参数 JSON 字符串合法路径 ────────────────────────────────────


def test_create_tool_parses_valid_parameters_json_string():
    """参数为合法 JSON 字符串时应被解析为 dict。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    # 名称合法但后续会因动态 import 失败——只验证参数解析成功
    result = builder.create_tool(
        "my_tool",
        "desc",
        '{"type":"object","properties":{"x":{"type":"string"}}}',
        "return kwargs.get('x', '')",
    )
    # 不应因参数格式报错
    if not result["success"]:
        assert "Invalid parameters JSON" not in result["error"]


def test_create_tool_empty_parameters_dict_is_ok():
    """参数为空 dict（无参数工具）应通过验证。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    result = builder.create_tool(
        "no_params",
        "A tool with no parameters",
        {},
        "return 'hello'",
    )
    # 不应因参数报错
    if not result["success"]:
        assert "Parameters must be a JSON schema object" not in result["error"]
        assert "Invalid parameters JSON" not in result["error"]


# ── 完整流程：创建后实际调用 ────────────────────────────────────


def test_create_tool_full_flow_executable(tmp_path, monkeypatch):
    """创建的工具应能被动态 import 后实际调用并返回结果。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)
    monkeypatch.setattr("core.self_tool.OUTPUT_DIR", tmp_path)

    # 确保 parent 在 sys.path 中
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))

    registered_fn = None

    def capture_register(name, desc, params, fn, override=False):
        nonlocal registered_fn
        registered_fn = fn

    reg = MagicMock()
    reg.tool_names = []
    reg.has.return_value = False
    reg.register = capture_register

    builder = ToolBuilder(reg)
    result = builder.create_tool(
        "adder",
        "Add two numbers",
        {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
        "a = kwargs.get('a', 0)\nb = kwargs.get('b', 0)\nreturn a + b",
    )
    assert result["success"] is True

    # 验证注册的函数可以实际调用
    assert registered_fn is not None
    assert callable(registered_fn)
    assert registered_fn(a=3, b=4) == 7


# ── 动态 import 失败场景 ────────────────────────────────────────


def test_create_tool_function_not_found(tmp_path, monkeypatch):
    """生成的模块中找不到同名函数时应报错。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)
    monkeypatch.setattr("core.self_tool.OUTPUT_DIR", tmp_path)

    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))

    reg = MagicMock()
    reg.tool_names = []
    builder = ToolBuilder(reg)

    # 直接写入一个不含同名函数的 .py 文件
    # create_tool 会写入 def bad_name(**kwargs)... 但代码中 "pass" 不会生成函数名不匹配
    # 我们用 monkeypatch 让 write_text 写入不同内容来模拟
    original_write = Path.write_text

    def mock_write(self, content, **kw):
        # 替换内容：把函数名改成不同的
        content = content.replace("def wrong_func", "def wrong_func")
        # 写入一个没有正确函数名的文件
        content = "# Auto-generated\n\ndef completely_different(**kwargs):\n    pass\n"
        return original_write(self, content, **kw)

    with patch.object(Path, "write_text", mock_write):
        result = builder.create_tool(
            "wrong_func",
            "desc",
            {},
            "pass",
        )

    assert result["success"] is False
    assert "not found" in result["error"]


# ── list_custom_tools 细节 ──────────────────────────────────────


def test_list_custom_tools_extracts_description(tmp_path, monkeypatch):
    """应正确提取非 Auto-generated 注释行作为描述。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    (custom_dir / "my_tool.py").write_text(
        "# Auto-generated custom tool: my_tool\n"
        "# This is the real description\n"
        "def my_tool(**kwargs):\n"
        "    return kwargs\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    reg = _mock_registry()
    builder = ToolBuilder(reg)
    tools = builder.list_custom_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "my_tool"
    assert tools[0]["description"] == "This is the real description"


def test_list_custom_tools_no_description(tmp_path, monkeypatch):
    """没有注释行时描述应为空字符串。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    (custom_dir / "bare.py").write_text(
        "def bare(**kwargs):\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    reg = _mock_registry()
    builder = ToolBuilder(reg)
    tools = builder.list_custom_tools()
    assert len(tools) == 1
    assert tools[0]["description"] == ""


def test_list_custom_tools_registered_field(tmp_path, monkeypatch):
    """registered 字段应反映 registry.has 的结果。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    (custom_dir / "checker.py").write_text(
        "# Auto-generated custom tool: checker\n# check desc\ndef checker(**kwargs):\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    reg = _mock_registry(has_result=True)
    builder = ToolBuilder(reg)
    tools = builder.list_custom_tools()
    assert tools[0]["registered"] is True


# ── delete_tool 模块清理 ────────────────────────────────────────


def test_delete_tool_cleans_sys_modules(tmp_path, monkeypatch):
    """delete_tool 应清理 sys.modules 中对应的模块缓存。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    (custom_dir / "modtool.py").write_text(
        "def modtool(**kwargs):\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    # 预加载模块到 sys.modules
    module_name = "custom_tools.modtool"
    sys.modules[module_name] = __import__("os")  # dummy

    reg = MagicMock()
    reg.unregister.return_value = False
    builder = ToolBuilder(reg)
    builder.delete_tool("modtool")

    assert module_name not in sys.modules, f"{module_name} should be removed from sys.modules"


def test_delete_tool_file_deleted_regardless_of_unregister(tmp_path, monkeypatch):
    """即使 registry 注销失败（返回 False），文件也应被删除。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    tool_file = custom_dir / "fileonly.py"
    tool_file.write_text("def fileonly(**kwargs):\n    pass\n", encoding="utf-8")
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    reg = MagicMock()
    reg.unregister.return_value = False  # registry 中没有此工具
    builder = ToolBuilder(reg)
    result = builder.delete_tool("fileonly")
    # 文件存在过 → existed=True → 返回 True
    assert result is True
    assert not tool_file.exists()


# ── 语法错误信息 ───────────────────────────────────────────────


def test_create_tool_syntax_error_contains_details():
    """语法错误信息应包含具体的错误描述。"""
    reg = _mock_registry()
    builder = ToolBuilder(reg)
    result = builder.create_tool(
        "syn_err",
        "desc",
        {},
        "return 1 /",  # 不完整语句 → SyntaxError
    )
    assert result["success"] is False
    assert "Syntax error" in result["error"]
    # Python SyntaxError message 不为空
    assert "invalid syntax" in result["error"] or "unexpected EOF" in result["error"]


# ── executor 覆盖 ──────────────────────────────────────────────


def test_executor_list_custom_tools_returns_json(tmp_path, monkeypatch):
    """_exec_list_custom_tools 应返回 JSON 字符串。"""
    custom_dir = tmp_path / "custom_tools"
    custom_dir.mkdir()
    monkeypatch.setattr("core.self_tool.CUSTOM_TOOLS_DIR", custom_dir)

    fn = SELF_TOOL_EXECUTOR_MAP["list_custom_tools"]
    out = fn()
    data = json.loads(out)
    assert isinstance(data, list)


def test_executor_delete_tool_returns_json():
    """_exec_delete_tool 应返回 JSON 字符串。"""
    fn = SELF_TOOL_EXECUTOR_MAP["delete_tool"]
    out = fn(name="nonexistent")
    data = json.loads(out)
    assert "success" in data
    assert "tool_name" in data
