"""Tests for cleanup — Categories D+F: remove stale files, fix configs."""

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestDeletedFiles:
    """Verify stale/deprecated files are removed."""

    def test_core_fusion_deleted(self):
        """core/core_fusion.py should not exist (stale fusion module)."""
        assert not (PROJECT_ROOT / "core" / "core_fusion.py").exists(), (
            "core/core_fusion.py should be deleted"
        )

    def test_plan_verify_deleted(self):
        """core/plan_verify.py should not exist (stale plan verify module)."""
        assert not (PROJECT_ROOT / "core" / "plan_verify.py").exists(), (
            "core/plan_verify.py should be deleted"
        )


class TestModelsConfig:
    """Verify models.json cleanup."""

    def test_zhipu_key_removed(self):
        """models.json providers.zhipu.api_key should be empty string."""
        models_path = PROJECT_ROOT / "models.json"
        assert models_path.exists(), "models.json should exist"
        with open(models_path, encoding="utf-8") as f:
            data = json.load(f)
        providers = data.get("providers", {})
        assert "zhipu" in providers, "zhipu provider should exist in models.json"
        api_key = providers["zhipu"].get("api_key", None)
        assert api_key == "", (
            f"providers.zhipu.api_key should be empty string, got: {api_key!r}"
        )


class TestChatDefaults:
    """Verify chat.py defaults are correct."""

    def test_vote_default_false(self):
        """ChatSession._vote_enabled should default to False."""
        from core.chat import ChatSession
        # Create a minimal session to check default
        ChatSession.__new__(ChatSession)
        # _vote_enabled is set in __init__, so we need to init
        # Instead, check the class source for the default value
        import inspect
        source = inspect.getsource(ChatSession.__init__)
        assert "_vote_enabled" in source, "_vote_enabled should be set in __init__"
        assert "False" in source.split("_vote_enabled")[1].split("=")[1].split("#")[0], (
            "_vote_enabled default should be False"
        )


class TestVersionImport:
    """Verify version is imported from single source of truth."""

    def test_version_not_hardcoded(self):
        """crux_studio.py _chat_plain should import __version__ from core.version."""
        crux_studio_path = PROJECT_ROOT / "crux_studio.py"
        assert crux_studio_path.exists(), "crux_studio.py should exist"
        source = crux_studio_path.read_text(encoding="utf-8")

        # _chat_plain function should import from core.version
        # Check that __version__ is imported from core.version somewhere in the file
        assert "from core.version import __version__" in source, (
            "crux_studio.py should import __version__ from core.version"
        )

    def test_version_module_exists(self):
        """core/version.py should exist and export __version__."""
        from core.version import __version__
        assert isinstance(__version__, str)
        assert len(__version__) > 0
        # Should follow semver pattern
        import re
        assert re.match(r"^\d+\.\d+\.\d+", __version__), (
            f"Version should be semver, got: {__version__}"
        )
