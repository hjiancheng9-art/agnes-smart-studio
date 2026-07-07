"""
CRUX ChatGPT Automator - 等待登录后自动发送消息
"""
import asyncio, json, urllib.request, sys
from playwright.async_api import async_playwright

BRIDGE_URL = "http://127.0.0.1:4366"

async def push_task(prompt):
    data = json.dumps({"provider": "chatgpt", "prompt": prompt}).encode()
    req = urllib.request.Request(
        f"{BRIDGE_URL}/api/browser-companion/tasks/push",
        data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["task"]

async def report_result(task_id, result_text):
    data = json.dumps({"result": result_text}).encode()
    req = urllib.request.Request(
        f"{BRIDGE_URL}/api/browser-companion/tasks/{task_id}/result",
        data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req):
        pass

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        
        page = None
        for pg in context.pages:
            if "chatgpt.com" in pg.url:
                page = pg
                break
        if not page:
            page = await context.new_page()
            await page.goto("https://chatgpt.com/")
        
        await page.bring_to_front()
        print("⏳ 等待 ChatGPT 登录...")
        sys.stdout.flush()
        
        for i in range(200):
            await asyncio.sleep(3)
            
            info = await page.evaluate("""() => {
                const text = document.body.innerText;
                const hasLogin = text.includes("登录") && text.includes("免费注册");
                const hasInput = !!document.querySelector('textarea');
                return { hasLogin, hasInput };
            }""")
            
            if info["hasInput"]:
                print(f"✅ 检测到输入框! (等了 {i*3} 秒)")
                break
            
            if not info["hasLogin"]:
                print(f"✅ 登录状态已变更! (等了 {i*3} 秒)")
                await asyncio.sleep(3)
                break
            
            if i % 10 == 0:
                print(f"  等待登录中... ({i*3} 秒)")
                sys.stdout.flush()
        else:
            print("⏰ 登录等待超时")
            return
        
        print("📋 推送任务...")
        task = await push_task("你好！请用中文回复，告诉我今天的日期和星期。")
        print(f"  任务ID: {task['taskId']}")
        
        ta = page.locator("textarea").first
        await ta.wait_for(state="visible", timeout=10000)
        await ta.click()
        await ta.fill(task["prompt"])
        await asyncio.sleep(0.5)
        await ta.press("Enter")
        print("✉️ 已发送!")
        
        print("⏳ 等待 AI 回复...")
        for j in range(60):
            await asyncio.sleep(2)
            
            resp = await page.evaluate("""() => {
                const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                if (msgs.length > 0) {
                    const last = msgs[msgs.length - 1];
                    const text = last.textContent;
                    const stopBtn = document.querySelector('[data-testid="stop-button"]');
                    if (text && text.length > 30 && !stopBtn) {
                        return { done: true, text: text };
                    }
                    return { done: false, partial: (text || "").substring(0, 80) };
                }
                return { done: false, partial: "" };
            }""")
            
            if resp.get("done"):
                print(f"\n✅ AI 回复完成!")
                print(resp["text"][:600])
                await report_result(task["taskId"], resp["text"])
                print("✅ 结果已回传!")
                return
            
            if j % 5 == 0:
                p = resp.get("partial", "")
                print(f"  等待中... ({j*2}s) {p[:40] if p else ''}")
                sys.stdout.flush()
        
        print("⏰ 回复超时")

if __name__ == "__main__":
    asyncio.run(main())
