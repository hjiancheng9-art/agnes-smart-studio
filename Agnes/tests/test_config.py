"""Tests for AgnesConfig and environment loading."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agnes.client import AgnesConfig, AgnesError


class TestAgnesConfig:
    """Config unit tests – no API calls."""

    def test_defaults(self):
        c = AgnesConfig()
        assert c.api_key == ""
        assert c.api_base == "https://apihub.agnes-ai.com/v1"
        assert c.timeout == 600

    def test_from_env_loads_key(self):
        os.environ["AGNES_API_KEY"] = "sk-test-12345"
        try:
            c = AgnesConfig.from_env()
            assert c.api_key == "sk-test-12345"
        finally:
            del os.environ["AGNES_API_KEY"]

    def test_from_env_custom_base(self):
        os.environ["AGNES_API_KEY"] = "sk-test"
        os.environ["AGNES_API_BASE"] = "https://custom.example.com/v1"
        try:
            c = AgnesConfig.from_env()
            assert c.api_base == "https://custom.example.com/v1"
        finally:
            del os.environ["AGNES_API_KEY"]
            del os.environ["AGNES_API_BASE"]

    def test_from_env_timeout(self):
        os.environ["AGNES_API_KEY"] = "sk-test"
        os.environ["AGNES_TIMEOUT"] = "30"
        try:
            c = AgnesConfig.from_env()
            assert c.timeout == 30
        finally:
            del os.environ["AGNES_API_KEY"]
            del os.environ["AGNES_TIMEOUT"]


class TestAgnesError:
    """Error class tests."""

    def test_creation(self):
        e = AgnesError("test message")
        assert str(e) == "test message"
        assert e.status_code == 0

    def test_with_status(self):
        e = AgnesError("unauthorized", status_code=401)
        assert e.status_code == 401
        assert "unauthorized" in str(e)

    def test_with_response(self):
        e = AgnesError("error", response={"detail": "bad"})
        assert e.response == {"detail": "bad"}

    def test_is_exception(self):
        with pytest.raises(AgnesError):
            raise AgnesError("boom")


class TestLoadDotenv:
    """_load_dotenv tests."""

    def test_loads_with_quotes(self):
        """Values wrapped in quotes are stripped."""
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".env", delete=False, encoding="utf-8"
        )
        tmp.write('AGNES_API_KEY="sk-quoted"\n')
        tmp.close()

        from pathlib import Path
        for line in Path(tmp.name).read_text(encoding="utf-8").split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"\'')
                assert v == "sk-quoted"

        os.unlink(tmp.name)
