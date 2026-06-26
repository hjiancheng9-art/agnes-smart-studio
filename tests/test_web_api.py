"""Smoke tests for core/web_api.py — FastAPI REST interface.

Tests cover:
- Module imports, HAS_FASTAPI guard, ROOT constant
- App creation and structure (when FastAPI available)
- start_server() function signature
- _get_session / _reset_session helpers
"""

from unittest.mock import patch

import pytest


class TestModuleImports:
    def test_module_imports(self):
        import core.web_api as wa

        assert hasattr(wa, "ROOT")
        assert hasattr(wa, "app")
        assert hasattr(wa, "start_server")
        assert hasattr(wa, "HAS_FASTAPI")

    def test_has_fastapi_is_bool(self):
        from core.web_api import HAS_FASTAPI

        assert isinstance(HAS_FASTAPI, bool)

    def test_root_is_path(self):
        from core.web_api import ROOT

        from pathlib import Path

        assert isinstance(ROOT, Path)
        assert ROOT.exists()

    def test_version_import(self):
        from core.web_api import __version__

        assert isinstance(__version__, str)
        assert len(__version__) > 0


class TestAppState:
    def test_app_none_when_no_fastapi(self):
        """If FastAPI not installed, app should be None."""
        from core.web_api import HAS_FASTAPI, app

        if not HAS_FASTAPI:
            assert app is None


class TestSessionHelpers:
    def test_get_session_creates_session(self):
        from core.web_api import _get_session

        # Reset first
        from core.web_api import _reset_session

        _reset_session()
        session = _get_session()
        assert session is not None
        _reset_session()

    def test_get_session_reuses(self):
        from core.web_api import _get_session, _reset_session

        _reset_session()
        s1 = _get_session()
        s2 = _get_session()
        assert s1 is s2
        _reset_session()

    def test_reset_session(self):
        from core.web_api import _get_session, _reset_session

        _get_session()
        _reset_session()
        # After reset, next call should create a new one
        session = _get_session()
        assert session is not None
        _reset_session()


@pytest.mark.skipif(not pytest.importorskip("fastapi"), reason="FastAPI not installed")
class TestFastAPIRoutes:
    """Tests that only run when FastAPI is available."""

    def test_app_is_fastapi_instance(self):
        from fastapi import FastAPI

        from core.web_api import app

        assert isinstance(app, FastAPI)

    def test_health_route_exists(self):
        from core.web_api import app

        routes = [r.path for r in app.routes]
        assert "/health" in routes

    def test_capability_route_exists(self):
        from core.web_api import app

        routes = [r.path for r in app.routes]
        assert "/capability" in routes

    def test_chat_route_exists(self):
        from core.web_api import app

        routes = [r.path for r in app.routes]
        assert "/chat" in routes

    def test_chat_stream_route_exists(self):
        from core.web_api import app

        routes = [r.path for r in app.routes]
        assert "/chat/stream" in routes

    def test_self_audit_route_exists(self):
        from core.web_api import app

        routes = [r.path for r in app.routes]
        assert "/self/audit" in routes

    def test_eval_route_exists(self):
        from core.web_api import app

        routes = [r.path for r in app.routes]
        assert "/eval" in routes

    def test_tools_score_route_exists(self):
        from core.web_api import app

        routes = [r.path for r in app.routes]
        assert "/tools/score" in routes

    def test_rag_search_route_exists(self):
        from core.web_api import app

        routes = [r.path for r in app.routes]
        assert "/rag/search" in routes

    def test_app_title(self):
        from core.web_api import app

        assert "CRUX" in app.title


class TestStartServer:
    def test_start_server_no_fastapi(self):
        from core.web_api import start_server

        # Patch HAS_FASTAPI to False
        with patch("core.web_api.HAS_FASTAPI", False):
            # Should print message and return
            result = start_server()
            assert result is None

    def test_start_server_signature(self):
        from core.web_api import start_server

        import inspect

        sig = inspect.signature(start_server)
        assert "host" in sig.parameters
        assert "port" in sig.parameters
        defaults = {k: v.default for k, v in sig.parameters.items() if v.default is not inspect.Parameter.empty}
        assert defaults.get("host") == "127.0.0.1"
        assert defaults.get("port") == 8420
