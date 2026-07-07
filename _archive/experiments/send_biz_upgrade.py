import asyncio
import os

from playwright.async_api import async_playwright

d = r"C:\Users\huangjiancheng\CodeBuddy\comfyui智能体"
gw = os.path.join(d, "generated_workflows")

real_files = [f for f in os.listdir(gw) if f.endswith('.json') and 'canvas' not in f.lower() and 'runtime-acceptance' not in f.lower()]
vcount = sum(1 for f in real_files if any(k in f.lower() for k in ['ltx','video','animate','六宫格','动作迁移','导演台','berni']))
icount = len(real_files) - vcount

PROMPT = f"""# ComfyUI 智能体: 业务能力升级规划

## 当前能力

### 工作流资产: {len(real_files)} 个
- video: {vcount}+ 个 (LTXV/AnimateDiff/六宫格导演台/动作迁移/ICLORA)
- image: {icount}+ 个 (文生图/图生图/FLUX/ControlNet)

### 已搭建的能力
1. Registry 动态加载 — generated_workflows/ 自动索引
2. workflow_runner — 模板→参数填充→提交 ComfyUI
3. V2 24阶段映射 — 8个阶段对应模板
4. CRUX API: POST /api/crux/comfyui/run-stage
5. WorkflowValidator — JSON 校验

### 关键缺口
1. 工作流都是文件, 没有参数模板(不知道哪些字段要用户填)
2. 没有"推荐工作流"逻辑 — 用户说"做视频"不知道该用哪个
3. executor.submit() 只定义了接口, 没真正连 ComfyUI
4. 没有结果管理(出图后怎么回传)
5. 没有参数配置UI/自然语言引导

## 请分析
1. 当前业务能力成熟度评分
2. 最急需做的 3 件事 + 具体方案
3. 如果先做"参数模板", 技术方案是什么
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
