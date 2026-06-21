"""Tests for core.self_evolve — self-evolution engine."""

import json
from pathlib import Path
from unittest.mock import patch


class TestParseEvolutionOutput:
    def test_basic_parsing(self):
        from core.self_evolve import parse_evolution_output
        raw = """### 1. Failure Categories
Network timeout
API rate limit

### 2. Critical Fixes
FILE: core/client.py
FIND: old code
REPLACE: new code
REASON: bug fix

### 3. Preventive Measures
Add retry logic

### 4. New Tool Suggestions
Add health check tool
"""
        result = parse_evolution_output(raw)
        assert len(result["categories"]) > 0
        assert "Network timeout" in result["categories"]
        assert len(result["fixes"]) > 0
        assert "Preventive Measures" not in str(result["preventions"])
        assert "Add retry logic" in result["preventions"]
        assert "Add health check tool" in result["suggestions"]

    def test_empty_output(self):
        from core.self_evolve import parse_evolution_output
        result = parse_evolution_output("")
        assert result["categories"] == []
        assert result["fixes"] == []
        assert result["edit_file_tasks"] == []

    def test_extracts_edit_file_tasks(self):
        from core.self_evolve import parse_evolution_output
        raw = """
EDIT_FILE_PATH: core/client.py
EDIT_FILE_FIND:
    timeout = 5
EDIT_FILE_REPLACE:
    timeout = 30
REASON: increase timeout

Some other text
"""
        result = parse_evolution_output(raw)
        assert len(result["edit_file_tasks"]) == 1
        task = result["edit_file_tasks"][0]
        assert task["path"] == "core/client.py"
        assert "timeout = 5" in task["find"]
        assert "timeout = 30" in task["replace"]

    def test_raw_preserved(self):
        from core.self_evolve import parse_evolution_output
        raw = "some analysis output"
        result = parse_evolution_output(raw)
        assert result["raw"] == raw


class TestExtractFilePatches:
    def test_extracts_patches(self):
        from core.self_evolve import extract_file_patches
        text = """
Some intro text
FILE: core/tools.py
FIND: old_code
REPLACE: new_code
REASON: improvement
More text
"""
        patches = extract_file_patches(text)
        assert len(patches) == 1
        assert patches[0]["file"] == "core/tools.py"
        assert patches[0]["find"] == "old_code"
        assert patches[0]["replace"] == "new_code"

    def test_no_patches(self):
        from core.self_evolve import extract_file_patches
        patches = extract_file_patches("no patches here")
        assert patches == []

    def test_multiple_patches(self):
        from core.self_evolve import extract_file_patches
        text = """
FILE: a.py
FIND: old_a
REPLACE: new_a
REASON: fix a

FILE: b.py
FIND: old_b
REPLACE: new_b
REASON: fix b
"""
        patches = extract_file_patches(text)
        assert len(patches) == 2
        assert patches[0]["file"] == "a.py"
        assert patches[1]["file"] == "b.py"


class TestCollectFailureLogs:
    def test_no_logs(self, tmp_path):
        from core.self_evolve import collect_failure_logs
        with patch("core.self_evolve.OUTPUT_DIR", tmp_path):
            result = collect_failure_logs()
        assert result == []

    def test_reads_audit_log(self, tmp_path):
        from core.self_evolve import collect_failure_logs
        audit = tmp_path / "tool_audit.jsonl"
        entries = [
            {"tool": "read_file", "success": True, "error": ""},
            {"tool": "write_file", "success": False, "error": "Permission denied"},
            {"tool": "run_bash", "success": True, "error": ""},
        ]
        audit.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in entries),
            encoding="utf-8",
        )
        with patch("core.self_evolve.OUTPUT_DIR", tmp_path):
            result = collect_failure_logs()
        assert len(result) == 1
        assert result[0]["tool"] == "write_file"
        assert "Permission denied" in result[0]["error"]

    def test_reads_trace_log(self, tmp_path):
        from core.self_evolve import collect_failure_logs
        traces = tmp_path / "traces.jsonl"
        entries = [
            {"tool": "read_file", "success": False, "error": "Not found"},
        ]
        traces.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in entries),
            encoding="utf-8",
        )
        with patch("core.self_evolve.OUTPUT_DIR", tmp_path):
            result = collect_failure_logs()
        assert len(result) == 1

    def test_max_entries(self, tmp_path):
        from core.self_evolve import collect_failure_logs
        audit = tmp_path / "tool_audit.jsonl"
        entries = [{"tool": f"tool_{i}", "success": False, "error": f"err_{i}"}
                   for i in range(50)]
        audit.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in entries),
            encoding="utf-8",
        )
        with patch("core.self_evolve.OUTPUT_DIR", tmp_path):
            result = collect_failure_logs(max_entries=10)
        assert len(result) <= 10


class TestCollectRecentCode:
    def test_collects_py_files(self, tmp_path):
        from core.self_evolve import collect_recent_code
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "a.py").write_text("x = 1\n", encoding="utf-8")
        with patch.object(Path, "parent", tmp_path):
            # Just test it doesn't crash
            pass
        # Test with specific files
        f = tmp_path / "test.py"
        f.write_text("hello", encoding="utf-8")
        result = collect_recent_code(files=[str(f)])
        assert "test.py" in result
        assert "hello" in result

    def test_nonexistent_files(self, tmp_path):
        from core.self_evolve import collect_recent_code
        # Nonexistent files are silently skipped (p.exists() check)
        result = collect_recent_code(files=["/nonexistent/file.py"])
        assert result == ""


class TestApplyPatchSafe:
    def test_dry_run_success(self, tmp_path):
        from core.self_evolve import apply_patch_safe
        f = tmp_path / "target.py"
        f.write_text("line1\nold_line\nline3\n", encoding="utf-8")
        patch = {
            "file": str(f),
            "find": "old_line",
            "replace": "new_line",
            "reason": "update",
        }
        result = apply_patch_safe(patch, dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True
        # File unchanged
        assert "old_line" in f.read_text(encoding="utf-8")

    def test_dry_run_file_not_found(self):
        from core.self_evolve import apply_patch_safe
        patch = {"file": "/nonexistent/file.py", "find": "x", "replace": "y"}
        result = apply_patch_safe(patch, dry_run=True)
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_dry_run_find_not_found(self, tmp_path):
        from core.self_evolve import apply_patch_safe
        f = tmp_path / "target.py"
        f.write_text("actual content\n", encoding="utf-8")
        patch = {"file": str(f), "find": "nonexistent text", "replace": "new"}
        result = apply_patch_safe(patch, dry_run=True)
        assert result["success"] is False
        assert "FIND text not found" in result["error"]

    def test_actual_apply(self, tmp_path):
        from core.self_evolve import apply_patch_safe
        f = tmp_path / "target.py"
        f.write_text("old content\n", encoding="utf-8")
        patch = {"file": str(f), "find": "old content", "replace": "new content", "reason": "test"}
        result = apply_patch_safe(patch, dry_run=False)
        assert result["success"] is True
        assert "new content" in f.read_text(encoding="utf-8")
        # Backup should exist
        assert f.with_suffix(".py.bak").exists()

    def test_relative_path_resolution(self, tmp_path):
        from core.self_evolve import apply_patch_safe
        # Test relative path is resolved against project root
        patch = {"file": "nonexistent_rel.py", "find": "x", "replace": "y"}
        result = apply_patch_safe(patch, dry_run=True)
        # Should resolve relative to project root (may or may not exist)
        # We just verify it doesn't crash
        assert "success" in result


class TestBuildAnalysisPrompt:
    def test_basic_prompt(self):
        from core.self_evolve import build_analysis_prompt
        failures = [{"tool": "read_file", "error": "not found"}]
        with patch("core.self_evolve.collect_recent_code", return_value="# code here"):
            prompt = build_analysis_prompt(failures)
        assert "read_file" in prompt
        assert "not found" in prompt
        assert "FILE:" in prompt
        assert "FIND:" in prompt

    def test_empty_failures(self):
        from core.self_evolve import build_analysis_prompt
        with patch("core.self_evolve.collect_recent_code", return_value=""):
            prompt = build_analysis_prompt([])
        assert "0 entries" in prompt


class TestToolDefs:
    def test_tool_defs_exist(self):
        from core.self_evolve import SELF_EVOLVE_TOOL_DEFS
        assert len(SELF_EVOLVE_TOOL_DEFS) == 1
        assert SELF_EVOLVE_TOOL_DEFS[0]["function"]["name"] == "self_evolve"

    def test_executor_map(self):
        from core.self_evolve import SELF_EVOLVE_EXECUTOR_MAP
        assert "self_evolve" in SELF_EVOLVE_EXECUTOR_MAP
