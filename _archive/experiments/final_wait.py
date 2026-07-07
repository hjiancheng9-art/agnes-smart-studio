import asyncio
import json
import time

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = None
        for pg in browser.contexts[0].pages:
            if "chatgpt.com" in pg.url:
                page = pg
                break
        if not page:
            print("no page")
            return

        print("waiting for response...", flush=True)
        start = time.time()
        while time.time()-start < 240:
            await asyncio.sleep(5)
            d = json.loads(await page.evaluate("() => JSON.stringify({s:!!document.querySelector('[data-testid=stop-button]')})"))
            l = await page.evaluate("() => {const m=document.querySelectorAll('[data-message-author-role=assistant]');return m.length>0?m[m.length-1].textContent.length:0;}")
            if not d["s"] and l > 500:
                text = await page.evaluate("() => {const m=document.querySelectorAll('[data-message-author-role=assistant]');return m.length>0?m[m.length-1].textContent:''}")
                path = r"C:\Users\huangjiancheng\agnes-smart-studio\wf_generator_result.txt"
                with open(path,"w",encoding="utf-8") as f:
                    f.write(text)
                print(f"SAVED {len(text)} chars to wf_generator_result.txt")
                print(text[:600])
                return
            elapsed = time.time()-start
            if int(elapsed)%20==0:
                print(f"  {elapsed:.0f}s l={l}", flush=True)
        print("timeout")

asyncio.run(main())
