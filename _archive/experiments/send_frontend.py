import asyncio
from playwright.async_api import async_playwright

PROMPT = """# ComfyUI 智能体: 前端严重落后后端

## 现状
- 后端: 22模块, 82+健康分, 4轮迭代
- 前端: 6806行单块 SPA (vanilla JS, 无框架)
- 后端17个新API前端完全没用上

## 缺失的能力
1. 工作流模板浏览/搜索/推荐 — 1351个模板前端看不到
2. 参数引导 — prompt/seed/steps/cfg 等推荐值前端没展示
3. LoRA炼制UI — 数据集管理/训练配置/进度追踪全无
4. SSE进度推送 — 执行过程看不到
5. 人性化错误 — 错误还是抛json/traceback
6. 恢复系统 — 重试/诊断按钮

## 而前端现状
- 6806行单文件, 无框架, 无模块化
- 40个旧API调用, 大部分是/brain/ /agent-flow/ /auto-fix/ 等旧路由
- server.py里已经找不到这些旧路由了

## 请分析
1. 前端和后端的差距到底多大?
2. 建议: 重新写前端还是增量修改?
3. 如果重构: 用什么方案(新SPA/分模块/C同CRUX共用前端)?
4. V2已经有HUD驾驶舱界面, ComfyUI智能体应该有自己的前端还是复用V2的?
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = None
        for pg in browser.contexts[0].pages:
            if "chatgpt.com" in pg.url and "/c/" in pg.url:
                page = pg
                break
        if not page:
            page = await browser.contexts[0].new_page()
            await page.goto("https://chatgpt.com/")
            await asyncio.sleep(5)
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
