import asyncio

from playwright.async_api import async_playwright

PROMPT = """# ComfyUI 智能体 第三轮审计 — 终审

经过两轮改造后, 当前状态:
- server.py 9476→1586行 + handlers/5模块295函数 ✅
- types.py/constants.py/shared.py ✅
- llm_client.py 统一LLM网关 ✅
- main.py 统一入口 ✅
- 20+ 测试 ✅
- V2桥接 ✅

## 剩余结构问题

### 1. 52 个文件超过 300 行 (共 106 个 .py 文件)
一半以上的文件都是"大文件"。这不是一个健康的分布。
最突出的:
- executor.py (2120行, 48函数)
- agent_flow.py (1899行, 40函数)
- 52个文件>300行

### 2. agent_flow.py (1899行) 仍含 LLM 调用
已经有 llm_client.py 作为统一网关, 但 agent_flow.py 仍有 LLM 引用。
brain.py (376行) 存在但未被 agent_flow.py 使用。

### 3. agent.py (272行, 1函数)
ComfyUIAgent 类只剩 __init__ 和一些 @property, 但整个框架依然依赖它作为入口。
是否应该让它彻底退役?

### 4. 类型提示覆盖率未知
部分函数缺少返回类型注解。

### 5. Web 前端文件
43 JS + 12 HTML 混杂在后端项目中, 应该分离。

## 要求
1. 当前健康评分
2. P0/P1/P2 问题清单 (仅限仍然存在的问题)
3. 最优先的 3 件事
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = None
        for pg in browser.contexts[0].pages:
            if "chatgpt.com" in pg.url:
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
