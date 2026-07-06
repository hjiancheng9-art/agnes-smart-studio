import asyncio
from playwright.async_api import async_playwright

PROMPT = """# 新烬龙V2: 还需要几轮迭代？

## 当前状态

### 已建设
- 20 轮 ChatGPT 审计 + 改造 (架构→模块→源码→知识→规则→业务→QA→导演→Prompt→核心→多模态输入→管线→安全→数据模型→部署→日志→API设计)
- 36 新增文件, 16 修改文件, 4 测试文件
- 95+ API 端点
- CRUX 总控调度 (我)
- creative-bible / rule-engine / quality-gate / stage-contract / core-switchboard
- 20+ 方法论体系 (生图生视频方法论 16 套)
- world_knowledge v1 (21,799 字, 6 领域)
- V2 ↔ ComfyUI 智能体桥接通 (POST /api/crux/comfyui/run-stage)
- 健康分: 58 → 76

### 已知未完成
1. autoflow 24 阶段 → CRUX 推荐 ComfyUI 模板的链路还未真正跑通(只定义了接口)
2. ComfyUI 智能体前端(驾驶舱)已对接23/23 API但 V2 自身没有现代化前端(HUD是旧式)
3. 测试覆盖率还是偏低(只有 4 个测试文件)
4. 没有真正的 E2E 测试(启动 V2→CRUX→ComfyUI 智能体→出图全链路)
5. 有了 world_knowledge 但还没有真正被 autoflow 的 24 阶段引用(只在 registry 里)

## 请评估

1. V2 当前的产品成熟度阶段?
2. 到"真正可交付"还需要几轮迭代? 每轮做什么?
3. 如果只做 3 件事让健康分到 85, 是哪三件?
4. V2 + ComfyUI 智能体的完整度是多少?
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
