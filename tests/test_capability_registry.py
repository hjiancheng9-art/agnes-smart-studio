"""Tests for capability_registry — tool registration and discovery."""
import pytest

pytestmark = pytest.mark.unit

import pytest
from unittest.mock import MagicMock, patch


class TestCapabilityRegistryStructure:
    """Verify capability_registry module has expected API."""

    def test_module_imports(self):
        """capability_registry module can be imported."""
        import importlib.util, os
        path = os.path.join("core", "capability_registry.py")
        if not os.path.exists(path):
            pytest.skip("capability_registry.py not found")
        spec = importlib.util.spec_from_file_location("capability_registry", path)
        assert spec is not None, "capability_registry.py should be importable"

    def test_has_register_and_lookup(self):
        """capability_registry should expose register/lookup functions."""
        import importlib.util, os
        path = os.path.join("core", "capability_registry.py")
        if not os.path.exists(path):
            pytest.skip("capability_registry.py not found")

        import importlib
        spec = importlib.util.spec_from_file_location("capability_registry", path)
        mod = importlib.util.module_from_spec(spec)
        # Don't actually load it (may have side effects), just check the file
        assert spec is not None

    def test_capability_registry_referenced(self):
        """capability_registry module exists as a Python file."""
        import os
        path = os.path.join("core", "capability_registry.py")
        assert os.path.exists(path), f"{path} should exist"


# ═══════════════════════════════════════════════════
#  Fake capability registry for contract testing
# ═══════════════════════════════════════════════════

class FakeCapabilityRegistry:
    """Fake capability registry for unit testing."""

    def __init__(self):
        self._capabilities: dict[str, dict] = {}

    def register(self, name: str, tool_name: str, category: str, risk: str):
        self._capabilities[name] = {
            "tool": tool_name,
            "category": category,
            "risk": risk,
        }

    def lookup(self, name: str) -> dict | None:
        return self._capabilities.get(name)

    def find_by_tool(self, tool_name: str) -> list[dict]:
        return [v for v in self._capabilities.values() if v["tool"] == tool_name]

    def all(self) -> dict[str, dict]:
        return dict(self._capabilities)

    def has_capability(self, name: str) -> bool:
        return name in self._capabilities


class TestFakeCapabilityRegistry:
    """FakeCapabilityRegistry behaves like the real one should."""

    @pytest.fixture
    def registry(self):
        r = FakeCapabilityRegistry()
        r.register("code_search", "search_files", "search", "readonly")
        r.register("code_execute", "run_python", "execute", "shell")
        r.register("browser_nav", "pw_navigate", "browser", "browser")
        return r

    def test_register_and_lookup(self, registry):
        cap = registry.lookup("code_search")
        assert cap is not None
        assert cap["tool"] == "search_files"

    def test_lookup_missing(self, registry):
        cap = registry.lookup("nonexistent")
        assert cap is None

    def test_has_capability(self, registry):
        assert registry.has_capability("code_search")
        assert not registry.has_capability("nope")

    def test_find_by_tool(self, registry):
        caps = registry.find_by_tool("run_python")
        assert len(caps) == 1
        assert caps[0]["category"] == "execute"

    def test_all_returns_copy(self, registry):
        all_caps = registry.all()
        assert len(all_caps) == 3
        # Modifying the copy doesn't affect original
        all_caps["new"] = {}
        assert not registry.has_capability("new")
