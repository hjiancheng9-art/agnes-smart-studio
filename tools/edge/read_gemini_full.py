import time

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

page = None
for ctx in browser.contexts:
    for pg in ctx.pages:
        if "gemini" in pg.url:
            page = pg
            break

if page:
    page.bring_to_front()
    time.sleep(12)

    result = page.evaluate("""() => {
        const stopBtn = document.querySelector('[aria-label="停止"], button[aria-label*="停止"]');
        const els = document.querySelectorAll('.model-response-text');
        return {
            generating: !!stopBtn,
            count: els.length,
            texts: Array.from(els).map((el, i) => `=== Response ${i} (${el.innerText.length}chars) ===\n${el.innerText}`).join('\n\n')
        };
    }""")

    print(f"generating={result['generating']}, count={result['count']}")
    print(result["texts"])

    with open("tools/edge/gemini_verdict.txt", "w", encoding="utf-8") as f:
        f.write(result["texts"])
else:
    print("Gemini page not found!")

p.stop()
