import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://127.0.0.1:9222')
        page = browser.contexts[0].pages[0]
        
        data = await page.evaluate("""
            () => {
                const msgs = document.querySelectorAll('[data-message-author-role]');
                const result = [];
                msgs.forEach((m, i) => {
                    const role = m.getAttribute('data-message-author-role');
                    const txt = m.innerText.trim();
                    result.push(`[MSG ${i}] role=${role} (${txt.length} chars)`);
                    result.push(txt.slice(0, 200));
                });
                return result.join('\n---\n');
            }
        """)
        
        print(data[:3000])
        await browser.close()

asyncio.run(main())
