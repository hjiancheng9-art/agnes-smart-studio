import asyncio
from playwright.async_api import async_playwright

PROMPT = """# 为新烬龙V2创建专属方法论体系

V2 是一个 24 阶段视频创作管线(script→storyboard→keyframes→...→delivery), 有 CRUX 总控调度。

需要你给 V2 创作 5 套可执行的方法论, 不是通用知识, 而是 CRUX 总控能直接用的:

## 1. 管线运行方法论
- CRUX 如何调度 24 阶段(并行/串行/卡住怎么办)
- 阶段间数据传递(script→storyboard 传什么)
- 失败恢复策略(重试/跳过/降级)
- 24 阶段执行时间参考

## 2. 导演决策方法论
- 何时做决策、做什么决策
- 创作方向冲突仲裁(CRUX vs creative-bible vs 用户)
- 风格一致性维护

## 3. 质量门方法论
- 什么情况阻断/警告/放行
- 每阶段验收标准(具体检查项)
- 修复流程

## 4. 多平台执行方法论
- 什么阶段用 ChatGPT/Gemini/ComfyUI
- 平台切换策略
- 结果格式统一

## 5. 提示词工程方法论(V2版)
- 剧本创作提示词模板(CRUX→ChatGPT)
- 分镜/关键帧提示词模板(CRUX→Gemini/ComfyUI)
- 每阶段提示词质量检查清单

直接给可用模板和参数, 不要只给原则。"""

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
