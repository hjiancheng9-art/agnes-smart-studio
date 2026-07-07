"""Use Playwright to send msg to ChatGPT."""
import asyncio

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='msedge', headless=False)
        page = await browser.new_page()
        await page.goto('https://chatgpt.com', wait_until='domcontentloaded', timeout=30000)
        print('READY: title=' + await page.title())

        msg = '之前聊的"七兽一体 vs 过度设计"思辨，我做了实际代码审计。\n\n实测结果颠覆了我的假设。\n\n实际 Hot Path 系统提示词很瘦：\n- CHAT 模式: 1,474 tokens\n- CODE 模式: 2,449 tokens\n\n我原本以为 lore 文件夹（19个文件、114K 叙事层）被无差别注入系统提示词。实测发现——这19个文件从未被任何代码引用，纯死代码。\n\n我干的事：删了 16 个纯死代码 lore 文件（99,655 chars），留下2个有真实工具函数文件的。\n\n真正的 Hot Path 问题不在 Python 代码，在 AGENTS.md（15K chars, ~3,700 tokens）——框架把它当系统提示词加载，混合了运行时指令 + 架构文档 + 七兽世界观。但这是 IDE 框架层的事，我动不了。\n\n两个问题问你：\n1. 我删这 16 个 lore 文件对不对？有没有可能它们是将来要用的设计文档？\n2. AGENTS.md 的分层建议——拆成 SYSTEM.md（热路径：纯指令）和 AGENTS_REF.md（冷路径：参考文档）——靠谱吗？'

        # Clear input and type
        await page.keyboard.press('Control+a')
        await asyncio.sleep(0.2)
        await page.keyboard.press('Delete')
        await asyncio.sleep(0.2)
        await page.keyboard.type(msg, delay=1)
        await asyncio.sleep(0.5)

        await page.screenshot(path=r'C:\Users\huangjiancheng\agnes-smart-studio\output\before_send.png')

        # Send
        await page.keyboard.press('Enter')
        print('Sent! Waiting 45s...')

        await asyncio.sleep(45)

        text = await page.evaluate('() => document.body.innerText')
        with open(r'C:\Users\huangjiancheng\agnes-smart-studio\output\gpt_final_response.txt', 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'Response: {len(text)} chars')

        await browser.close()

asyncio.run(main())
