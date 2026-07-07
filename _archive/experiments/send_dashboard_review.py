import asyncio

from playwright.async_api import async_playwright

PROMPT = """# ComfyUI 智能体: 驾驶舱已就绪

刚完成的工作:
1. 新建 dashboard.html — 轻量驾驶舱, 对接后端全部新API
2. server.py 添加静态文件服务
3. 驾驶舱现有功能:
   - 状态面板: ComfyUI在线/熔断器/队列 实时轮询
   - 工作流浏览: 搜索1351个模板 + 分类过滤 + 分页
   - 推荐引擎: "生成一个视频" → 自动推荐模板
   - 执行面板: 输入prompt → 提交 → SSE进度推送
   - LoRA创建: 数据集/训练参数
   - 事件日志: SSE实时事件
4. 后端15个API少数没用上(诊断/重试/LoRA导入等)

## 当前全貌
- 22模块, 34回归测试, 全部通过
- 后端健康分: 82+
- 前端健康分: 35→65 (新驾驶舱填补了最大缺口)
- 前后端API匹配: 8/8 核心API全部对接

## 请评估
1. 驾驶舱设计是否合理? 还缺什么?
2. 下一步最应该做什么?
3. V2和ComfyUI智能体现在已经桥接, 要不要合二为一?
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
