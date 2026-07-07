"""Tests for core/skill_manifest — SkillManifest."""

from __future__ import annotations

import pytest
from core.skill_manifest import SkillManifest


class TestSkillManifest:
    def test_default_creation(self):
        sm = SkillManifest(name="test", version="1.0", description="A test skill")
        assert sm.name == "test"
        assert sm.version == "1.0"
        assert sm.description == "A test skill"

    def test_with_permissions(self):
        sm = SkillManifest(
            name="test-skill",
            version="2.0.0",
            description="Test with permissions",
            permissions=[],
        )
        assert sm.name == "test-skill"
        assert sm.version == "2.0.0"
        assert sm.permissions == []

    def test_example_manifest(self):
        from core.skill_manifest import EXAMPLE_MANIFEST
        assert EXAMPLE_MANIFEST.name is not None
        assert EXAMPLE_MANIFEST.version is not None
