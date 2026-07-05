from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].pages[0]
    page.wait_for_timeout(1000)

    info = page.evaluate('() => { const el = document.querySelector("#prompt-textarea"); if (!el) return {error: "not found"}; return { tag: el.tagName, id: el.id, "class": el.className, type: el.type, role: el.getAttribute("role"), placeholder: el.placeholder, value_len: el.value ? el.value.length : 0, innerText_length: el.innerText ? el.innerText.length : 0, childElementCount: el.childElementCount, isContentEditable: el.isContentEditable, style: el.getAttribute("style") ? el.getAttribute("style").substring(0, 100) : "" }; }')
    import json
    print(json.dumps(info, indent=2, ensure_ascii=False))
    browser.close()
