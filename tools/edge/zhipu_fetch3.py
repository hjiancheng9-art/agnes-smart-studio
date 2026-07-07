"""Fetch Zhipu response - wait for completion"""
import os
import time

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

page = None
for ctx in browser.contexts:
    for pg in ctx.pages:
        if 'open.bigmodel' in pg.url:
            page = pg
            break

if page:
    page.bring_to_front()

    # Wait for generation to finish (wait for stop button to disappear)
    for i in range(20):
        info = page.evaluate("""() => {
            const stopBtn = document.querySelector('button:has-text("停止生成")');
            return {generating: !!stopBtn, len: document.body.innerText.length};
        }""")
        if not info['generating'] and info['len'] > 800:
            break
        time.sleep(3)

    # Get the complete text
    text = page.evaluate("() => document.body.innerText")
    out = os.path.join('tools', 'edge', 'zhipu_complete.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"SAVED {len(text)} chars")

    # Print debate sections
    for marker in ['正方', '反方', '裁决', '论点']:
        idx = text.find(marker)
        if idx >= 0:
            print(f"\n[{marker}]:")
            print(text[idx:idx+600])

p.stop()
