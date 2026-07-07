"""
Edge 浏览器自动化控制
====================
用法:
  python edge_connect.py                    # 启动新 Edge 并打开百度
  python edge_connect.py --url <URL>        # 启动新 Edge 并打开指定网址
  python edge_connect.py --connect          # 连已有 Edge（需加 --remote-debugging-port=9222 启动）
  python edge_connect.py --script <file>    # 执行自定义脚本文件

已安装: Playwright 1.61.0 | Edge (Chromium)
"""

import sys, asyncio, os
from playwright.async_api import async_playwright

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


async def launch_new(url: str = "https://www.baidu.com"):
    """启动新的 Edge 浏览器"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=False,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = await context.new_page()
        await page.goto(url)
        print(f"✅ Edge 已启动 → {url}")
        print(f"   页面标题: {await page.title()}")
        # 保持窗口打开，等待用户操作
        while True:
            await asyncio.sleep(1)


async def connect_existing():
    """连接已有 Edge（需先以调试端口启动）"""
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        print(f"✅ 已连接到 Edge 实例")
        for i, ctx in enumerate(browser.contexts):
            for j, page in enumerate(ctx.pages):
                print(f"   [{i}.{j}] {page.url}")
        while True:
            await asyncio.sleep(1)


async def run_script(script_path: str):
    """执行自定义控制脚本"""
    with open(script_path, "r", encoding="utf-8") as f:
        code = f.read()
    exec(code)


async def demo_actions(page):
    """一些常用操作示例"""
    # 搜索
    await page.fill("input[name='wd']", "Playwright 教程")
    await page.press("input[name='wd']", "Enter")
    await page.wait_for_load_state()
    print(f"   搜索结果页: {await page.title()}")

    # 截屏
    await page.screenshot(path="screenshot.png")
    print("   截图已保存: screenshot.png")

    # 获取页面内容
    links = await page.eval_on_selector_all(
        "h3", "els => els.map(el => el.innerText)"
    )
    print(f"   搜索结果标题: {links[:5]}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        asyncio.run(launch_new())
    elif args[0] == "--connect":
        asyncio.run(connect_existing())
    elif args[0] == "--url" and len(args) > 1:
        asyncio.run(launch_new(args[1]))
    elif args[0] == "--script" and len(args) > 1:
        asyncio.run(run_script(args[1]))
    else:
        print(f"未知参数: {args}")
        print("用法见文件头部注释")
