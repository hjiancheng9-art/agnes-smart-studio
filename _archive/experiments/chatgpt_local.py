"""
ChatGPT 浏览器自动化 — 本地 Windows 运行
========================================
用法: python chatgpt_local.py

你的本地电脑有真实浏览器 + 真实 IP，Cloudflare 不会拦。
窗口保持打开，你可以看着它操作。
按 Ctrl+C 关闭。
"""

import asyncio

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=False,          # 显示窗口
            args=["--start-maximized"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print("🚀 正在打开 ChatGPT...")
        await page.goto("https://chatgpt.com")
        print(f"✅ 已打开: {await page.title()}")

        # 保持运行
        await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 已关闭")
