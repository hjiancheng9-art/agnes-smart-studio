"""Unit tests for core/codex_tools.py and core/codex_engines.py.

这两个模块通过 tools.json 动态加载（importlib.import_module），之前零测试。
覆盖：可导入性、纯函数行为、依赖缺失时的优雅降级。
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── 模块可导入性 ──────────────────────────────────────────────────────


class TestCodexToolsImportability:
    """所有通过 tools.json 注册的函数都能成功 import。"""

    @pytest.fixture(autouse=True)
    def _import_modules(self):
        import core.codex_tools as ct
        import core.codex_engines as ce
        self.ct = ct
        self.ce = ce

    def test_all_tools_json_functions_resolve(self):
        """tools.json 里引用的每个函数都必须是可调用的。"""
        tools_json = json.loads((ROOT / "tools.json").read_text(encoding="utf-8"))
        codex_funcs = []
        for tool in tools_json.get("tools", []):
            fn_path = tool.get("function", "")
            if fn_path.startswith("core.codex_tools.") or fn_path.startswith("core.codex_engines."):
                codex_funcs.append(fn_path)
        assert len(codex_funcs) > 0, "tools.json 应有 codex_tools/codex_engines 条目"

        for fn_path in codex_funcs:
            mod_path, func_name = fn_path.rsplit(".", 1)
            parts = mod_path.split(".")
            mod = sys.modules.get(mod_path)
            assert mod is not None, f"模块 {mod_path} 未 import"
            assert hasattr(mod, func_name), f"{fn_path} 中无 {func_name}"
            assert callable(getattr(mod, func_name)), f"{fn_path} 不是可调用对象"

    def test_codex_tools_all_exported(self):
        assert hasattr(self.ct, 'browser_screenshot')
        assert hasattr(self.ct, 'create_markdown')
        assert hasattr(self.ct, 'create_html')
        assert hasattr(self.ct, 'create_pdf')
        assert hasattr(self.ct, 'text_to_speech')
        assert hasattr(self.ct, 'desktop_screenshot')
        assert hasattr(self.ct, 'deploy_vercel')
        assert hasattr(self.ct, 'deploy_netlify')
        assert hasattr(self.ct, 'browser_fetch')

    def test_codex_engines_all_exported(self):
        assert hasattr(self.ce, 'js_eval')
        assert hasattr(self.ce, 'mcp_connect')
        assert hasattr(self.ce, 'mcp_call')
        assert hasattr(self.ce, 'pw_navigate')
        assert hasattr(self.ce, 'pw_screenshot')
        assert hasattr(self.ce, 'pw_click')
        assert hasattr(self.ce, 'pw_fill')
        assert hasattr(self.ce, 'pw_js')
        assert hasattr(self.ce, 'pw_close')
        assert hasattr(self.ce, 'transcribe_audio')
        assert hasattr(self.ce, 'imagegen')


# ── create_markdown / create_html（纯函数）────────────────────────────


class TestCreateMarkdown:
    """create_markdown: 写 .md 文件。"""

    def test_creates_file_with_content(self, tmp_path):
        with patch.object(self._get_ct_module(), 'ROOT', tmp_path):
            from core.codex_tools import create_markdown
            out = create_markdown("Test Doc", "Hello World")
            assert Path(out).exists()
            content = Path(out).read_text(encoding="utf-8")
            assert "# Test Doc" in content
            assert "Hello World" in content

    def test_sanitizes_title_in_filename(self, tmp_path):
        with patch.object(self._get_ct_module(), 'ROOT', tmp_path):
            from core.codex_tools import create_markdown
            out = create_markdown("My Great Title", "content")
            assert "My_Great_Title.md" in out

    def test_truncates_long_title(self, tmp_path):
        with patch.object(self._get_ct_module(), 'ROOT', tmp_path):
            from core.codex_tools import create_markdown
            out = create_markdown("x" * 100, "content")
            assert Path(out).stem.startswith("x")
            assert len(Path(out).stem) <= 50

    def _get_ct_module(self):
        return sys.modules.get('core.codex_tools')


class TestCreateHtml:
    """create_html: 写 .html 文件。"""

    def test_creates_valid_html(self, tmp_path):
        with patch.object(sys.modules['core.codex_tools'], 'ROOT', tmp_path):
            from core.codex_tools import create_html
            out = create_html("Test", "<p>body</p>")
            assert Path(out).exists()
            html = Path(out).read_text(encoding="utf-8")
            assert "<!DOCTYPE html>" in html
            assert "<title>Test</title>" in html

    def test_html_is_standalone(self, tmp_path):
        with patch.object(sys.modules['core.codex_tools'], 'ROOT', tmp_path):
            from core.codex_tools import create_html
            out = create_html("S", "content")
            html = Path(out).read_text(encoding="utf-8")
            assert html.startswith("<!DOCTYPE")
            assert html.strip().endswith("</html>")


# ── create_pdf（依赖 reportlab / weasyprint）──────────────────────────


class TestCreatePdf:
    """create_pdf: 优雅处理依赖缺失。"""

    def test_no_dependency_returns_error(self, tmp_path):
        """两个库都没有时返回错误信息而非崩溃。"""
        with patch.object(sys.modules['core.codex_tools'], 'ROOT', tmp_path):
            from core.codex_tools import create_pdf
            with patch.dict(sys.modules, {'reportlab': None, 'weasyprint': None}):
                out = create_pdf("test content", output=str(tmp_path / "test.pdf"))
                assert isinstance(out, str)
                assert "[错误]" in out or out.endswith(".pdf")


# ── js_eval（依赖 Node.js）────────────────────────────────────────────


class TestJsEval:
    """js_eval: 需要 Node.js REPL，测试优雅降级。"""

    def test_returns_string(self):
        """js_eval 应返回字符串结果（即使 Node 不可用也应是 str 而非崩溃）。"""
        from core.codex_engines import js_eval
        result = js_eval("1+1")
        # 可能返回 "2" 或错误信息，但必须是 str
        assert isinstance(result, str)


# ── MCPConnector ───────────────────────────────────────────────────────


class TestMCPConnector:
    """MCPConnector: 进程管理。"""

    def test_mcp_connect_returns_bool_or_str(self):
        """mcp_connect 对不存在的命令应返回 False 或错误字符串（不崩溃）。"""
        from core.codex_engines import mcp_connect
        result = mcp_connect("test-server", "nonexistent_command_xyz", "")
        assert isinstance(result, (bool, str))

    def test_mcp_call_no_server(self):
        """对未连接的 server 调用应优雅处理。"""
        from core.codex_engines import mcp_call
        result = mcp_call("nonexistent", "tool", "{}")
        assert isinstance(result, str)
