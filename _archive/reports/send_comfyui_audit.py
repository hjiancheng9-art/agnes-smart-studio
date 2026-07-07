import asyncio
import os

from playwright.async_api import async_playwright

d = r"C:\Users\huangjiancheng\CodeBuddy\comfyui智能体"
agent_py = open(os.path.join(d, "comfyui_agent", "agent.py"), encoding='utf-8').read()

# Get function list from agent.py
funcs = []
for line in agent_py.split('\n'):
    s = line.strip()
    if s.startswith('def ') or s.startswith('async def ') or s.startswith('class '):
        funcs.append(s[:120])

PROMPT = f"""# ComfyUI 智能体 架构审计

这是一个 ComfyUI 工作流智能体系统。

## 核心模块

### agent.py (2256 lines) — 主接口
{chr(10).join(funcs[:30])}
...(共2256行, {len(funcs)}个函数/类)...

### executor.py (2099 lines) — 执行器 
- 提交工作流到 ComfyUI REST API
- 轮询进度、下载结果

### agent_flow.py (1899 lines) — NL工作流编排
- 自然语言驱动的工作流构建

### brain.py (376 lines) — LLM大脑
- OpenAI 兼容 API 连接器

### config.py (143 lines) — 路径/环境配置

### launch.py (613 lines) — 启动器(管理ComfyUI进程)

## 项目规模: 106 Python / 43 JS / 12 HTML / 9 test

## 请分析

1. agent.py 2256行 — 上帝对象还是合理聚合？
2. brain.py 376行 — LLM连接器，和 agent.py 关系是什么？
3. executor.py 2000+行 — ComfyUI API 通信，错误处理/超时/重试机制？
4. config.py 143行 — 硬编码了什么？安全性？
5. 启动入口混乱 — launch.py 管理 ComfyUI 进程，agent.py 启动 API，谁负责总启动？
6. 无测试覆盖核心流程 — 9个测试够吗？
7. 与 V2 集成 — V2 有 comfyuiPreflightBlockers 引用 ComfyUI，这个项目如何作为 V2 的子执行器？
8. CRUX 总控如何调用 — 我(CRUX)通过 API 还是 browser-control 调用它？

## 输出
- 健康评分
- P0/P1/P2 问题
- 改进建议"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]

        # Open new ChatGPT page
        page = await context.new_page()
        await page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
        await asyncio.sleep(4000)

        # Click new chat if needed
        try:
            new_btn = page.locator('a:has-text("新聊天"), a:has-text("New chat"), button:has-text("新聊天")').first
            if await new_btn.is_visible():
                await new_btn.click()
                await asyncio.sleep(2000)
        except:
            pass

        await page.wait_for_timeout(2000)

        input_box = page.locator("#prompt-textarea")
        await input_box.click()
        await input_box.fill(PROMPT)
        await page.wait_for_timeout(300)
        await page.keyboard.press("Enter")
        print("已发送!")

asyncio.run(main())
