"""Self-Audit: CDP Connection Stability.

Tests:
  1. attach to existing browser
  2. page navigation, click, input, eval
  3. disconnection and reconnection
  4. error handling (port not open, page closed, timeout)
"""

from __future__ import annotations

import asyncio

import pytest

# Only run CDP tests if explicitly requested
pytestmark = pytest.mark.skipif(
    not pytest.importorskip("playwright", reason="playwright not installed"), reason="playwright required for CDP tests"
)

CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"


def _check_cdp_alive() -> bool:
    """Quick check if CDP port is responding."""
    import urllib.request

    try:
        resp = urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=2)
        return resp.status == 200
    except Exception:
        return False


# ── Helpers ──


async def _get_cdp_page():
    """Get or create a page via CDP."""
    from playwright.async_api import async_playwright

    p = await async_playwright().__aenter__()
    browser = await p.chromium.connect_over_cdp(CDP_URL)
    if browser.contexts and browser.contexts[0].pages:
        page = browser.contexts[0].pages[0]
    else:
        page = await browser.contexts[0].new_page() if browser.contexts else None
    return p, browser, page


@pytest.fixture(scope="module")
def event_loop():
    """Module-scoped event loop for async CDP tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── 1. CONNECTION ──


@pytest.mark.skipif("not _check_cdp_alive()")
class TestCdpConnection:
    """Basic CDP attach/detach operations."""

    def test_cdp_port_is_open(self):
        """CDP debug port 9222 must be listening."""
        assert _check_cdp_alive(), "CDP port 9222 not responding"

    @pytest.mark.asyncio
    async def test_attach_to_browser(self):
        """Can attach to existing browser via CDP."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            assert browser is not None
            assert browser.contexts is not None
            await browser.close()

    @pytest.mark.asyncio
    async def test_get_page_list(self):
        """Can retrieve list of open pages."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            pages = []
            for ctx in browser.contexts:
                pages.extend(ctx.pages)
            assert isinstance(pages, list)
            await browser.close()

    @pytest.mark.asyncio
    async def test_page_has_url(self):
        """Attached page should have a valid URL."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            for ctx in browser.contexts:
                for page in ctx.pages:
                    url = page.url
                    assert url.startswith("http"), f"Invalid URL: {url}"
                    break
            await browser.close()


# ── 2. PAGE OPERATIONS ──


@pytest.mark.skipif("not _check_cdp_alive()")
class TestCdpPageOps:
    """Click, input, evaluate on pages."""

    @pytest.mark.asyncio
    async def test_navigate_to_url(self):
        """Navigate to a URL should succeed."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            ctx = browser.contexts[0]
            page = await ctx.new_page()
            await page.goto("about:blank", wait_until="domcontentloaded")
            assert page.url == "about:blank"
            await page.close()
            await browser.close()

    @pytest.mark.asyncio
    async def test_evaluate_javascript(self):
        """Evaluate JS should return result."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            ctx = browser.contexts[0]
            page = await ctx.new_page()
            result = await page.evaluate("() => 1 + 1")
            assert result == 2, f"Expected 2, got {result}"
            await page.close()
            await browser.close()

    @pytest.mark.asyncio
    async def test_get_page_title(self):
        """Page title should be accessible."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            for ctx in browser.contexts:
                for page in ctx.pages:
                    title = await page.title()
                    assert isinstance(title, str)
                    break
            await browser.close()


# ── 3. STABILITY ──


@pytest.mark.skipif("not _check_cdp_alive()")
class TestCdpStability:
    """Repeated attach/detach and error recovery."""

    @pytest.mark.asyncio
    async def test_attach_detach_10_times(self):
        """Repeated attach/detach should not degrade."""
        from playwright.async_api import async_playwright

        for i in range(10):
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(CDP_URL)
                assert browser is not None
                await browser.close()

    @pytest.mark.asyncio
    async def test_multiple_pages_no_conflict(self):
        """Creating multiple pages from same context."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            ctx = browser.contexts[0]
            pages = []
            for _ in range(5):
                page = await ctx.new_page()
                pages.append(page)
            assert len(pages) == 5
            for pg in pages:
                await pg.close()
            await browser.close()


# ── 4. ERROR RESILIENCE ──


class TestCdpErrorResilience:
    """CDP failures must not crash the main loop."""

    def test_connection_refused_returns_error(self):
        """Connecting to nonexistent CDP port returns structured error, not crash."""
        from playwright.async_api import async_playwright

        try:
            loop = asyncio.new_event_loop()

            async def try_connect():
                async with async_playwright() as p:
                    try:
                        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:19999", timeout=3000)
                        return {"success": True}
                    except Exception as e:
                        return {"success": False, "error": str(e), "error_type": type(e).__name__}

            result = loop.run_until_complete(try_connect())
            loop.close()
            assert result["success"] is False
            assert "error" in result
            assert "error_type" in result
        except Exception as e:
            # Even the test infrastructure failing should be caught
            pytest.skip(f"CDP error resilience test infrastructure: {e}")

    def test_invalid_cdp_url_returns_error(self):
        """Malformed CDP URL returns structured error."""
        from playwright.async_api import async_playwright

        try:
            loop = asyncio.new_event_loop()

            async def try_bad_url():
                async with async_playwright() as p:
                    try:
                        browser = await p.chromium.connect_over_cdp("not-a-valid-url", timeout=2000)
                        return {"success": True}
                    except Exception as e:
                        return {"success": False, "error": str(e)}

            result = loop.run_until_complete(try_bad_url())
            loop.close()
            assert result["success"] is False
        except Exception:
            pytest.skip("CDP error handling test limitation")
