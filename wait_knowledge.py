import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = None
        for pg in context.pages:
            if "chatgpt" in pg.url:
                page = pg
                break
        if not page:
            return
        
        print("waiting...")
        for i in range(60):
            await asyncio.sleep(5)
            result = await page.evaluate('() => JSON.stringify({done:!document.querySelector("[data-testid=stop-button]"),len:(document.querySelectorAll("[data-message-author-role=assistant]").length>0?document.querySelectorAll("[data-message-author-role=assistant]")[document.querySelectorAll("[data-message-author-role=assistant]").length-1].textContent.length:0)})')
            resp = json.loads(result)
            if resp["done"] and resp["len"] > 1000:
                break
            print(f"  {resp['len']} chars")
        
        text = await page.evaluate("() => {const m=document.querySelectorAll('[data-message-author-role=assistant]');return m.length>0?m[m.length-1].textContent:''}")
        with open("chatgpt_knowledge.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\nsaved {len(text)} chars")

asyncio.run(main())
