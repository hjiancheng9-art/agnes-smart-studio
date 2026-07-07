from playwright.sync_api import sync_playwright
CDP_URL = "http://127.0.0.1:9222"
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

page = None
for ctx in browser.contexts:
    for pg in ctx.pages:
        if 'gemini.google.com' in pg.url:
            page = pg
            break

if page:
    page.bring_to_front()
    full = page.evaluate("""() => {
        const els = document.querySelectorAll('.model-response-text');
        return Array.from(els).map((el, i) => `[Gemini Response ${i}]\n${el.innerText}`).join('\n\n');
    }""")
    print(full)
    with open('tools/edge/gemini_verdict.txt', 'w', encoding='utf-8') as f:
        f.write(full)
    print(f"\n✅ Saved {len(full)} chars")
else:
    print("Gemini page not found")

p.stop()
