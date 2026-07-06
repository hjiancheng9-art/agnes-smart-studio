import asyncio
from playwright.async_api import async_playwright

# 重新设计的图像生成提示词 — 走 V2 的 prompt 管道思路
# 锚定具体风格关键词 + 负面约束 + 技术参数

PROMPT = """你现在是 V2 Keyframe Prompt Engineer。你的任务是为动画短片《翠翎风心》生成高质量 AI 图像提示词。

## 质量锚定 (必须包含)
风格: cinematic keyframe concept art, 3D anime style, Mikko Lagerstedt lighting, Ghost of Tsushima color grading, intricate details, volumetric lighting, depth of field, 8k resolution, dramatic atmosphere, professional concept art, pixar style render, smooth surface detail

## 负面约束 (必须避免)
ugly, deformed, blurry, low quality, distorted, bad anatomy, extra limbs, watermark, text, signature, oversaturated, flat lighting, poorly drawn

## 工作流
1. 用英文描述画面主体、构图、灯光、色调
2. 在描述末尾附加质量锚定关键词
3. 格式: [画面描述], [质量锚定], [负面约束]

## 输入分镜
场景1: 风停之晨
- Shot 1: 翠翎全景 — 浮空岛屿悬浮云海，青色羽叶树、空中瀑布、漂浮石阶、能量核心远景。超广角俯拍，缓慢推进。6秒。
- Shot 2: 风心黯淡 — 青金色能量核心悬浮空中，光芒明灭不定，表面裂纹。环绕中景。5秒。
- Shot 3: 翎召唤晨风失败 — 少女站在观风台，左眼风纹发光，伸手召唤晨风，掌心只有静止空气。中景推近特写。5秒。
- Shot 4: 岛屿下沉 — 浮空石阶倾斜，翼鹿惊飞，碎石坠落云海。快速横移。4秒。
- Shot 5: 苍梧显形 — 古树化身从阴影显现，树干身躯、枝叶长袍、淡金年轮眼睛。低角度仰拍。5秒。
- Shot 6: 使命揭示 — 苍梧告诉翎她是最后风语者，翎捂眼，风心低鸣天空渐暗。双人中景。8秒。

对以上6个镜头逐一生成提示词，中英双语：

短中文名: [名称]
EN: [英文提示词，含画面描述+质量锚定+负面约束]
"""

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = None
        for pg in browser.contexts[0].pages:
            if "gemini" in pg.url.lower():
                page = pg
                break
        if not page:
            print("no gemini page")
            return
        
        await page.bring_to_front()
        input_box = page.locator('[contenteditable="true"], textarea').first
        await input_box.click()
        await input_box.fill("")
        await asyncio.sleep(0.3)
        await input_box.fill(PROMPT)
        await asyncio.sleep(0.3)
        send_btn = page.locator('[aria-label*="Send"], button:has(svg)').first
        if await send_btn.is_visible():
            await send_btn.click()
        else:
            await page.keyboard.press("Enter")
        print("✉️ 高质量提示词请求已发送到 Gemini!")

asyncio.run(run())
