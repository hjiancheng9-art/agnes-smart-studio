import asyncio
import json
import time

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

        print("waiting...", flush=True)
        start = time.time()
        while time.time() - start < 300:
            await asyncio.sleep(5)
            d = json.loads(await page.evaluate("() => JSON.stringify({s:!!document.querySelector('[data-testid=stop-button]')})"))
            if not d["s"]:
                text = await page.evaluate("() => {const m=document.querySelectorAll('[data-message-author-role=assistant]');return m.length>0?m[m.length-1].textContent:''}")
                with open("chatgpt_multimodal.txt","w",encoding="utf-8") as f:
                    f.write(text)
                print(f"SAVED {len(text)} chars", flush=True)
                return
            elapsed = time.time()-start
            if int(elapsed) % 20 == 0:
                print(f"  waiting {elapsed:.0f}s", flush=True)
        print("timeout", flush=True)

asyncio.run(main())
