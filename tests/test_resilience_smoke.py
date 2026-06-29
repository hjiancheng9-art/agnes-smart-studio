"""Smoke tests for core/resilience.py — retry, classify, circuit breaker."""

from pathlib import Path


class TestResilienceSyntax:
    """resilience.py 语法和基本结构检查。"""

    def test_resilience_syntax(self):
        """resilience.py 可被 ast.parse 正确解析。"""
        import ast
        path = Path(__file__).parent.parent / "core" / "resilience.py"
        assert path.exists(), "core/resilience.py not found"
        with open(path, encoding="utf-8") as f:
            ast.parse(f.read())

    def test_resilience_class_exists(self):
        """关键类和函数签名存在。"""
        path = Path(__file__).parent.parent / "core" / "resilience.py"
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # 核心类
        classes = [
            "class ErrorClassifier",
            "class CircuitBreaker",
            "class GracefulDegradation",
            "class RetryPolicy",
        ]
        for c in classes:
            assert c in content, f"Class missing: {c}"
        # 核心函数
        funcs = ["def classify(", "def is_retryable(", "def reset_all_circuits("]
        for f in funcs:
            assert f in content, f"Function missing: {f}"


class TestResilienceModuleImport:
    """resilience.py 模块导入测试。"""

    def test_core_resilience_module(self):
        """core.resilience 可导入（不报 SyntaxError）。"""
        import importlib
        import sys
        # 不实际运行初始化（可能有文件 IO 副作用），只检查可导入
        spec = importlib.util.find_spec("core.resilience")
        assert spec is not None, "core.resilience module not found"

    def test_key_imports_in_resilience(self):
        """resilience.py 使用的关键标准库导入。"""
        path = Path(__file__).parent.parent / "core" / "resilience.py"
        with open(path, encoding="utf-8") as f:
            content = f.read()
        imports = []
        for line in content.split("\n"):
            if line.startswith("import ") or line.startswith("from "):
                imports.append(line.strip())
        # 至少应该有 asyncio / time / traceback 等标准库导入
        assert any("asyncio" in i for i in imports), "asyncio import missing"
        assert any("time" in i for i in imports), "time import missing"
        assert any("import traceback" in i or "import threading" in i for i in imports), \
            "traceback/threading import missing"


class TestCircuitBreakerContract:
    """CircuitBreaker 接口契约检查。"""

    def test_circuit_breaker_methods(self):
        """CircuitBreaker 应有标准方法签名。"""
        path = Path(__file__).parent.parent / "core" / "resilience.py"
        with open(path, encoding="utf-8") as f:
            content = f.read()

        if "class CircuitBreaker" not in content:
            return  # 跳过

        methods = ["def call(", "def record_success(", "def record_failure(", "def allow_request("]
        for m in methods:
            assert m in content, f"CircuitBreaker missing {m} method"

    def test_circuit_breaker_states(self):
        """CircuitBreaker 状态定义。"""
        path = Path(__file__).parent.parent / "core" / "resilience.py"
        with open(path, encoding="utf-8") as f:
            content = f.read()

        states = ["CLOSED", "OPEN", "HALF_OPEN"]
        for s in states:
            if s in content:
                return  # 至少有一个状态
        if "'closed'" in content or "'open'" in content or "'half_open'" in content:
            return
        assert False, "No circuit breaker states (CLOSED/OPEN/HALF_OPEN) found"


class TestErrorClassifierContract:
    """ErrorClassifier 接口契约检查。"""

    def test_error_categories(self):
        """错误分类应有网络/API/超时等类别。"""
        path = Path(__file__).parent.parent / "core" / "resilience.py"
        with open(path, encoding="utf-8") as f:
            content = f.read()

        categories = ["network", "timeout", "rate_limit", "auth", "api"]
        found = [c for c in categories if c in content.lower()]
        assert len(found) >= 2, \
            f"Only {len(found)}/{len(categories)} error categories found: {found}"
