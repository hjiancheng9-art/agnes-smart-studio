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
        "flaky: Known flaky test — triaged, root cause documented in conftest.",
    ]
    for marker in markers:
        config.addinivalue_line("markers", marker)

    # --leak-report: detect global state pollution across test modules
    config.addinivalue_line(
        "markers",
        "leak: Enable global state leak detection (use --leak-report flag)",
    )


# ── Global state cleanup ──
#
# These resets are proven safe and reduce cross-module test pollution.
# See commit history for failed attempts (35+ resets caused MORE failures).
#
# KNOWN REMAINING FLAKY TESTS (root cause: 265-module global singleton debt):
#   tests/test_zcode_pipeline.py — 5–6 tests, OUTPUT_ROOT/MANIFEST_DIR pollution
#     → Runs fine in isolation.  Fails in full suite when prior modules set
#       pt.OUTPUT_ROOT to deleted temp dirs (propagated via transitive imports).
#   tests/test_tool_router.py — 4 tests, intra-module ordering
#   tests/test_background.py — 1 test, singleton reset race
#   tests/test_phase11_failure_learning.py — 1 test
#   tests/test_zcode_engines.py — 1 test, validator state

_RESET_CALLS = [
    ("core.tool_router", "reset_tool_router"),
    ("core.background", "reset_background_manager"),
    ("core.chat_prompt", "reset_prompt_cache"),
    ("core.tool_cache", "reset_tool_cache"),
    ("core.agent_cache", "reset_agent_cache"),
    ("core.workspace_guard", "reset_workspace_guard"),
    ("core.secret_redactor", "reset_secret_redactor"),
    ("core.pipeline_tools", "reset_pipeline_globals"),
]


@pytest.fixture(autouse=True, scope="module")
def _reset_shared_state():
    """Reset module-level globals before each test module."""
    for module_name, func_name in _RESET_CALLS:
        try:
            mod = __import__(module_name, fromlist=[func_name])
            reset_fn = getattr(mod, func_name, None)
            if reset_fn is not None:
                reset_fn()
        except Exception:
            pass
    return


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    from pathlib import Path

    return Path(__file__).resolve().parent.parent
