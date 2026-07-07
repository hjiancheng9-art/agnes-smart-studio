import asyncio, json, time, sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = None
        for pg in browser.contexts[0].pages:
            if "gemini" in pg.url.lower():
                page = pg
                break
        if not page:
            print("no gemini page")
            return
        
        print("⏳ Gemini 生成中...", flush=True)
        start = time.time()
        prev = 0
        stable = 0
        
        while time.time() - start < 180:
            await asyncio.sleep(5)
            text = await page.evaluate("() => document.body.innerText")
            l = len(text)
            if l > 500 and l == prev:
                stable += 1
                if stable >= 4:
                    break
            else:
                stable = 0
            prev = l
            elapsed = time.time()-start
            if int(elapsed) % 15 == 0:
                print(f"  {elapsed:.0f}s - {l} chars", flush=True)
        
        text = await page.evaluate("() => document.body.innerText")
        with open("v2_keyframe_prompts.txt","w",encoding="utf-8") as f:
            f.write(text)
        print(f"✅ 已保存 {len(text)} chars", flush=True)

asyncio.run(main())
