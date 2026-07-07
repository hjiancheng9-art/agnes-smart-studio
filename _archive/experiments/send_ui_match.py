import asyncio
from playwright.async_api import async_playwright

PROMPT = """# V2驾驶舱 vs 后端API匹配

V2有75个CRUX API路由, 驾驶舱只调用了9个, 覆盖率17%。
后端功能远强于界面。

请评估:
1. 驾驶舱应该对接哪些关键API才能"够用"?
2. 75个路由中有哪些是"管理类"(不需要界面)? 哪些是"用户类"(必须接入)?
3. 建议的优先级排序?
4. 你觉得驾驶舱最应该展示什么?
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = None
        for pg in browser.contexts[0].pages:
            if "chatgpt.com" in pg.url and "/c/" in pg.url:
                page = pg
                break
        if not page: return
        await page.bring_to_front()
        await asyncio.sleep(1)
        ta = page.locator("#prompt-textarea")
        await ta.wait_for(state="visible", timeout=10000)
        await ta.click()
        await ta.fill(PROMPT)
        await asyncio.sleep(0.3)
        await page.keyboard.press("Enter")
        print("SENT")

asyncio.run(main())
