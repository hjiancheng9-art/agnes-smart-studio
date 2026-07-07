"""
Edge 本地控制台 — 你打开浏览器，我远程操控
============================================
用法:
  1. 在本地电脑安装: pip install playwright
  2. 运行: python edge_local.py
  3. 浏览器自动打开 ChatGPT
  4. 在终端输入我给你的命令

命令列表（终端直接输入）:
  goto <url>        — 导航到网页
  ss [文件名]        — 截图
  click <选择器>     — 点击元素
  fill <选择器> <文本> — 填写输入框
  press <按键>       — 按键 (Enter, Tab, Escape...)
  text [选择器]      — 获取文本 (默认body)
  links             — 获取所有链接
  js <代码>          — 执行 JavaScript
  url               — 显示当前地址
  help              — 显示帮助
  exit / quit       — 关闭
"""

import asyncio
import sys

from playwright.async_api import async_playwright


async def main():
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = "https://chatgpt.com"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="msedge",
            headless=False,
            args=["--start-maximized"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print(f"🌐 正在打开 {url} ...")
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        print(f"✅ 已打开 → {await page.title()}")
        print(f"📌 当前地址: {page.url}")
        print(f"\n{'='*50}")
        print("💡 在下方输入我给你的命令")
        print(f"{'='*50}\n")

        while True:
            try:
                cmd = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 关闭中...")
                break

            if not cmd:
                continue

            parts = cmd.split()
            action = parts[0].lower()
            args_list = parts[1:]

            if action in ("exit", "quit"):
                break

            elif action == "help":
                print("""可用命令:
  goto <url>        — 导航
  ss [文件名]        — 截图
  click <选择器>     — 点击
  fill <选择器> <文> — 填表
  press <按键>       — 按键
  text [选择器]      — 获取文本
  links             — 获取链接
  js <代码>          — 执行 JS
  url               — 当前地址
  reload            — 刷新页面
  back              — 后退
  help              — 帮助
  exit              — 退出""")

            elif action == "goto":
                u = args_list[0] if args_list else "https://www.baidu.com"
                try:
                    await page.goto(u, timeout=30000, wait_until="domcontentloaded")
                    print(f"🔗 {page.url}")
                    print(f"📄 {await page.title()}")
                except Exception as e:
                    print(f"❌ {e}")

            elif action in ("ss", "screenshot"):
                name = args_list[0] if args_list else f"ss_{int(asyncio.get_event_loop().time())}.png"
                await page.screenshot(path=name)
                print(f"📸 已保存: {name}")

            elif action == "click":
                sel = args_list[0] if args_list else "body"
                try:
                    await page.click(sel, timeout=5000)
                    await asyncio.sleep(0.5)
                    print(f"✅ 已点击: {sel}")
                except Exception as e:
                    print(f"❌ {e}")

            elif action == "fill":
                if len(args_list) < 2:
                    print("❌ 用法: fill <选择器> <文本>")
                else:
                    sel = args_list[0]
                    text = " ".join(args_list[1:])
                    await page.fill(sel, text)
                    print(f"✅ 已填入: {sel} ← {text[:50]}{'...' if len(text)>50 else ''}")

            elif action == "press":
                key = args_list[0] if args_list else "Enter"
                await page.keyboard.press(key)
                await asyncio.sleep(0.5)
                print(f"✅ 已按键: {key}")

            elif action == "text":
                sel = args_list[0] if args_list else "body"
                els = await page.query_selector_all(sel)
                if not els:
                    print("(无内容)")
                elif len(els) == 1:
                    t = await els[0].inner_text()
                    print(t[:1000] + ("..." if len(t) > 1000 else ""))
                else:
                    texts = [await el.inner_text() for el in els[:20]]
                    for i, t in enumerate(texts):
                        print(f"[{i}] {t[:100]}")
                    print(f"...共 {len(els)} 个元素")

            elif action == "links":
                links = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(el => ({text: el.innerText.trim(), href: el.href})).filter(x => x.text)"
                )
                for l in links[:30]:
                    print(f"  🔗 {l['text'][:50]} → {l['href'][:80]}")
                print(f"  ...共 {len(links)} 个链接")

            elif action == "js":
                code = " ".join(args_list)
                try:
                    result = await page.evaluate(code)
                    print(f"🖥️ {result}")
                except Exception as e:
                    print(f"❌ {e}")

            elif action == "url":
                print(f"🔗 {page.url}")
                print(f"📄 {await page.title()}")

            elif action == "reload":
                await page.reload()
                print("🔄 已刷新")

            elif action == "back":
                await page.go_back()
                print(f"🔙 {page.url}")

            else:
                print(f"❌ 未知命令: {action} (输入 help 查看帮助)")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
