import sys

from playwright.sync_api import sync_playwright


def log(*args):
    msg = " ".join(str(a) for a in args)
    with open('output/chatgpt_log.txt', 'a', encoding='utf-8') as f:
        f.write(msg + "\n")
    print(msg, flush=True)

try:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = browser.contexts[0].pages[0]
        page.wait_for_timeout(1000)

        log(f"Current URL: {page.url}")

        # Click on the input to focus
        page.click('#prompt-textarea')
        page.wait_for_timeout(500)

        # Type message
        msg = "你好ChatGPT，请帮我做一次完整的架构诊断。我是CRUX Studio，一个AI-native平台。"
        page.keyboard.type(msg, delay=5)
        page.wait_for_timeout(500)

        text_content = page.evaluate('() => document.querySelector("#prompt-textarea").innerText')
        log(f"Entered text ({len(text_content)} chars): {text_content[:100]}")

        if len(text_content) > 5:
            page.keyboard.press('Enter')
            log("Message sent via Enter!")
            page.wait_for_timeout(8000)

            body = page.evaluate('() => document.body.innerText')
            log(f"Body ({len(body)} chars)")
            log(f"Body preview: {body[:500]}")
            page.screenshot(path='output/chatgpt_result.png')
            log("Screenshot saved")
        else:
            log("Text entry failed - trying execCommand")
            # Try alternative
            page.evaluate('document.execCommand("insertText", false, "' + msg + '")')
            page.wait_for_timeout(500)
            page.keyboard.press('Enter')
            page.wait_for_timeout(5000)
            page.screenshot(path='output/chatgpt_result2.png')
            log("Alternative approach done")

        browser.close()
except Exception as e:
    log(f"ERROR: {str(e)}")
    sys.exit(1)
