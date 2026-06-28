"""Tests for pipeline/workflows.py — PipelineOrchestrator structure."""

import importlib


class TestWorkflowImports:
    def test_imports(self):
        mod = importlib.import_module("pipeline.workflows")
        assert hasattr(mod, "PipelineOrchestrator")
