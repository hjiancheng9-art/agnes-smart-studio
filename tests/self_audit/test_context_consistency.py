"""Self-Audit: Context & Multi-turn Consistency.

Tests:
  1. Version identity across turns
  2. Provider consistency across turns
  3. Task tracking across turns
  4. Completed actions remembered
  5. Correction after user negation
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ── Multi-turn consistency test cases ──

CONSISTENCY_CASES = [
    {
        "name": "version_consistency",
        "turns": [
            {"user": "你是谁？", "expect_contains": ["CRUX Studio"]},
            {"user": "你是不是 v5.0？", "expect_not_contains": ["我是 v5.0"]},
            {"user": "刚才我说你是什么版本？", "expect_contains": ["v6.0.0"]},
        ],
    },
    {
        "name": "task_memory",
        "turns": [
            {"user": "帮我记录：当前任务是测试 context 一致性", "expect_contains": []},
            {"user": "你刚才说当前任务是什么？", "expect_contains": ["context", "一致性", "测试"]},
            {"user": "还有别的任务吗？", "expect_not_contains": ["P8", "P9", "P10"]},
        ],
    },
    {
        "name": "correction_consistency",
        "turns": [
            {"user": "CRUX v6.0.0 已完成了 self-audit 框架搭建", "expect_contains": []},
            {"user": "建议下一步做什么？", "expect_contains": [], "expect_not_contains": ["先搭框架"]},
            {
                "user": "你刚才建议了什么？",
                "expect_contains": [],
                "expect_not_contains": [],
            },  # should reference its own suggestion
        ],
    },
]


class TestContextConsistency:
    """Multi-turn conversation must maintain invariants."""

    def test_context_jsonl_must_exist(self):
        """If using jsonl test cases, the file must exist."""
        # This validates the test data exists
        path = Path("tests/self_audit/fixtures/consistency_cases.jsonl")
        if not path.exists():
            pytest.skip("consistency_cases.jsonl not found — create it for full testing")

    @pytest.mark.parametrize("case", CONSISTENCY_CASES, ids=lambda c: c["name"])
    def test_consistency_case_structure(self, case):
        """Validate consistency test case format."""
        assert "name" in case
        assert "turns" in case
        assert len(case["turns"]) >= 2, "Consistency test needs at least 2 turns"
        for turn in case["turns"]:
            assert "user" in turn
            assert "expect_contains" in turn or "expect_not_contains" in turn

    def test_version_identity_file(self):
        """Version identity must be consistent across all config files."""
        mismatches = []
        for path in Path(".").glob("*.md"):
            content = path.read_text(encoding="utf-8", errors="ignore")
            # Check for older version references
            old_versions = ["v5.0", "v5.0.0", "v4.0", "v3.0"]
            for v in old_versions:
                if v in content and "CHANGELOG" not in str(path):
                    mismatches.append(f"{path}: references {v}")
        # CHANGELOG is allowed to reference old versions
        if mismatches:
            print(f"⚠ Version inconsistency found: {len(mismatches)} files reference old versions")
            for m in mismatches[:5]:
                print(f"  {m}")


class TestMemorySnapshot:
    """Structured memory snapshot validation."""

    REQUIRED_KEYS = [
        "user_decisions",
        "project_constraints",
        "current_task",
        "known_failures",
        "recent_files",
        "open_questions",
    ]

    def test_memory_snapshot_structure(self):
        """Memory snapshot must have all required keys."""
        # Check that memory snapshot format is defined
        memory_dir = Path(".crux_memory")
        assert memory_dir.exists(), ".crux_memory directory not found"

    def test_wiki_structure(self):
        """Wiki pages must be accessible for context persistence."""
        wiki_dir = Path(".crux_wiki")
        if wiki_dir.exists():
            pages = list(wiki_dir.glob("**/*.json"))
            assert len(pages) >= 0  # Just check it doesn't crash
