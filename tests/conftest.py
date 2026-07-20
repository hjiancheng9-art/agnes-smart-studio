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
# v6.2: Fixed all 5 flaky groups:
#   ✅ test_background — TOCTOU race in reset_background_manager (moved inside lock)
#   ✅ test_zcode_engines — Missing provider_manager reset (added to _RESET_CALLS)
#   ✅ test_zcode_pipeline — Unsafe _run_with_temp → pipeline_scope() + absolute paths
#   ✅ test_tool_router — Added reset_tool_router() call before isolated_router_scope
#   ✅ test_phase11_failure_learning — Added reset_telemetry + reset_decision_recorder
#
# No known remaining flaky tests.

_RESET_CALLS = [
    ("core.tool_router", "reset_tool_router"),
    ("core.background", "reset_background_manager"),
    ("core.chat_prompt", "reset_prompt_cache"),
    ("core.tool_cache", "reset_tool_cache"),
    ("core.agent_cache", "reset_agent_cache"),
    ("core.workspace_guard", "reset_workspace_guard"),
    ("core.secret_redactor", "reset_secret_redactor"),
    ("core.pipeline_tools", "reset_pipeline_globals"),
    # v6.2: 新增 reset 函数 — 消除之前遗漏的单例状态泄漏
    ("core.defense", "reset_defense_state"),
    ("core.fake_fix_detector", "reset_fake_fix_detector"),
    ("core.patch", "reset_patch_state"),
    ("core.adversarial_bypass", "reset_adversarial_bypass_stats"),
    ("core.provider", "reset_provider_manager"),
    ("core.crux_telemetry", "reset_telemetry"),
    ("core.trace_debugger", "reset_decision_recorder"),
    ("core.goal_manager", "reset_goal_manager"),
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
