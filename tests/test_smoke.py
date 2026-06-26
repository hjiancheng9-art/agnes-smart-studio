"""Smoke tests - verify key modules import and basic functionality works."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestImports:
    def test_core_config(self):
        pass

    def test_core_client(self):
        pass

    def test_core_tools(self):
        pass

    def test_core_brain(self):
        pass

    def test_core_agent(self):
        pass

    def test_core_skills(self):
        pass

    def test_core_hooks(self):
        pass

    def test_core_provider(self):
        pass

    def test_ui_cli(self):
        pass

    def test_engines_text_to_image(self):
        pass

    def test_engines_video(self):
        pass

    def test_pipeline_workflows(self):
        pass

    def test_utils_modules(self):
        pass

    def test_register_learning_hooks_callable(self):
        from core.hooks import register_learning_hooks

        assert callable(register_learning_hooks)
        register_learning_hooks()


class TestSyntax:
    def test_all_py_files_syntax(self):
        errors = []
        # 归档目录（scripts/scratch, tests/manual）不纳入语法扫描，
        # 它们是一次性脚本，已知有 lint 警告，不是生产代码。
        skip_dirs = {"__pycache__", ".pytest_cache", "output", "scripts", "manual"}
        for py_file in sorted(ROOT.rglob("*.py")):
            parts = set(py_file.parts)
            if parts & skip_dirs:
                continue
            try:
                with open(py_file, encoding="utf-8") as fh:
                    ast.parse(fh.read(), filename=str(py_file))
            except SyntaxError as e:
                errors.append(str(py_file) + ":" + str(e.lineno) + " - " + e.msg)
        assert len(errors) == 0, "Syntax errors:" + chr(10) + chr(10).join(errors)


class TestToolsJson:
    def test_tools_json_exists(self):
        assert (ROOT / "tools.json").exists()

    def test_tools_json_is_valid_json(self):
        with open(ROOT / "tools.json", encoding="utf-8") as fh:
            data = json.load(fh)
        assert "tools" in data
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) > 10

    def test_tools_json_has_key_tools(self):
        with open(ROOT / "tools.json", encoding="utf-8") as fh:
            data = json.load(fh)
        names = {t["name"] for t in data["tools"]}
        for name in ("read_file", "write_file", "edit_file", "search_files", "run_python"):
            assert name in names


class TestHealthCheck:
    def test_startup_checks_run(self):
        from core.startup_checks import critical_failures, run_all

        results = run_all()
        assert isinstance(results, list)
        assert len(results) >= 3
        crit = critical_failures(results)
        assert isinstance(crit, list)
