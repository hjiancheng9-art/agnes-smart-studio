import asyncio
from playwright.async_api import async_playwright

PROMPT = """# 新烬龙V2: 请求完整世界知识库

我是CRUX总控。新烬龙V2是一个24阶段多模态视频创作管线。现在需要你作为世界知识库，给我系统补全以下所有领域的详细资料。

## 1. 24阶段视频制作资料
对每个阶段，给出：
- 阶段的最佳实践（剧本/分镜/关键帧/视觉开发/角色设计/环境/道具/特效/动画/灯光/电影化/配音/音乐/音效/剪辑/调色/VFX/标题/字幕/打包/审阅/交付/归档/回顾）
- 每个阶段的常见错误和修复方法
- 每个阶段的质量检查清单（5-10项）
- 每个阶段需要的关键技能/工具

## 2. 提示词工程资料（分阶段）
- 剧本创作提示词模板（3幕/英雄之旅/非线形）
- 分镜提示词模板（镜头语言/构图/转场）
- 关键帧提示词模板（分层描述：主体/环境/灯光/色调/细节/渲染）
- 视觉开发提示词模板（风格锚定/参考图/色板）
- 角色设计提示词模板（外貌/服装/表情/pose）
- 电影化提示词模板（镜头运动/景深/灯光方案）
- 配音提示词模板（语气/节奏/情感）

## 3. 创作圣经(creative-bible)参考
- 世界观构建模板（时代/地点/物理规则/社会结构/魔法系统）
- 角色设定模板（外貌/性格/动机/关系网/成长弧）
- 视觉风格参考（宫崎骏/赛博朋克/暗黑奇幻/皮克斯/EVA/新海诚）
- 常见世界观设定示例（5个完整案例）

## 4. 质量管理资料
- 视频制作各阶段的质量CHECKLIST（10-15项/阶段）
- 常见质量问题和修复方案
- 电影/动画评审标准（叙事/视觉/音频/节奏/完整性）
- 客户反馈常见问题和应对策略

## 5. 项目管理/交付资料
- 视频制作项目的时间线模板（从接收到交付）
- 交付物清单（每个阶段产出什么）
- 版本管理策略
- 客户沟通模板

## 6. 多模态输入处理
- 参考视频/图片/音频的处理流程
- 风格提取方法（从参考图提取色板/构图/灯光）
- 多模态输入的标注规范

请给出具体参数值和模板，不要只给原则。越详细越好。
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
