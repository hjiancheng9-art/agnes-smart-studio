#!/usr/bin/env python
"""Use Playwright with stealth to read ChatGPT conversation."""

import asyncio, os, sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # Use Playwright's own Chromium with stealth
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        
        page = await context.new_page()
        
        # Apply stealth
        try:
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            """)
        except:
            pass
        
        await page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        title = await page.title()
        url = page.url
        print(f"Title: {title}")
        print(f"URL: {url}")
        
        # Try waiting for Cloudflare to pass
        await asyncio.sleep(5)
        
        # Take screenshot
        screenshot_path = r"C:\Users\huangjiancheng\agnes-smart-studio\output\chatgpt3.png"
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        await page.screenshot(path=screenshot_path)
        print(f"Screenshot: {screenshot_path}")
        
        # Get text
        text = await page.evaluate("() => document.body.innerText")
        print(f"\nPage text ({len(text)} chars):")
        print(text[:2000])
        
        await asyncio.sleep(5)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
