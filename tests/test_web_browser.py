"""Smoke tests for core/web_browser.py — Playwright browser automation tools.

Tests cover:
- Module imports and __all__ exports
- Tool definitions structure (BROWSER_GENERAL_TOOL_DEFS)
- Executor map structure (BROWSER_GENERAL_EXECUTOR_MAP)
- Error/validation paths of all executor functions (no real browser needed)
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.web_browser import (
    BROWSER_GENERAL_EXECUTOR_MAP,
    BROWSER_GENERAL_TOOL_DEFS,
    execute_browser_click,
    execute_browser_close,
    execute_browser_extract,
    execute_browser_fill,
    execute_browser_navigate,
    execute_browser_screenshot,
    execute_browser_scroll,
    execute_browser_wait_for,
)


class TestModuleStructure:
    def test_tool_defs_count(self):
        assert len(BROWSER_GENERAL_TOOL_DEFS) == 8

    def test_tool_def_names(self):
        names = {t["function"]["name"] for t in BROWSER_GENERAL_TOOL_DEFS}
        expected = {
            "browser_navigate",
            "browser_click",
            "browser_fill",
            "browser_screenshot",
            "browser_extract",
            "browser_scroll",
            "browser_wait_for",
            "browser_close",
        }
        assert names == expected

    def test_executor_map_keys_match(self):
        def_names = {t["function"]["name"] for t in BROWSER_GENERAL_TOOL_DEFS}
        assert set(BROWSER_GENERAL_EXECUTOR_MAP.keys()) == def_names

    def test_executor_map_values_callable(self):
        for name, fn in BROWSER_GENERAL_EXECUTOR_MAP.items():
            assert callable(fn), f"{name} executor is not callable"

    def test_tool_defs_have_function_type(self):
        for t in BROWSER_GENERAL_TOOL_DEFS:
            assert t["type"] == "function"
            assert "function" in t


class TestBrowserNavigate:
    def test_navigate_no_url(self):
        result = json.loads(execute_browser_navigate())
        assert "error" in result
        assert "url required" in result["error"]

    def test_navigate_empty_url(self):
        result = json.loads(execute_browser_navigate(url=""))
        assert "error" in result

    @patch("core.file_tools._validate_url", return_value="blocked")
    def test_navigate_invalid_url_rejected(self, mock_validate):
        result = json.loads(execute_browser_navigate(url="http://evil.com"))
        assert "error" in result
        assert "\u5b89\u5168\u62d2\u7edd" in result["error"]

    @patch("core.web_browser._get_browser", side_effect=TypeError("no browser"))
    def test_navigate_browser_error(self, mock_browser):
        with patch("core.file_tools._validate_url", return_value=None):
            result = json.loads(execute_browser_navigate(url="http://example.com"))
            assert "error" in result


class TestBrowserClick:
    def test_click_no_selector(self):
        result = json.loads(execute_browser_click())
        assert "error" in result
        assert "selector required" in result["error"]

    def test_click_empty_selector(self):
        result = json.loads(execute_browser_click(selector=""))
        assert "error" in result

    @patch("core.web_browser._get_browser", side_effect=TypeError("no browser"))
    def test_click_browser_error(self, mock_browser):
        result = json.loads(execute_browser_click(selector="#btn"))
        assert "error" in result


class TestBrowserFill:
    def test_fill_no_selector(self):
        result = json.loads(execute_browser_fill())
        assert "error" in result
        assert "selector required" in result["error"]

    def test_fill_empty_selector(self):
        result = json.loads(execute_browser_fill(selector=""))
        assert "error" in result

    @patch("core.web_browser._get_browser", side_effect=TypeError("no browser"))
    def test_fill_browser_error(self, mock_browser):
        result = json.loads(execute_browser_fill(selector="#input", text="hello"))
        assert "error" in result


class TestBrowserScreenshot:
    @patch("core.web_browser._get_browser", side_effect=TypeError("no browser"))
    def test_screenshot_browser_error(self, mock_browser):
        result = json.loads(execute_browser_screenshot())
        assert "error" in result


class TestBrowserExtract:
    @patch("core.web_browser._get_browser", side_effect=TypeError("no browser"))
    def test_extract_browser_error(self, mock_browser):
        result = json.loads(execute_browser_extract(selector="body"))
        assert "error" in result


class TestBrowserScroll:
    @patch("core.web_browser._get_browser", side_effect=TypeError("no browser"))
    def test_scroll_browser_error(self, mock_browser):
        result = json.loads(execute_browser_scroll(direction="down", amount=500))
        assert "error" in result

    @patch("core.web_browser._get_browser")
    def test_scroll_invalid_direction(self, mock_browser):
        page = MagicMock()
        mock_browser.return_value = page
        result = json.loads(execute_browser_scroll(direction="sideways"))
        assert "error" in result
        assert "direction" in result["error"].lower() or "up" in result["error"]


class TestBrowserWaitFor:
    def test_wait_no_selector(self):
        result = json.loads(execute_browser_wait_for())
        assert "error" in result
        assert "selector required" in result["error"]

    def test_wait_empty_selector(self):
        result = json.loads(execute_browser_wait_for(selector=""))
        assert "error" in result

    @patch("core.web_browser._get_browser", side_effect=TypeError("no browser"))
    def test_wait_browser_error(self, mock_browser):
        result = json.loads(execute_browser_wait_for(selector="#load"))
        assert "error" in result


class TestBrowserClose:
    @patch("core.web_browser._close_browser")
    def test_close_calls_close(self, mock_close):
        result = json.loads(execute_browser_close())
        mock_close.assert_called_once()
        assert result["status"] == "closed"


class TestExecutorMapIntegration:
    def test_navigate_executor(self):
        result = json.loads(BROWSER_GENERAL_EXECUTOR_MAP["browser_navigate"]())
        assert "error" in result

    def test_click_executor(self):
        result = json.loads(BROWSER_GENERAL_EXECUTOR_MAP["browser_click"]())
        assert "error" in result

    def test_fill_executor(self):
        result = json.loads(BROWSER_GENERAL_EXECUTOR_MAP["browser_fill"]())
        assert "error" in result

    def test_screenshot_executor(self):
        # screenshot has no required params, may raise browser error
        result = json.loads(BROWSER_GENERAL_EXECUTOR_MAP["browser_screenshot"]())
        assert "error" in result or "saved" in result

    def test_extract_executor(self):
        result = json.loads(BROWSER_GENERAL_EXECUTOR_MAP["browser_extract"]())
        assert "error" in result or "content" in result

    def test_scroll_executor(self):
        result = json.loads(BROWSER_GENERAL_EXECUTOR_MAP["browser_scroll"]())
        assert "error" in result or "scrolled" in result

    def test_wait_for_executor(self):
        result = json.loads(BROWSER_GENERAL_EXECUTOR_MAP["browser_wait_for"]())
        assert "error" in result

    def test_close_executor(self):
        with patch("core.web_browser._close_browser"):
            result = json.loads(BROWSER_GENERAL_EXECUTOR_MAP["browser_close"]())
            assert result["status"] == "closed"
