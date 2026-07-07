import asyncio

from playwright.async_api import async_playwright

PROMPT = """# V2 驾驶舱迭代评估

## 当前状态
驾驶舱经过多轮迭代, 现状:
- P0(9项): 全部完成 ✅
- P1(9项): 全部完成 ✅  
- P2(8项): 全部完成 ✅
- 后端对接率: 90% (68/75)
- JS语法通过, E2E测试通过
- 功能: 状态面板/工作流搜索/执行+SSE/24阶段管线/LoRA/创作圣经/导演决策/知识搜索/API注册表/Prompt日志/安全检测/规则审计/QA事件/高级诊断/Mock测试/知识重载/Schema/日志

## 但"做完"和"好用"是两回事
驾驶舱现在功能够全但:
1. 纯黑底白字, 没有品牌感
2. 移动端没有适配
3. 没有引导(用户进来不知道先点哪)
4. 实时性: 8秒轮询而不是WebSocket
5. 错误提示还是JSON格式
6. 没有搜索历史/收藏/常用工作流
7. 没有用户系统

## 请评估
1. 当前驾驶舱的产品成熟度评分
2. 到"可交付用户"还需要几轮迭代?
3. 如果只做3个体验改进, 是哪3个?
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
