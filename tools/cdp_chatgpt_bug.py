"""Send bug analysis question to ChatGPT via CDP and read reply."""
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright

OUTPUT_DIR = "output"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]

    # Check existing pages for our previous conversation
    for pg in ctx.pages:
        try:
            if "chatgpt" not in pg.url:
                continue
            articles = pg.query_selector_all("article")
            for art in articles:
                txt = art.inner_text()
                if "可能原因" in txt and "修复方向" in txt and len(txt) > 100:
                    print(f"FOUND_EXISTING\n{txt}")
                    with open(os.path.join(OUTPUT_DIR, "chatgpt_bug_analysis.txt"), "w", encoding="utf-8") as f:
                        f.write(txt)
                    browser.close()
                    exit(0)
        except Exception as e:
            print(f"Check error: {e}")

    # Not found, create new page and send question
    page = ctx.new_page()
    page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)

    question = """我在使用一个AI编程助手工具(CRUX Studio v6.0)，通过CDP连接Edge浏览器操控ChatGPT网页版。发现3个bug请分析原因和修复方向：

1. 输入区偶尔弹出大量历史消息片段/乱码
2. 长对话后鼠标滚轮和键盘滚动突然失效，只能刷新恢复
3. 模型断连后无法自动重连，只能关闭对话重开新会话

从前端状态管理、WebSocket连接管理、DOM事件冒泡、内存泄漏角度分析。200字内简短回答。"""

    textarea = page.query_selector("#prompt-textarea")
    if not textarea:
        print("ERROR: no textarea found")
        page.screenshot(path=os.path.join(OUTPUT_DIR, "chatgpt_error.png"))
        browser.close()
        exit(1)

    textarea.fill(question)
    time.sleep(0.5)
    textarea.press("Enter")
    print("SENT: 问题已发送")

    # Wait for response with polling (up to 2 minutes)
    for i in range(24):
        time.sleep(5)
        articles = page.query_selector_all("article")
        for art in articles[-3:]:
            txt = art.inner_text()
            if "可能原因" in txt and len(txt) > 200:
                print(f"\n===== ChatGPT 回复 ({len(txt)} 字符) =====\n{txt}")
                with open(os.path.join(OUTPUT_DIR, "chatgpt_bug_analysis.txt"), "w", encoding="utf-8") as f:
                    f.write(txt)
                browser.close()
                exit(0)
        if i % 3 == 0:
            print(f"等待中... ({5*(i+1)}秒)")

    # Timeout fallback
    page.screenshot(path=os.path.join(OUTPUT_DIR, "chatgpt_timeout.png"))
    print("TIMEOUT: 2分钟内未获取到回复")
    browser.close()
