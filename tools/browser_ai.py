#!/usr/bin/env python3
"""Browser AI Connector — standalone CDP bridge to ChatGPT / Gemini / etc.
Zero CRUX dependency. Only needs: pip install playwright && playwright install chromium.

Usage from any AI tool:
    from browser_ai import send_to_ai
    reply = send_to_ai("chatgpt", "Write a haiku about coding")
    print(reply)

Or as CLI:
    python browser_ai.py chatgpt "Write a haiku about coding"
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

# ── Config ────────────────────────────────────────────────────────
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not Path(EDGE_PATH).exists():
    EDGE_PATH = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
USER_DATA = str(Path.home() / "edge-debug-profile")
DEFAULT_TIMEOUT = 120

PlatformName = Literal["chatgpt", "gemini", "kling", "jimeng", "runway", "luma"]

PLATFORMS: dict[str, dict] = {
    "chatgpt": {
        "url": "https://chatgpt.com",
        "input": '[contenteditable="true"]',
        "submit": "Enter",
        "response": '[data-message-author-role="assistant"]',
        "stop_button": '[data-testid="stop-button"]',
    },
    "gemini": {
        "url": "https://gemini.google.com",
        "input": 'div.ql-editor[contenteditable="true"]',
        "submit": "click",
        "submit_selector": '[aria-label="Send message"]',
        "response": ".message-content",
        "stop_button": '[aria-label="Stop"]',
    },
}


# ── Core functions ─────────────────────────────────────────────────


def _connect():
    """Connect to browser via CDP (launch Edge if needed). Returns (playwright, context)."""
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()

    # Try existing CDP session first
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=5000)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        return pw, ctx
    except Exception:
        import logging

        logging.getLogger(__name__).debug("silent except", exc_info=True)

    # Launch Edge with CDP
    subprocess.Popen(
        [
            EDGE_PATH,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={USER_DATA}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(4)

    browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=15000)
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    return pw, ctx


def _find_or_create_page(ctx, platform: str):
    """Find an existing page for the platform or create one."""
    cfg = PLATFORMS[platform]
    for page in ctx.pages:
        if cfg["url"].split("//")[1].split("/")[0] in page.url:
            page.bring_to_front()
            return page
    page = ctx.new_page()
    page.goto(cfg["url"], wait_until="domcontentloaded")
    time.sleep(2)
    return page


def _fill(page, text: str, platform: str):
    """Fill prompt using JS evaluate (fast) with keyboard fallback."""
    cfg = PLATFORMS[platform]
    try:
        page.evaluate(f"""() => {{
            const el = document.querySelector('{cfg["input"]}');
            if (el) {{
                el.focus();
                // contenteditable: set textContent then dispatch input
                if (el.getAttribute('contenteditable') !== null) {{
                    el.textContent = {json.dumps(text)};
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                }} else {{
                    el.value = {json.dumps(text)};
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                }}
                return true;
            }}
            return false;
        }}""")
        return True
    except Exception:
        # Fallback: keyboard typing
        el = page.locator(cfg["input"]).first
        el.click()
        time.sleep(0.2)
        page.keyboard.type(text, delay=5)
        return True


def _submit(page, platform: str):
    """Submit the prompt."""
    cfg = PLATFORMS[platform]
    if cfg["submit"] == "Enter":
        page.keyboard.press("Enter")
    else:
        page.locator(cfg["submit_selector"]).first.click()


def _count_messages(page, platform: str) -> int:
    """Count existing assistant messages on the page."""
    cfg = PLATFORMS[platform]
    try:
        return page.evaluate(f"""() => {{
            return document.querySelectorAll('{cfg["response"]}').length;
        }}""")
    except Exception:
        return 0


def _read_response(page, platform: str, timeout: int):
    """Poll for NEW assistant response. Returns text or empty string on timeout.

    Fix: Uses platform-specific selectors. Only returns when stop button
    disappears (generation done) AND text is substantive.
    """
    cfg = PLATFORMS[platform]
    t0 = time.monotonic()
    last_len = 0
    stable_count = 0

    while time.monotonic() - t0 < timeout:
        time.sleep(2)
        try:
            result = page.evaluate(f"""() => {{
                const msgs = document.querySelectorAll('{cfg["response"]}');
                if (msgs.length > 0) {{
                    const last = msgs[msgs.length - 1];
                    const text = last.textContent || '';
                    const stopped = !document.querySelector('{cfg["stop_button"]}');
                    return JSON.stringify({{done: stopped, text: text, count: msgs.length}});
                }}
                return JSON.stringify({{done: false, text: '', count: 0}});
            }}""")
            data = json.loads(result)
            current_len = len(data["text"])

            # Stop button disappeared + text substantive -> generation complete
            if data["done"] and current_len > 10:
                return data["text"]

            # Stability: text unchanged for 3 consecutive polls -> end of stream
            if current_len == last_len and current_len > 0:
                stable_count += 1
                if stable_count >= 3:
                    return data["text"] if data["text"] else ""
            else:
                stable_count = 0
            last_len = current_len
        except Exception:
            import logging

            logging.getLogger(__name__).debug("silent except", exc_info=True)
    return ""


# ── Public API ─────────────────────────────────────────────────────


def send_to_ai(
    platform: PlatformName = "chatgpt",
    prompt: str = "",
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Send a prompt to an AI platform and return the reply.

    Args:
        platform: One of chatgpt, gemini.
        prompt: The text to send.
        timeout: Maximum wait time in seconds.

    Returns:
        The AI's text response, or empty string on failure/timeout.

    Example:
        reply = send_to_ai("chatgpt", "Write a Python function", timeout=120)
    """
    if platform not in PLATFORMS:
        return f"Unknown platform: {platform}. Valid: {', '.join(PLATFORMS)}"

    pw = None
    try:
        pw, ctx = _connect()
        page = _find_or_create_page(ctx, platform)
        _fill(page, prompt, platform)
        _submit(page, platform)
        return _read_response(page, platform, timeout)
    except Exception as e:
        return f"Error: {e}"
    finally:
        if pw:
            try:
                pw.stop()
            except Exception:
                import logging

                logging.getLogger(__name__).debug("silent except", exc_info=True)


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python browser_ai.py <platform> <prompt>")
        print(f"Platforms: {', '.join(PLATFORMS)}")
        sys.exit(1)

    plat = sys.argv[1]
    text = sys.argv[2] if len(sys.argv) > 2 else "Hello, who are you?"
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_TIMEOUT

    print(f"Sending to {plat}...")
    reply = send_to_ai(plat, text, timeout=timeout)

    # Windows GBK console compatibility
    try:
        print(reply)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(reply)
