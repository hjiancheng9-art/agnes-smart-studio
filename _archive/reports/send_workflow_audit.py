import asyncio

from playwright.async_api import async_playwright

PROMPT = """# ComfyUI 智能体: 真的能做工作流吗？

架构已经改造完了, 现在问一个更本质的问题: 这个智能体到底能不能真正创建、编辑、执行 ComfyUI 工作流?

## 当前工作流能力清单

### 1. ROUTES 中 256 条 API 端点
其中工作流相关约 50 条:
- POST /api/queue — 提交工作流
- GET /api/status — 查询状态
- GET /api/comfyui/status — ComfyUI 连接状态
- POST /api/agent-bridge-workflow — 桥接工作流
- POST /api/advanced-storyboard-workflow — 高级分镜工作流
- POST /api/lora-analyze-workflow — Lora 分析
- POST /api/lora-plan — Lora 规划
- GET /api/workflows/ — 列出工作流
- POST /api/workflows/ — 保存工作流
- GET /api/skills/ — 技能列表

### 2. 工作流生成能力
agent_flow.py (40 函数) 包含:
- _try_brain_design_route — LLM 设计工作流
- plan_advanced_workflow — 规划高级工作流
- invent_advanced_workflow — 发明新工作流
- adapt_advanced_storyboard_workflow — 适配分镜工作流
- validate_workflow — 验证工作流

### 3. 工作流模板
- advanced_workflow_blueprints.py (366行) — 蓝图定义
- advanced_storyboard_workflow.py (388行) — 分镜工作流
- advanced_workflow_research.py (303行) — 工作流研究

### 4. 执行能力
- executor.py — 提交 + 轮询 + 结果下载
- @_retry 重试

### 5. 工作流编辑器
- 前端有 43 JS + 12 HTML (Web 编辑器)
- agent.py 中有 editor 属性

## 请评估

### 正方: 能力完整
- 有设计(LLM) → 创建(blueprint) → 验证(validate) → 提交(queue) → 跟踪(status) → 结果(fetch) 全链路
- 前端有可视化编辑器
- 256 API 端点的覆盖面

### 反方: 真能用吗?
1. LLM 设计工作流 — 真的能生成可执行的 ComfyUI JSON 吗? 还是只生成"描述"?
2. 蓝图系统 — 有多少个预置模板? 覆盖多少种场景(文生图/图生图/视频/放大)?
3. 编辑器 — 是"能编辑 JSON"还是"能拖拽节点"?  
4. 错误修复 — agent_flow 的修复功能: 能自动安装缺失节点吗? 能修复连接错误吗?
5. 批量能力 — 支持批量/队列/种子变化吗?
6. 前端体验 — 用户从打开页面到跑出第一张图需要几步?
7. 和 ComfyUI 原版 UI 比 — 为什么用户要用这个而不是直接开 ComfyUI?

## 最终输出
1. 工作流能力评分 (0-100, 维度: 设计/创建/执行/修复/前端)
2. 现有能力的真正短板
3. 如果要"真的能用", 最需要补什么
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
