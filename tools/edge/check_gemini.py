from playwright.sync_api import sync_playwright
import time, sys

CDP_URL = "http://127.0.0.1:9222"
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

for ctx in browser.contexts:
    for pg in ctx.pages:
        if 'gemini.google.com' in pg.url:
            pg.bring_to_front()
            time.sleep(1)
            main_text = pg.evaluate('() => document.querySelector("main")?.innerText || document.body.innerText')
            print(f"Gemini content ({len(main_text)} chars):")
            print(main_text[:3000])

p.stop()
