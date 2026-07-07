#!/usr/bin/env python
"""Launch Chrome via Playwright with Profile 4 user data, read ChatGPT conversation."""

import asyncio
import os

from playwright.async_api import async_playwright

USER_DATA = r"C:\Users\huangjiancheng\AppData\Local\Google\Chrome\User Data"

async def main():
    async with async_playwright() as p:
        print("Launching Chrome with Profile 4 user data...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA,
            headless=False,
            channel="chrome",
            args=[
                "--profile-directory=Profile 4",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        print("Chrome launched!")

        page = context.pages[0] if context.pages else await context.new_page()
        print(f"Using page: {page.url}")

        await page.goto("https://chatgpt.com", wait_until="networkidle", timeout=90000)
        print(f"Navigated to: {page.url}")
        print(f"Title: {await page.title()}")

        await asyncio.sleep(5)

        screenshot_path = r"C:\Users\huangjiancheng\agnes-smart-studio\output\chatgpt_final.png"
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot: {screenshot_path}")

        # Get page text
        text = await page.evaluate("() => document.body.innerText")
        print(f"\n=== Page Text ({len(text)} chars) ===")
        print(text[:5000])

        # Look for the conversation
        print("\n=== Searching for 'CRUX Studio架构诊断' ===")
        result = await page.evaluate("""(searchTerm) => {
            const body = document.body.innerText;
            const idx = body.indexOf(searchTerm);
            if (idx >= 0) {
                return body.substring(Math.max(0, idx-200), idx + 500);
            }
            return null;
        }""", "CRUX Studio")

        if result:
            print(f"FOUND:\n{result}")
        else:
            print("Not found directly. Looking at conversation history...")

            # Try different selectors for conversation history
            selectors = [
                'nav a[href*="/c/"]',
                'a[href*="/c/"]',
                '[data-testid="history-item"]',
                'nav li a',
                'ol li a',
                'ul li a',
                'a:has(div)',
            ]

            for sel in selectors:
                items = await page.evaluate(f"""(sel) => {{
                    const elements = document.querySelectorAll(sel);
                    return Array.from(elements).slice(0, 30).map(el => ({{
                        text: (el.innerText || el.textContent || '').trim().substring(0, 100),
                        href: el.getAttribute('href') || ''
                    }})).filter(x => x.text);
                }}""", sel)

                if items:
                    print(f"\nUsing selector '{sel}': {len(items)} items")
                    for item in items[:10]:
                        print(f"  [{item['text']}] -> {item['href'][:40]}")
                    break

        await asyncio.sleep(30)
        print("Closing...")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
