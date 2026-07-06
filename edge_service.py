"""Edge 持久化后台服务 (headless)"""
import asyncio, json, os, sys, signal
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from playwright.async_api import async_playwright

SVC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", ".edge_svc")
os.makedirs(SVC_DIR, exist_ok=True)
PID_FILE = os.path.join(SVC_DIR, "pid")
CMD_FILE = os.path.join(SVC_DIR, "command.json")
RESP_FILE = os.path.join(SVC_DIR, "response.json")


async def main():
    pw = await async_playwright().__aenter__()
    
    browser = await pw.chromium.launch(
        channel="msedge",
        headless=True,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )
    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    
    # Write PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    
    # Open initial page
    try:
        await page.goto("https://www.baidu.com", timeout=15000, wait_until="domcontentloaded")
        print(f"OK|READY|{await page.title()}")
    except:
        print("OK|READY|blank")
    
    sys.stdout.flush()
    
    running = True
    while running:
        try:
            if os.path.exists(CMD_FILE):
                with open(CMD_FILE, "r") as f:
                    cmd = json.load(f)
                os.unlink(CMD_FILE)
                
                action = cmd.get("action", "")
                params = cmd.get("params", {})
                result = {"status": "ok"}
                
                if action == "goto":
                    url = params.get("url", "https://www.baidu.com")
                    try:
                        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                        await asyncio.sleep(1)
                        result = {"url": page.url, "title": await page.title()}
                    except Exception as e:
                        result = {"status": "timeout", "url": url, "error": str(e)[:100]}
                
                elif action == "screenshot":
                    path = params.get("path", os.path.join(SVC_DIR, f"ss_{int(asyncio.get_event_loop().time())}.png"))
                    await page.screenshot(path=path)
                    result = {"path": path}
                
                elif action == "click":
                    await page.click(params["selector"], timeout=5000)
                    await asyncio.sleep(0.5)
                    result = {"url": page.url}
                
                elif action == "fill":
                    await page.fill(params["selector"], params["text"])
                    result = {"ok": True}
                
                elif action == "press":
                    await page.keyboard.press(params.get("key", "Enter"))
                    await asyncio.sleep(1)
                    result = {"ok": True}
                
                elif action == "text":
                    sel = params.get("selector", "body")
                    els = await page.query_selector_all(sel)
                    texts = [await el.inner_text() for el in els[:30]]
                    result = {"texts": texts, "count": len(texts)} if len(texts) > 1 else {"text": texts[0] if texts else ""}
                
                elif action == "eval":
                    result = {"result": await page.evaluate(params["js"])}
                
                elif action == "url":
                    result = {"url": page.url, "title": await page.title()}
                
                elif action == "stop":
                    running = False
                    result = {"status": "stopping"}
                
                with open(RESP_FILE, "w") as f:
                    json.dump(result, f, ensure_ascii=False, default=str)
            
            await asyncio.sleep(0.3)
        except Exception as e:
            try:
                with open(RESP_FILE, "w") as f:
                    json.dump({"status": "error", "error": str(e)}, f, ensure_ascii=False)
            except: pass
    
    await browser.close()
    await pw.__aexit__(None, None, None)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
