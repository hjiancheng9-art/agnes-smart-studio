# -*- coding: utf-8 -*-
"""Pytest fixtures for Agnes tests."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def api_key():
    """Ensure AGNES_API_KEY is set from .env."""
    from agnes.client import _load_dotenv
    _load_dotenv()
    key = os.environ.get("AGNES_API_KEY", "")
    if not key:
        pytest.skip("AGNES_API_KEY not set – skipping integration tests")
    return key


@pytest.fixture(scope="session")
def client(api_key):
    """Create a reusable AgnesClient for integration tests."""
    from agnes.client import AgnesClient
    return AgnesClient()
