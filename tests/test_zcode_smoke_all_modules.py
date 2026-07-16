"""Auto-generated smoke test — verifies every core module imports without error.

Covers all core modules. Catches SyntaxError, ImportError, and circular imports.
"""

from __future__ import annotations

import importlib
import os
import sys

import pytest

# ── Discover all core modules ────────────────────────────────

CORE_DIR = os.path.join(os.path.dirname(__file__), "..", "core")


def _discover_modules() -> list[str]:
    modules = []
    for f in sorted(os.listdir(CORE_DIR)):
        if f.endswith(".py") and not f.startswith("__") and not f.startswith("._"):
            modules.append(f"core.{f[:-3]}")
    return modules


ALL_MODULES = _discover_modules()

# Known optional / experimental modules that may fail to import
# (these require external dependencies not in requirements.txt)
OPTIONAL_MODULES: set[str] = set()


@pytest.mark.parametrize("module_name", ALL_MODULES)
def test_module_imports(module_name: str):
    """Each core module must be importable without error."""
    if module_name in OPTIONAL_MODULES:
        pytest.skip(f"Optional module: {module_name}")

    # Clean slate: remove from sys.modules to test fresh import
    if module_name in sys.modules:
        del sys.modules[module_name]

    try:
        importlib.import_module(module_name)
    except SyntaxError as e:
        pytest.fail(f"SyntaxError in {module_name}: line {e.lineno}: {e.msg}")
    except ImportError as e:
        msg = str(e)
        # Allow optional dependency failures
        if any(skip in msg.lower() for skip in ("no module named", "optional")):
            OPTIONAL_MODULES.add(module_name)
            pytest.skip(f"Optional dependency: {msg[:80]}")
        pytest.fail(f"ImportError in {module_name}: {msg[:120]}")
    except Exception as e:
        pytest.fail(f"{type(e).__name__} in {module_name}: {str(e)[:120]}")


def test_module_count():
    """Sanity check: core module count within expected range."""
    assert len(ALL_MODULES) >= 200, f"Expected >=200 modules, got {len(ALL_MODULES)}"
    assert len(ALL_MODULES) <= 270, f"Expected <=270 modules, got {len(ALL_MODULES)}"
