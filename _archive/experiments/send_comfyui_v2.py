import asyncio
import os

from playwright.async_api import async_playwright

d = r"C:\Users\huangjiancheng\CodeBuddy\comfyui智能体"
agent_py = open(os.path.join(d, "comfyui_agent", "agent.py"), encoding='utf-8').read()

funcs = []
for line in agent_py.split('\n'):
    s = line.strip()
    if s.startswith('def ') or s.startswith('async def ') or s.startswith('class '):
        funcs.append(s[:120])

PROMPT = f"""# ComfyUI 智能体 架构审计(新对话)

核心模块:
- agent.py (2256行, {len(funcs)}函数) — 主API
- executor.py (2099行) — ComfyUI执行器
- agent_flow.py (1899行) — NL流程编排
- brain.py (376行) — LLM大脑
- config.py (143行) — 配置
- launch.py (613行) — 启动器

关键函数:
{chr(10).join(funcs[:40])}

规模: 106个.py / 43 JS / 12 HTML / 9测试

请分析:
1. agent.py 2256行上帝对象？职责划分？
2. executor.py 2000+行错误处理/超时？
3. config.py 硬编码了哪些敏感信息？
4. brain.py (376行LLM) 和 agent.py 的关系？
5. launch.py 和 agent.py 启动入口混乱？
6. 9个测试覆盖106个文件？
7. 如何作为V2子执行器？
8. CRUX总控如何调用？

健康评分 + P0/P1/P2 + 改进建议"""

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
            await asyncio.sleep(4)

        await page.bring_to_front()
        await asyncio.sleep(1)

        # Check if it's a fresh page (no conversation) or has an old one
        url = page.url
        if "/c/" in url:
            # Already in a conversation - try new chat first
            try:
                new_btn = page.locator('a:has-text("新聊天"), button:has-text("新聊天")').first
                if await new_btn.is_visible(timeout=2000):
                    await new_btn.click()
                    await asyncio.sleep(2)
            except:
                pass

        await asyncio.sleep(1)

        ta = page.locator("#prompt-textarea")
        if await ta.is_visible(timeout=5000):
            await ta.click()
            await ta.fill(PROMPT)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")
            print("SENT", flush=True)
        else:
            print("NO_INPUT", flush=True)

asyncio.run(main())
