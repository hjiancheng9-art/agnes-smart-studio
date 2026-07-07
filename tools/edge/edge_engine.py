"""
Edge Browser Headless 引擎 — 稳定、可复用
=========================================
所有操作都是"用完即走"模式，每次调用独立浏览器会话，彻底避免会话泄漏问题。
适合：导航、截图、填表、点击、提取数据。

使用方式:
  from edge_engine import EdgeEngine
  engine = EdgeEngine()
  await engine.goto("https://www.baidu.com")
  result = await engine.screenshot()
  text = await engine.get_text("h3")
  await engine.close()

单命令模式:
  python edge_engine.py goto https://www.baidu.com
  python edge_engine.py screenshot
  python edge_engine.py fill "input[name=wd]" "测试"
  python edge_engine.py click "#su"
  python edge_engine.py text "h3"
"""

import asyncio
import json
import os
import sys
import time

from playwright.async_api import TimeoutError as PwTimeout
from playwright.async_api import async_playwright


class EdgeEngine:
    """Edge Headless 浏览器引擎 — 每次调用独立会话"""

    def __init__(self, headless=True, timeout=30):
        self.headless = headless
        self.timeout = timeout
        self._pw = None
        self._browser = None
        self._page = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if self._browser and self._browser.is_connected():
            return
        self._pw = await async_playwright().__aenter__()
        self._browser = await self._pw.chromium.launch(
            channel="msedge",
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

    async def _ensure_page(self):
        """确保有一个可用页面"""
        await self._ensure_browser()
        if not self._page or self._page.is_closed():
            ctx = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            self._page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    async def goto(self, url: str, wait_until="domcontentloaded"):
        """导航到 URL"""
        await self._ensure_page()
        try:
            await self._page.goto(url, timeout=self.timeout * 1000, wait_until=wait_until)
            await asyncio.sleep(1)
            return {"url": self._page.url, "title": await self._page.title(), "status": "ok"}
        except PwTimeout:
            return {"url": url, "title": "(超时)", "status": "timeout"}

    async def screenshot(self, path: str = None):
        """截图"""
        await self._ensure_page()
        if not path:
            safe_name = f"ss_{int(time.time())}.png"
            path = os.path.join(os.environ.get("CRUX_OUTPUT_DIR", "."), safe_name)
        await self._page.screenshot(path=path, full_page=False)
        return {"path": os.path.abspath(path)}

    async def click(self, selector: str):
        """点击元素"""
        await self._ensure_page()
        await self._page.click(selector, timeout=5000)
        await asyncio.sleep(0.5)
        return {"selector": selector, "url": self._page.url}

    async def fill(self, selector: str, text: str):
        """填写输入框"""
        await self._ensure_page()
        await self._page.fill(selector, text)
        return {"selector": selector, "length": len(text)}

    async def press(self, key: str):
        """按键盘键"""
        await self._ensure_page()
        await self._page.keyboard.press(key)
        return {"key": key}

    async def evaluate(self, js: str):
        """执行 JS"""
        await self._ensure_page()
        return {"result": await self._page.evaluate(js)}

    async def get_text(self, selector: str = "body"):
        """获取元素的文本内容"""
        await self._ensure_page()
        els = await self._page.query_selector_all(selector)
        if not els:
            return {"text": ""}
        texts = []
        for el in els[:30]:
            try:
                t = await el.inner_text()
                texts.append(t[:200])
            except: pass
        if len(texts) == 1:
            return {"text": texts[0]}
        return {"texts": texts, "count": len(texts)}

    async def get_links(self):
        """获取页面所有链接"""
        await self._ensure_page()
        links = await self._page.eval_on_selector_all(
            "a[href]", "els => els.map(el => ({text: el.innerText.trim(), href: el.href}))"
        )
        return {"links": [l for l in links if l["text"]][:50]}

    async def wait(self, seconds: float):
        """等待"""
        await asyncio.sleep(seconds)

    async def close(self):
        """关闭浏览器"""
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.__aexit__(None, None, None)
        except: pass
        self._browser = None
        self._pw = None
        self._page = None


# === CLI 单命令模式 ===
COMMANDS = {"goto", "screenshot", "click", "fill", "press", "eval", "text", "links", "wait"}


async def main_cli():
    if len(sys.argv) < 2:
        print("Edge Engine CLI")
        print("用法: python edge_engine.py <命令> [参数...]")
        print(f"命令: {', '.join(sorted(COMMANDS))}")
        return

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"未知命令: {cmd}")
        return

    async with EdgeEngine() as engine:
        if cmd == "goto":
            url = sys.argv[2] if len(sys.argv) > 2 else "https://www.baidu.com"
            r = await engine.goto(url)
            print(json.dumps(r, ensure_ascii=False))

        elif cmd == "screenshot":
            path = sys.argv[2] if len(sys.argv) > 2 else None
            r = await engine.screenshot(path)
            print(json.dumps(r, ensure_ascii=False))

        elif cmd == "click":
            sel = sys.argv[2] if len(sys.argv) > 2 else "body"
            r = await engine.click(sel)
            print(json.dumps(r, ensure_ascii=False))

        elif cmd == "fill":
            sel = sys.argv[2] if len(sys.argv) > 2 else "input"
            text = sys.argv[3] if len(sys.argv) > 3 else ""
            r = await engine.fill(sel, text)
            print(json.dumps(r, ensure_ascii=False))

        elif cmd == "press":
            key = sys.argv[2] if len(sys.argv) > 2 else "Enter"
            r = await engine.press(key)
            print(json.dumps(r, ensure_ascii=False))

        elif cmd == "eval":
            js = sys.argv[2] if len(sys.argv) > 2 else "document.title"
            r = await engine.evaluate(js)
            print(json.dumps(r, ensure_ascii=False))

        elif cmd == "text":
            sel = sys.argv[2] if len(sys.argv) > 2 else "body"
            r = await engine.get_text(sel)
            print(json.dumps(r, ensure_ascii=False, indent=2))

        elif cmd == "links":
            r = await engine.get_links()
            print(json.dumps(r, ensure_ascii=False, indent=2))

        elif cmd == "wait":
            sec = float(sys.argv[2]) if len(sys.argv) > 2 else 1
            await engine.wait(sec)


if __name__ == "__main__":
    asyncio.run(main_cli())
