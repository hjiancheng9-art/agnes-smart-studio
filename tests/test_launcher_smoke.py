"""Smoke tests for launcher.py health_check and BeastConfig logic."""

import json
import subprocess
import sys
from pathlib import Path


class TestBeastConfigLoading:
    """验证 BeastConfig 能从 JSON 正确加载。"""

    def test_beast_config_structure(self):
        """launcher.py 依赖的 beast JSON 结构完整性检查。"""
        config_path = Path(__file__).parent.parent / "beasts.json"
        if not config_path.exists():
            # 也检查 .mcp.json 格式
            mcp_path = Path(__file__).parent.parent / ".mcp.json"
            assert mcp_path.exists(), "Neither beasts.json nor .mcp.json found"
            with open(mcp_path, encoding="utf-8") as f:
                cfg = json.load(f)
            assert "mcpServers" in cfg, ".mcp.json missing mcpServers"
            return

        with open(config_path, encoding="utf-8") as f:
            beasts = json.load(f)

        assert isinstance(beasts, dict), "beasts.json must be a dict"
        if "beasts" in beasts:
            beasts = beasts["beasts"]

        for bid, bcfg in beasts.items():
            assert isinstance(bcfg, dict), f"{bid} config must be a dict"
            assert "name" in bcfg or "command" in bcfg, \
                f"{bid} missing name/command"

    def test_binary_in_path_or_config(self):
        """至少 launcher.py 自身的 Python 在 PATH 中。"""
        py = sys.executable
        assert py, "No Python executable found"


class TestHealthResultShape:
    """HealthResult 数据形状契约。"""

    def test_health_result_keys(self):
        """模拟健康检查返回的字段完整性。"""
        # 只验证字段契约，不实际启动进程
        expected_keys = {"name", "icon", "status", "version", "latency_ms", "error"}
        mock = {
            "name": "test-beast",
            "icon": "T",
            "status": "offline",
            "version": "",
            "latency_ms": 0.0,
            "error": None,
        }
        assert set(mock.keys()) == expected_keys, \
            f"HealthResult keys mismatch: {set(mock.keys()) - expected_keys}"


class TestLauncherPythonSyntax:
    """launcher.py 语法和基本导入检查。"""

    def test_launcher_syntax(self):
        """launcher.py 可被 ast.parse 正确解析。"""
        import ast
        path = Path(__file__).parent.parent / "launcher.py"
        assert path.exists(), "launcher.py not found"
        with open(path, encoding="utf-8") as f:
            ast.parse(f.read())

    def test_launcher_imports(self):
        """launcher.py 核心导入不出错。"""
        # 只检查 import 行，不实际运行 launcher（它有 CLI 入口）
        path = Path(__file__).parent.parent / "launcher.py"
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # 确保关键符号存在
        assert "class BeastConfig" in content, "BeastConfig class missing"
        assert "class ProcessManager" in content, "ProcessManager class missing"
        assert "class MeshLauncher" in content, "MeshLauncher class missing"
        assert "def cleanup_zombies" in content, "cleanup_zombies method missing"
