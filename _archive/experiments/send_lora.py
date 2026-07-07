import asyncio

from playwright.async_api import async_playwright

PROMPT = """# ComfyUI 智能体: LoRA 炼制能力

我有很多 LoRA 相关的 ComfyUI 工作流，智能体现在也能学习节点规律和合成工作流了。但 LoRA 炼制（训练）是一个完全不同的能力维度——不只是在工作流里"加载"LoRA，而是要能够帮用户"炼制"新的 LoRA。

## LoRA 炼制的完整链路

### 1. 数据准备阶段
- 帮助用户整理训练图片（裁剪/去重/标注）
- 自动生成标签（用 LLM 描述图片内容）
- 创建正确的目录结构

### 2. 训练配置阶段
- 基础模型选择（SD1.5 / SDXL / FLUX）
- 训练参数配置（rank/alpha/lr/epochs/batch）
- 训练脚本生成

### 3. 训练执行阶段
- 调用 Kohya_ss / OneTrainer / ComfyUI LoRA 训练节点
- 进度监控
- 中间 checkpoint 保存

### 4. 测试验证阶段
- 用训练好的 LoRA 跑测试工作流
- 对比原模型效果
- 调整参数重新训练

### 5. 工作流集成
- 自动生成 LoraLoader 节点
- 调整权重参数

## 当前智能体的相关能力
- 1351 个工作流中已有 LoRA 相关: LoRA Loader / IC-LoRA / LoRA 分析 / LoRA 规划
- 参数引擎能理解 KSampler/LoraLoader 的参数
- 工作流合成器能生成含 LoRA 节点的链路

## 请分析
1. LoRA 炼制链条在当前智能体中还缺什么
2. 哪些环节可以自动化, 哪些必须人工介入
3. 技术方案: 智能体应该如何管理"训练数据→训练配置→训练执行→测试→集成"这个完整流程
4. 和 ComfyUI 的 LoRA 训练节点的集成方式
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
