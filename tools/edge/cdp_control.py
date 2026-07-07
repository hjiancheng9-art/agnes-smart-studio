"""
Edge CDP Controller — 通过 CDP 控制已打开的 Edge + ChatGPT
用法: python tools/edge/cdp_control.py <命令> [参数]

命令:
  status         查看当前页状态
  goto <url>     导航到 URL
  send <文本>    在 ChatGPT 输入框发送消息
  read [行数]    读取 ChatGPT 最新回复
  screenshot     截图
  js <code>      执行 JS
  list           列出所有标签页
  switch <n>     切换到第 n 个标签页
  close          关闭当前标签页
"""
import sys, requests, json, time
from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"

def get_browser():
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(CDP_URL)
    return p, browser

def cmd_status():
    p, browser = get_browser()
    pages = browser.contexts[0].pages if browser.contexts else []
    if not pages:
        print("❌ 没有打开的标签页")
    else:
        for i, page in enumerate(pages):
            print(f"  [{i}] {page.title()} | {page.url}")
        active = pages[-1]
        print(f"\n当前活跃: [{len(pages)-1}] {active.title()}")
        print(f"  URL: {active.url}")
    p.stop()

def cmd_goto(url):
    p, browser = get_browser()
    page = browser.contexts[0].pages[-1] if browser.contexts else browser.contexts[0].new_page()
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle")
    print(f"✅ 已导航到: {page.url}")
    p.stop()

def cmd_send(text):
    p, browser = get_browser()
    page = browser.contexts[0].pages[-1]
    # Try multiple selectors for ChatGPT input
    selectors = [
        '#prompt-textarea',  # ChatGPT new UI (ProseMirror)
        'div[contenteditable="true"]',
        'textarea[placeholder*="问题"]',
        'textarea[placeholder*="Message"]',
        'div[contenteditable="true"][role="textbox"]',
    ]
    input_el = None
    for sel in selectors:
        try:
            input_el = page.wait_for_selector(sel, timeout=3000)
            if input_el:
                break
        except:
            continue
    
    if not input_el:
        print("❌ 找不到 ChatGPT 输入框")
        page.screenshot(path="_error.png")
        p.stop()
        return
    
    input_el.click()
    input_el.fill("")
    page.keyboard.type(text, delay=10)
    time.sleep(0.5)
    page.keyboard.press("Enter")
    print(f"✅ 已发送消息 ({len(text)} 字符)")
    time.sleep(2)
    p.stop()

def cmd_read(lines=30):
    p, browser = get_browser()
    page = browser.contexts[0].pages[-1]
    time.sleep(1)
    # Get all message elements
    texts = page.evaluate("""
        () => {
            const msgs = document.querySelectorAll('[data-message-content]');
            return Array.from(msgs).slice(-30).map(m => m.innerText).join('\\n---\\n');
        }
    """)
    if texts:
        print(texts[:3000])
    else:
        # Fallback: get body text
        print(page.inner_text("body")[:2000])
    p.stop()

def cmd_js(code):
    p, browser = get_browser()
    page = browser.contexts[0].pages[-1]
    result = page.evaluate(code)
    print(f"Result:\n{json.dumps(result, indent=2, ensure_ascii=False)[:2000]}")
    p.stop()

def cmd_list():
    p, browser = get_browser()
    for ctx in browser.contexts:
        for i, page in enumerate(ctx.pages):
            print(f"  [{i}] {page.title()} | {page.url}")
    print(f"  总计: {sum(len(ctx.pages) for ctx in browser.contexts)} 个标签页")
    p.stop()

def cmd_switch(idx):
    p, browser = get_browser()
    pages = browser.contexts[0].pages
    if idx < 0 or idx >= len(pages):
        print(f"❌ 索引 {idx} 超出范围 (0-{len(pages)-1})")
    else:
        pages[idx].bring_to_front()
        print(f"✅ 已切换到: [{idx}] {pages[idx].title()}")
    p.stop()

def cmd_screenshot():
    p, browser = get_browser()
    page = browser.contexts[0].pages[-1]
    path = "_cdp_screenshot.png"
    page.screenshot(path=path, full_page=True)
    print(f"✅ 截图已保存: {path}")
    p.stop()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    args = sys.argv[2:]
    
    cmds = {
        "status": cmd_status,
        "goto": cmd_goto,
        "send": cmd_send,
        "read": cmd_read,
        "screenshot": cmd_screenshot,
        "js": cmd_js,
        "list": cmd_list,
        "switch": cmd_switch,
    }
    
    if cmd in cmds:
        cmds[cmd](*args)
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
