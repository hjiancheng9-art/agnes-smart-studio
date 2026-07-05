import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel='msedge',
            headless=False,
            args=['--no-first-run']
        )
        page = await browser.new_page()
        await page.goto('https://chatgpt.com', wait_until='domcontentloaded')
        print('Title:', await page.title())
        await page.screenshot(path='output/chatgpt_pw_connected.png')
        print('Screenshot saved!')
        # Keep browser alive for tool access
        while True:
            await asyncio.sleep(60)

asyncio.run(main())
