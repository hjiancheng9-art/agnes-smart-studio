"""Root test configuration — pytest markers and fixtures."""

import pytest


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


@pytest.fixture(scope="session")
def project_root():
    """Return the project root directory."""
    from pathlib import Path
    return Path(__file__).resolve().parent.parent
