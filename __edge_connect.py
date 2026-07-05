import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # Connect to existing Edge via CDP
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        
        # List all contexts and pages
        contexts = browser.contexts
        print(f"Browser contexts: {len(contexts)}")
        
        all_pages = []
        for ctx in contexts:
            pages = ctx.pages
            all_pages.extend(pages)
            for pg in pages:
                print(f"\n📄 {pg.url[:80]}")
                print(f"   Title: {await pg.title() or '(no title)'}")
        
        print(f"\nTotal pages: {len(all_pages)}")
        
        # Take screenshot of the first page
        if all_pages:
            first = all_pages[0]
            await first.screenshot(path="output/edge_screenshot.png", full_page=False)
            print(f"\n✅ Screenshot saved to output/edge_screenshot.png")
        
        await browser.close()

asyncio.run(main())
