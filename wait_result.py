import asyncio, json, time, sys
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
        
        # Wait for ChatGPT to finish generating
        print("⏳ 等待 ChatGPT 完成回复...", flush=True)
        start = time.time()
        while time.time() - start < 180:
            d = json.loads(await page.evaluate("() => JSON.stringify({s:!!document.querySelector('[data-testid=stop-button]')})"))
            if not d["s"]:
                break
            await asyncio.sleep(5)
            elapsed = time.time() - start
            if int(elapsed) % 15 == 0:
                print(f"  等待中... {elapsed:.0f}s", flush=True)
        
        text = await page.evaluate("""() => {
            const m = document.querySelectorAll('[data-message-author-role="assistant"]');
            return m.length > 0 ? m[m.length-1].textContent : '';
        }""")
        
        with open("v2_first_project_result.txt", "w", encoding="utf-8") as f:
            f.write(text)
        print(f"📝 已保存 {len(text)} chars", flush=True)
        print(text[:300], flush=True)

asyncio.run(main())
