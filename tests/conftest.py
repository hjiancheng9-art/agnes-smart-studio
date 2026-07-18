"""Root test configuration — pytest markers and fixtures."""

import pytest

# Load .env early so API key skip checks work at module import time
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


def pytest_configure(config):
    """Register custom markers for test layering."""
    markers = [
        "unit: Fast, no I/O, no network, no browser. Run first.",
        "integration: Tests that wire multiple modules together.",
        "slow: Tests taking >2 seconds.",
        "browser: Requires real browser (Playwright/CDP).",
        "network: Requires internet connectivity.",
        "mcp: Requires MCP server running.",
        "lsp: Requires LSP server running.",
        "github: Requires GitHub token.",
        "e2e: End-to-end, full stack.",
        "smoke: Quick sanity check (subset of unit).",
    ]
    for marker in markers:
        config.addinivalue_line("markers", marker)


# ── Global state cleanup: prevent singleton/global pollution across test modules ──


@pytest.fixture(autouse=True)
def _reset_shared_state():
    """Reset module-level globals before each test to prevent cross-test leakage.

    Some core modules use module-level singletons (BackgroundManager, ToolRouter)
    or global dicts (_internal_tools, _mcp_tools). Without cleanup between test
    files, tests that modify these globals poison downstream tests.

    This fixture clears the known global state before every single test.
    Tests that need pre-registered state should re-register in their own fixtures.
    """
    # Reset tool router globals (core.tool_router)
    try:
        from core.tool_router import reset_tool_router

        reset_tool_router()
    except Exception:
        pass

    # Reset background manager singleton (core.background)
    try:
        from core.background import reset_background_manager

        reset_background_manager()
    except Exception:
        pass

    return  # setup-only fixture, no teardown needed


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    from pathlib import Path

    return Path(__file__).resolve().parent.parent
