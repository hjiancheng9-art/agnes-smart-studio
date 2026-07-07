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

        print("⏳ 等待分镜完成...", flush=True)
        start = time.time()
        while time.time() - start < 180:
            d = json.loads(await page.evaluate("() => JSON.stringify({s:!!document.querySelector('[data-testid=stop-button]')})"))
            if not d["s"]:
                text = await page.evaluate("() => {const m=document.querySelectorAll('[data-message-author-role=assistant]');return m.length>0?m[m.length-1].textContent:''}")
                if len(text) > 200:
                    with open("v2_storyboard_result.txt","w",encoding="utf-8") as f:
                        f.write(text)
                    print(f"✅ {len(text)} chars", flush=True)
                    print(text[:400], flush=True)
                    return
            await asyncio.sleep(5)
            elapsed = time.time()-start
            if int(elapsed) % 15 == 0:
                print(f"  等待 {elapsed:.0f}s", flush=True)
        print("timeout", flush=True)

asyncio.run(main())
