"""测试：Playwright 启动 Edge → ChatGPT → 发送并读取回复"""
import time

from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
print("Playwright 已启动")

browser = pw.chromium.launch(
    channel="msedge",
    headless=False,
    args=["--start-maximized"],
)
print("Edge 已启动")

context = browser.contexts[0] if browser.contexts else browser.new_context()
page = context.pages[0] if context.pages else context.new_page()

page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=30000)
page.bring_to_front()
print(f"页面: {page.title()}")
time.sleep(3)

# 找输入框
el = None
for s in [
    'div#prompt-textarea[contenteditable="true"]',
    '[contenteditable="true"]',
    'textarea',
]:
    try:
        e = page.locator(s).first
        if e.is_visible(timeout=2000):
            el = e
            print(f"输入框: {s}")
            break
    except:
        continue
if not el:
    print("找不到输入框")
    exit(1)

el.click()
time.sleep(0.3)
el.type("用一句话介绍你自己", delay=30)
print("已填入")
page.keyboard.press("Enter")
print("已提交，等待回复...")

# 轮询
for i in range(90):
    time.sleep(2)
    try:
        rs = page.locator('[data-message-author-role="assistant"]').all()
        for r in rs:
            if not r.is_visible():
                continue
            t = r.inner_text().strip()
            if len(t) > 15:
                print("=" * 40)
                print(f"ChatGPT 回复 ({len(t)}字):")
                print(t[:1000])
                print("=" * 40)
                print("测试成功！")
                exit(0)
    except:
        import logging; logging.getLogger('crux').debug('silent except', exc_info=True)

print("等待超时")
