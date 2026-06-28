"""Tests for core/test_loop.py — TestGenerator, TestRunner, TestLoop classes."""

from unittest.mock import MagicMock

from core.test_loop import TestGenerator, TestLoop, TestRunner


class TestTestGenerator:
    def test_init_stores_client(self):
        mock_client = MagicMock()
        gen = TestGenerator(mock_client)
        assert gen.client is mock_client
        assert gen.model == "deepseek-v4-pro"

    def test_init_custom_model(self):
        mock_client = MagicMock()
        gen = TestGenerator(mock_client, model="custom-model")
        assert gen.model == "custom-model"


class TestTestRunner:
    def test_init(self):
        runner = TestRunner()
        assert isinstance(runner, TestRunner)

    def test_run_tests_returns_structured_dict(self):
        runner = TestRunner()
        result = runner.run_tests("tests/test_constraints.py")
        assert isinstance(result, dict)
        assert "passed" in result
        assert "failed" in result
        assert "total" in result
        assert "duration_s" in result
        assert "raw_output" in result

    def test_run_tests_nonexistent_file(self):
        runner = TestRunner()
        result = runner.run_tests("nonexistent_test_file.py")
        assert isinstance(result, dict)
        assert result["total"] == 0

    def test_run_single_test(self):
        runner = TestRunner()
        result = runner.run_single_test(
            "tests/test_constraints.py",
            "test_frozenset_immutable"
        )
        assert isinstance(result, dict)
        assert "total" in result


class TestTestLoop:
    def test_init(self):
        mock_client = MagicMock()
        loop = TestLoop(mock_client)
        assert loop.client is mock_client
        assert loop.model == "deepseek-v4-pro"

    def test_init_custom_model(self):
        mock_client = MagicMock()
        loop = TestLoop(mock_client, model="custom")
        assert loop.model == "custom"

    def test_init_creates_generator_and_runner(self):
        mock_client = MagicMock()
        loop = TestLoop(mock_client)
        assert isinstance(loop.generator, TestGenerator)
        assert isinstance(loop.runner, TestRunner)
