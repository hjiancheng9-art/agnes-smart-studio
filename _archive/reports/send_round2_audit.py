import asyncio

from playwright.async_api import async_playwright

PROMPT = """# ComfyUI 智能体 第二轮审计

第一轮已改造:
1. server.py 9476→1586行 + handlers/ 5模块 ✅
2. main.py 统一入口 ✅
3. config.py 环境变量覆盖 ✅
4. executor.py @_retry 重试 ✅
5. 20项测试通过 ✅
6. V2桥接对接 ✅

## 剩余问题

### 1. agent.py (2255行)
ComfyUIAgent 上帝对象, 77个方法
尝试拆分时遇到循环导入问题(agent.py 导入 agent_ops, agent_ops 引用 agent.py 的类型)

### 2. agent_flow.py (1899行)
NL工作流编排, 函数与brain.py的LLM逻辑重复

### 3. brain.py (376行)
OpenAI兼容大脑连接器, 和agent_flow.py都有LLM调用

### 4. 其他
- dataclass类型混在agent.py里
- 无真实HTTP集成测试(只测试了import)
- 异常处理方式不统一

## 输出要求
1. 当前健康评分
2. P0/P1/P2排序
3. agent.py拆分具体方案(如何避免循环导入)
4. brain + agent_flow LLM去重方案"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = None
        for pg in context.pages:
            if "chatgpt.com" in pg.url and "/c/" in pg.url:
                page = pg
                break
        if not page:
            for pg in context.pages:
                if "chatgpt.com" in pg.url:
                    page = pg
                    break
        if not page:
            page = await context.new_page()
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
