import asyncio
from playwright.async_api import async_playwright

PROMPT = """# ComfyUI 智能体: 第二轮业务能力升级

## 当前状态
- 1351个工作流已加载 ✅
- 1336个含参数模板 ✅
- 推荐引擎按意图匹配 ✅
- V2 8个阶段映射 ✅
- 12/12模块通过 ✅

## 还剩的差距

### 1. V2 阶段映射是死的
现在 V2→ComfyUI 映射写死8条规则. 应该: 阶段 + prompt → 推荐引擎 → 自动选最合适的

### 2. workflow_runner 没真正连 ComfyUI
executor.submit() 是 Stub, 没有真正 HTTP 请求

### 3. 没有执行状态/结果管理
提交后不知道进度, 出图后不知道图存哪了

### 4. V2 adapter 没真正接上 CRUX
comfyui-workflow-adapter.js 定义了接口但 autoflow 没调用

## 要求
1. 当前业务成熟度评分
2. 最优先解决的 3 个问题 + 技术方案
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
