from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

CDP_URL = "http://127.0.0.1:9222"

ASSISTANT_SELECTORS = (
    '[data-message-author-role="assistant"]',
    'article[data-testid^="conversation-turn-"] [data-message-author-role="assistant"]',
)

STOP_SELECTORS = (
    'button[data-testid="stop-button"]',
    'button[aria-label*="Stop"]',
    'button[aria-label*="停止"]',
)

CHATGPT_HOSTS = (
    "chatgpt.com",
    "chat.openai.com",
)


@dataclass
class ChatGPTConnection:
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page

    async def close(self) -> None:
        await self.playwright.stop()


async def connect_chatgpt() -> ChatGPTConnection:
    playwright = await async_playwright().start()

    try:
        browser = await playwright.chromium.connect_over_cdp(
            CDP_URL,
            timeout=15_000,
        )
    except Exception:
        await playwright.stop()
        raise RuntimeError(
            "无法连接 Edge CDP。请确认 Edge 使用以下参数启动：\n"
            "msedge.exe --remote-debugging-port=9222 "
            "--user-data-dir=C:\\crux-edge-profile"
        ) from None

    if not browser.contexts:
        await playwright.stop()
        raise RuntimeError("已连接 Edge，但没有可用的浏览器上下文。")

    context = browser.contexts[0]
    pages = context.pages

    for page in reversed(pages):
        url = page.url.lower()
        if any(host in url for host in CHATGPT_HOSTS):
            await page.bring_to_front()
            return ChatGPTConnection(
                playwright=playwright,
                browser=browser,
                context=context,
                page=page,
            )

    await playwright.stop()
    raise RuntimeError("没有找到已打开的 ChatGPT 页面。")


async def get_assistant_elements(page: Page):
    for selector in ASSISTANT_SELECTORS:
        locator = page.locator(selector)
        if await locator.count() > 0:
            return locator

    return page.locator(ASSISTANT_SELECTORS[0])


async def get_assistant_count(page: Page) -> int:
    locator = await get_assistant_elements(page)
    return await locator.count()


async def is_generating(page: Page) -> bool:
    for selector in STOP_SELECTORS:
        locator = page.locator(selector)
        try:
            if await locator.count() > 0 and await locator.first.is_visible():
                return True
        except Exception:
            continue

    return False


async def extract_latest_reply(page: Page) -> str:
    locator = await get_assistant_elements(page)
    count = await locator.count()

    if count == 0:
        return ""

    body_selectors = (
        ".markdown",
        '[class*="markdown"]',
        '[data-message-author-role="assistant"] .prose',
    )

    # Iterate from the last element backwards to skip empty placeholder elements
    # (ChatGPT creates empty assistant containers before generation starts)
    for idx in range(count - 1, -1, -1):
        el = locator.nth(idx)

        for selector in body_selectors:
            body = el.locator(selector)
            try:
                if await body.count() > 0:
                    text = (await body.first.inner_text()).strip()
                    if text:
                        return text
            except Exception:
                continue

        # Fallback: try inner_text directly
        try:
            text = (await el.inner_text()).strip()
            if text:
                return text
        except Exception:
            continue

    return ""


async def wait_for_latest_reply(
    page: Page,
    baseline_count: int | None = None,
    timeout_seconds: float = 180.0,
    stable_checks_required: int = 4,
    poll_interval: float = 0.7,
) -> str:
    deadline = time.monotonic() + timeout_seconds

    last_text = ""
    stable_checks = 0
    new_message_seen = baseline_count is None

    while time.monotonic() < deadline:
        try:
            current_count = await get_assistant_count(page)

            if baseline_count is None:
                new_message_seen = current_count > 0
            elif current_count > baseline_count:
                new_message_seen = True

            if not new_message_seen:
                await asyncio.sleep(poll_interval)
                continue

            text = await extract_latest_reply(page)
            generating = await is_generating(page)

            if text:
                if text == last_text:
                    stable_checks += 1
                else:
                    last_text = text
                    stable_checks = 0

                if not generating and stable_checks >= stable_checks_required:
                    return text

            await asyncio.sleep(poll_interval)

        except Exception:
            await asyncio.sleep(1.0)

    if last_text:
        return last_text

    raise TimeoutError("未能从 ChatGPT 页面取得回复。")


async def fetch_reply_already_generated() -> str:
    connection = await connect_chatgpt()

    try:
        await connection.page.wait_for_load_state(
            "domcontentloaded",
            timeout=10_000,
        )
    except Exception:
        import logging

        logging.getLogger("crux").debug("silent except", exc_info=True)

    try:
        reply = await wait_for_latest_reply(
            page=connection.page,
            baseline_count=None,
            timeout_seconds=30,
        )

        if not reply:
            raise RuntimeError("找到了 ChatGPT 页面，但最新回复内容为空。")

        return reply
    finally:
        await connection.close()


async def ask_and_fetch(
    send_question_callback,
    timeout_seconds: float = 180.0,
) -> str:
    connection = await connect_chatgpt()

    try:
        page = connection.page
        baseline_count = await get_assistant_count(page)

        await send_question_callback(page)

        return await wait_for_latest_reply(
            page=page,
            baseline_count=baseline_count,
            timeout_seconds=timeout_seconds,
        )
    finally:
        await connection.close()


async def main() -> None:
    try:
        reply = await fetch_reply_already_generated()
        print("\n========== GPT 最新回复 ==========\n")
        print(reply)
        print("\n=================================\n")
    except Exception as exc:
        print(f"取回失败：{exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    asyncio.run(main())
