#!/usr/bin/env python
"""Playwright: launch Chrome with Profile 4 user data, read ChatGPT conversation."""

import asyncio
import os

from playwright.async_api import async_playwright

USER_DATA = r"C:\Users\huangjiancheng\AppData\Local\Google\Chrome\User Data"

async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            USER_DATA,
            headless=False,
            channel="chrome",
            args=["--profile-directory=Profile 4", "--no-sandbox"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        title = await page.title()
        url = page.url
        print(f"Title: {title}")
        print(f"URL: {url}")

        screenshot_path = r"C:\Users\huangjiancheng\agnes-smart-studio\output\chatgpt_read.png"
        os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot: {screenshot_path}")

        # Get all text
        text = await page.evaluate("() => document.body.innerText")
        print(f"Page text length: {len(text)} chars")

        # Search for the conversation
        if "CRUX" in text or "架构诊断" in text:
            print(">>> FOUND conversation references <<<")
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if "CRUX" in line or "架构诊断" in line:
                    print(f"  L{i}: {line[:150]}")
        else:
            print("Conversation not found on page. Looking at links...")
            # Get all clickable conversation links
            links = await page.evaluate("""() => {
                const items = document.querySelectorAll('nav a, [data-testid="history-item"], ol li a, ul li a');
                return Array.from(items).slice(0, 30).map(a => ({
                    text: (a.innerText || a.textContent || '').trim().substring(0, 80),
                    href: a.getAttribute('href') || ''
                })).filter(x => x.text);
            }""")
            for i, link in enumerate(links):
                print(f"  {i+1}. [{link['text']}] -> {link['href'][:40]}")

        # Print first part of page text
        print("\n=== PAGE TEXT (first 3000) ===")
        print(text[:3000])

        await asyncio.sleep(10)
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
