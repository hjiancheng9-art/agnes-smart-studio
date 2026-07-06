import asyncio
from playwright.async_api import async_playwright

PROMPT = """# 向世界知识库索取全部资料

我现在在开发一个 ComfyUI 智能体。请你作为世界知识库，给我下面所有这些领域的详细资料。要具体、可执行、有参数值、有公式。

## 1. LoRA 训练完整资料
- Kohya_ss 训练脚本的完整参数表(rank/alpha/lr/epochs/optimizer/resolution 各场景最佳值)
- SD1.5 / SDXL / FLUX 三种模型的推荐配置(都列出来)
- 不同图片数量(5张 vs 20张 vs 50张+)的训练策略(LR/epochs/repeat)
- 常见训练失败原因和修复方法(过拟合/欠拟合/画崩了)
- 标签格式规范(WD14 tagger / 自然语言 / 空标签)和各种场景适用
- LoRA 权重合并/层分析/剪枝

## 2. ComfyUI 工作流设计资料
- 标准文生图链路的每个节点的输入输出schema
- 图生图/Inpaint/ControlNet/IP-Adapter/LoRA/Upscale 的标准连接方式
- ComfyUI API 的 queue/history/upload 端点完整文档
- 常见报错和修复: "invalid prompt" / "noise mismatch" / "latent size mismatch"

## 3. 图像处理资料
- 训练图片预处理: 裁剪/去重/格式转换/质量检测
- 图片相似度计算方法(phash/SSIM/CLIP similarity)及阈值
- 图片标注最佳实践: 分辨率和质量的关系

## 4. 参数调优知识库
- KSampler 全部参数(seed/steps/cfg/sampler_name/scheduler/denoise)的含义和推荐范围
- 不同模型的推荐采样器和调度器
- 常见画质问题和对应参数调整方案(太模糊/太暗/变形/颜色不对/过多噪点)
- 视频生成(LTXV)的专属参数调优

## 5. 训练环境部署
- Kohya_ss GUI vs CLI 的完整安装步骤(Windows)
- OneTrainer 的完整安装和配置
- ComfyUI 内置 LoRA 训练节点的使用方法
- 常用模型下载地址(SD1.5/SDXL/FLUX/VAE/ControlNet)

## 6. 测试验证资料
- LoRA 效果评估标准(权重对比/提示词一致性/风格迁移度)
- X/Y/Z plot 对比分析方法
- 常见的测试工作流模板

请直接给出具体参数值和命令，不要只给原则。越详细越好。
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
