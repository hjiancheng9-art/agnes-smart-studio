"""General-purpose browser automation tools.

Provides universal web interaction primitives:
- navigate(url): open a page
- click(selector): click an element
- fill(selector, text): fill input fields
- screenshot(filename): capture page screenshot
- extract(selector): extract text/content from page
- scroll(direction, amount): scroll the page
- wait_for(selector, timeout): wait for element to appear

Uses Playwright (already installed for browser_tools.py).
Falls back gracefully if Playwright is not available.
"""

import contextlib
import json
import threading

__all__ = [
    "BROWSER_GENERAL_EXECUTOR_MAP",
    "BROWSER_GENERAL_TOOL_DEFS",
    "execute_browser_click",
    "execute_browser_close",
    "execute_browser_extract",
    "execute_browser_fill",
    "execute_browser_navigate",
    "execute_browser_screenshot",
    "execute_browser_scroll",
    "execute_browser_wait_for",
    "reset_web_browser",
]

# ======================================================================
# Browser session management
# ======================================================================

_browser = None
_page = None
_browser_lock = threading.Lock()


def _get_browser():
    """Get or create a persistent browser instance (thread-safe)."""
    global _browser, _page
    with _browser_lock:
        if _page is not None:
            # Verify the page is still alive; if crashed, recreate
            try:
                _page.title()
                return _page
            except (RuntimeError, OSError) as e:
                logger.debug("Browser page stale: %s", e)
                _page = None
                _browser = None

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            ) from None

        pw = sync_playwright().start()
        _browser = pw.chromium.launch(headless=True)
        _page = _browser.new_page(viewport={"width": 1280, "height": 720})
        return _page


def _close_browser():
    """Close the browser session (thread-safe)."""
    global _browser, _page
    with _browser_lock:
        if _page:
            with contextlib.suppress(OSError, RuntimeError, ValueError):
                _page.close()
        if _browser:
            with contextlib.suppress(OSError, RuntimeError, ValueError):
                _browser.close()
        _page = None
        _browser = None


def reset_web_browser() -> None:
    """Tear down the shared browser session (test isolation / hot reload).

    Closes the persistent Playwright browser/page (real Chromium subprocess)
    and drops the module-level references. Safe to call when no session is
    open.
    """
    _close_browser()


# ======================================================================
# Tool executors
# ======================================================================


def execute_browser_navigate(url: str = "", wait: int = 3) -> str:
    """Navigate to a URL and return page title + initial text."""
    if not url:
        return json.dumps({"error": "url required"})

    from core.file_tools import _validate_url

    err = _validate_url(url)
    if err:
        return json.dumps({"error": f"[安全拒绝] {err}"})

    try:
        page = _get_browser()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if wait > 0:
            page.wait_for_timeout(wait * 1000)

        title = page.title()
        text = page.inner_text("body")[:3000]

        return json.dumps(
            {
                "url": url,
                "title": title,
                "text_preview": text,
                "status": "loaded",
            },
            ensure_ascii=False,
            indent=2,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)


def execute_browser_click(selector: str = "", wait: int = 2) -> str:
    """Click an element by CSS selector."""
    if not selector:
        return json.dumps({"error": "selector required"})

    try:
        page = _get_browser()
        page.click(selector, timeout=10000)
        if wait > 0:
            page.wait_for_timeout(wait * 1000)

        return json.dumps(
            {
                "clicked": selector,
                "url": page.url,
                "title": page.title(),
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e), "selector": selector}, ensure_ascii=False)


def execute_browser_fill(selector: str = "", text: str = "", submit: bool = False) -> str:
    """Fill an input field and optionally submit the form."""
    if not selector:
        return json.dumps({"error": "selector required"})

    try:
        page = _get_browser()
        page.fill(selector, text, timeout=10000)
        if submit:
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)

        return json.dumps(
            {
                "filled": selector,
                "text": text[:200],
                "submitted": submit,
                "url": page.url if submit else None,
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e), "selector": selector}, ensure_ascii=False)


def execute_browser_screenshot(filename: str = "", full_page: bool = False) -> str:
    """Take a screenshot of the current page."""
    try:
        page = _get_browser()
        if not filename:
            from datetime import datetime

            from core.config import OUTPUT_DIR

            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            save_path = str(OUTPUT_DIR / "images" / filename)
        else:
            save_path = filename

        page.screenshot(path=save_path, full_page=full_page)

        return json.dumps(
            {
                "saved": save_path,
                "full_page": full_page,
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def execute_browser_extract(selector: str = "", attribute: str = "text") -> str:
    """Extract content from page elements.

    selector: CSS selector (empty = whole page body)
    attribute: "text", "html", "href", "src", or any attribute name
    """
    try:
        page = _get_browser()

        if not selector:
            selector = "body"

        if attribute == "text":
            content = page.inner_text(selector)[:5000]
        elif attribute == "html":
            content = page.inner_html(selector)[:5000]
        elif attribute in ("href", "src"):
            elements = page.query_selector_all(selector)
            content = json.dumps(
                [el.get_attribute(attribute) for el in elements if el.get_attribute(attribute)], ensure_ascii=False
            )
        else:
            elements = page.query_selector_all(selector)
            content = json.dumps(
                [el.get_attribute(attribute) for el in elements if el.get_attribute(attribute)], ensure_ascii=False
            )

        return json.dumps(
            {
                "selector": selector,
                "attribute": attribute,
                "content": content,
                "url": page.url,
            },
            ensure_ascii=False,
            indent=2,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e), "selector": selector}, ensure_ascii=False)


def execute_browser_scroll(direction: str = "down", amount: int = 500) -> str:
    """Scroll the page in a direction by amount of pixels."""
    try:
        page = _get_browser()
        if direction == "down":
            page.mouse.wheel(0, amount)
        elif direction == "up":
            page.mouse.wheel(0, -amount)
        else:
            return json.dumps({"error": "direction must be 'up' or 'down'"})

        page.wait_for_timeout(500)

        return json.dumps(
            {
                "scrolled": direction,
                "amount": amount,
                "url": page.url,
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def execute_browser_wait_for(selector: str = "", timeout: int = 10) -> str:
    """Wait for an element to appear on the page."""
    if not selector:
        return json.dumps({"error": "selector required"})

    try:
        page = _get_browser()
        page.wait_for_selector(selector, timeout=timeout * 1000)

        return json.dumps(
            {
                "found": True,
                "selector": selector,
                "url": page.url,
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps(
            {
                "found": False,
                "selector": selector,
                "error": str(e),
            },
            ensure_ascii=False,
        )


def execute_browser_close() -> str:
    """Close the browser session."""
    _close_browser()
    return json.dumps({"status": "closed"}, ensure_ascii=False)


# ======================================================================
# Tool definitions for ToolRegistry
# ======================================================================

BROWSER_GENERAL_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Open a webpage and return its title and text content. Use for reading documentation, checking web apps, or starting a browser session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "wait": {"type": "integer", "description": "Seconds to wait for page load (default: 3)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element on the page by CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of element to click"},
                    "wait": {"type": "integer", "description": "Seconds to wait after click (default: 2)"},
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill",
            "description": "Fill an input field with text, optionally submit the form.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of input field"},
                    "text": {"type": "string", "description": "Text to enter"},
                    "submit": {"type": "boolean", "description": "Press Enter after filling (default: false)"},
                },
                "required": ["selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Take a screenshot of the current page. Saves as PNG file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Output filename (default: auto-generated)"},
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full page or just viewport (default: false)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_extract",
            "description": "Extract content from page elements (text, HTML, or attributes like href/src).",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector (empty = body)"},
                    "attribute": {
                        "type": "string",
                        "description": "What to extract: text, html, href, src (default: text)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the page up or down by a number of pixels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "description": "up or down"},
                    "amount": {"type": "integer", "description": "Pixels to scroll (default: 500)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait_for",
            "description": "Wait for an element to appear on the page. Useful for SPAs with dynamic content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector to wait for"},
                    "timeout": {"type": "integer", "description": "Max wait seconds (default: 10)"},
                },
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "Close the browser session and free resources.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

BROWSER_GENERAL_EXECUTOR_MAP = {
    "browser_navigate": lambda **kw: execute_browser_navigate(url=kw.get("url", ""), wait=kw.get("wait", 3)),
    "browser_click": lambda **kw: execute_browser_click(selector=kw.get("selector", ""), wait=kw.get("wait", 2)),
    "browser_fill": lambda **kw: execute_browser_fill(
        selector=kw.get("selector", ""), text=kw.get("text", ""), submit=kw.get("submit", False)
    ),
    "browser_screenshot": lambda **kw: execute_browser_screenshot(
        filename=kw.get("filename", ""), full_page=kw.get("full_page", False)
    ),
    "browser_extract": lambda **kw: execute_browser_extract(
        selector=kw.get("selector", ""), attribute=kw.get("attribute", "text")
    ),
    "browser_scroll": lambda **kw: execute_browser_scroll(
        direction=kw.get("direction", "down"), amount=kw.get("amount", 500)
    ),
    "browser_wait_for": lambda **kw: execute_browser_wait_for(
        selector=kw.get("selector", ""), timeout=kw.get("timeout", 10)
    ),
    "browser_close": lambda **kw: execute_browser_close(),
}
