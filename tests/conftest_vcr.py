"""VCR-based HTTP recording/replay for provider tests.

Uses vcrpy to record real API responses once, then replay offline.
No API key needed after initial recording — fast, deterministic, free.

Usage:
    # Record mode (needs API key):
    pytest tests/test_vcr_provider.py --vcr-record=once

    # Replay mode (no API key, no network):
    pytest tests/test_vcr_provider.py

Cassettes stored in tests/cassettes/ — commit to git for CI reproducibility.
"""

from __future__ import annotations

import pytest

# Shared vcrpy configuration for all provider tests
VCR_CONFIG = {
    "record_mode": "once",  # record once, replay thereafter
    "match_on": ["method", "scheme", "host", "port", "path", "query"],
    "filter_headers": ["authorization", "x-api-key", "cookie"],
    "filter_query_parameters": ["api_key", "key", "token"],
    "decode_compressed_response": True,
}


@pytest.fixture(scope="module")
def vcr_config():
    """Default vcr config for provider tests — filter secrets from cassettes."""
    return VCR_CONFIG


@pytest.fixture(scope="module")
def vcr_cassette_dir():
    """Path to cassette storage directory."""
    import os

    return os.path.join(os.path.dirname(__file__), "cassettes")
