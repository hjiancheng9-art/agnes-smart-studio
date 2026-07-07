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
            print("no page")
            return
        
        print("waiting for business layer analysis...", flush=True)
        for i in range(90):
            await asyncio.sleep(4)
            r = await page.evaluate("() => JSON.stringify({s:!!document.querySelector('[data-testid=stop-button]'),l:(document.querySelectorAll('[data-message-author-role=assistant]').length>0?document.querySelectorAll('[data-message-author-role=assistant]')[document.querySelectorAll('[data-message-author-role=assistant]').length-1].textContent.length:0)})")
            d = json.loads(r)
            if not d["s"] and d["l"] > 2000:
                break
            if i % 10 == 0:
                print(f"  {d['l']} chars, streaming={d['s']}", flush=True)
        
        text = await page.evaluate("() => {const m=document.querySelectorAll('[data-message-author-role=assistant]');return m.length>0?m[m.length-1].textContent:''}")
        with open("chatgpt_business.txt","w",encoding="utf-8") as f:
            f.write(text)
        print(f"saved {len(text)} chars", flush=True)

asyncio.run(main())
