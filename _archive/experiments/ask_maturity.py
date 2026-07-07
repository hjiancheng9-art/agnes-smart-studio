import asyncio

from playwright.async_api import async_playwright

PROMPT = """# ComfyUI 智能体: 还需要几轮迭代才能成熟？

## 当前状态 (健康分 78+)
17 个模块全部通过，已有能力:

### 核心能力
- server.py(路由层) + handlers/5模块(295函数)
- executor(真实HTTP连接ComfyUI)
- llm_client(统一LLM网关)
- workflow_analyzer(735节点类型/2151连接模式)
- workflow_generator(按需合成工作流)
- parameter_engine(参数语义理解+画质诊断)
- lora_manager(LoRA炼制全链路: 数据集→训练→测试)
- execution_manager(状态追踪+结果管理)
- 21,869字世界知识库已注入

### V2 桥接
- POST /api/crux/comfyui/run-stage → 动态推荐工作流 → 执行

## 请你评估

1. 按产品成熟度模型（从"能用"到"好用"到"可靠"），当前处于哪个阶段？
2. 到"真正能交给用户用"还需要几轮迭代？每轮做什么？
3. 每轮的预计健康分提升是多少？
4. 如果只做最关键的3件事让健康分到90，是哪三件？
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
