"""Second try - fetch fresh Zhipu response"""
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
    time.sleep(0.5)
    text = page.evaluate("() => document.body.innerText")
    out = os.path.join('tools', 'edge', 'zhipu_final.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"SAVED {len(text)} chars to {out}")
    # Print the debate-relevant part
    if '正方' in text:
        idx = text.index('正方')
        print(text[max(0,idx-50):][:3000])
    else:
        print(text[:2000])
else:
    print("Zhipu page not found!")

p.stop()
