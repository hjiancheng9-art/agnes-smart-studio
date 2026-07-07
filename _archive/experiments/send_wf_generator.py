import asyncio

from playwright.async_api import async_playwright

PROMPT = """# ComfyUI 智能体: 如何成为真正的工作流生成器

现在的 ComfyUI 智能体能"推荐"和"套模板"，但本质上是模板匹配。它不能：

1. 根据需求从头生成新工作流
2. 理解当前工作流的问题并自动修复
3. 调参数——不知道哪些参数能调、怎么调
4. 组合多个工作流（比如先放大再视频化）

你给我的 1351 个工作流是很好的基础数据，但它们应该是"学习材料"而非"数据库"。

## 我想让它变成

一个能从工作流数据中学习 ComfyUI 节点组合规律、能根据用户需求合成新工作流、能理解参数语义并自动调优的智能体。

## 请分析

1. 当前能力差距（模板匹配 vs 智能合成）
2. 需要什么新能力模块（工作流表示学习/参数语义理解/组合生成/自动调优）
3. 技术路线图：先做什么后做什么
4. 如果 LLM 已经能理解 ComfyUI JSON 结构，怎么用 LLM 做工作流生成
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = None
        for pg in browser.contexts[0].pages:
            if "chatgpt.com" in pg.url:
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
