#!/usr/bin/env python
"""Connect to Edge via CDP and read ChatGPT conversation."""

import asyncio, os, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # Connect to the running Edge with remote debugging
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        
        # Get all contexts and pages
        default_context = browser.contexts[0] if browser.contexts else None
        pages = browser.contexts[0].pages if browser.contexts else []
        
        if not pages:
            page = await browser.new_page()
        else:
            page = pages[0]
        
        # Wait for page to load
        await asyncio.sleep(3)
        
        url = page.url
        title = await page.title()
        print(f"URL: {url}")
        print(f"Title: {title}")
        
        # Take screenshot
        screenshot_path = os.path.join(os.getcwd(), "output", "chatgpt_page.png")
        os.makedirs(os.path.join(os.getcwd(), "output"), exist_ok=True)
        await page.screenshot(path=screenshot_path)
        print(f"Screenshot: {screenshot_path}")
        
        # Get page text content
        text = await page.evaluate("""() => {
            return document.body.innerText.substring(0, 10000);
        }""")
        
        print(f"\n=== Page Text (first 5000) ===")
        print(text[:5000])
        
        # Look for conversation titles / history
        conv_titles = await page.evaluate("""() => {
            // ChatGPT conversation history selectors
            const items = document.querySelectorAll('a[href*="/c/"], [data-testid="conversation-item"], li a, nav a');
            return Array.from(items).slice(0, 20).map(a => ({
                text: a.innerText?.trim() || a.textContent?.trim() || '',
                href: a.getAttribute('href') || ''
            })).filter(x => x.text);
        }""")
        
        if conv_titles:
            print(f"\n=== Conversation History ({len(conv_titles)} items) ===")
            for i, item in enumerate(conv_titles):
                print(f"  {i+1}. {item['text'][:50]} -> {item['href'][:30]}")
        
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
