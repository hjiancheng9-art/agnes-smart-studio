from playwright.sync_api import sync_playwright
import time, sys

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = browser.contexts[0].pages[0]
    page.bring_to_front()
    time.sleep(1)
    
    # Check current state
    state = page.evaluate("""() => {
        const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
        const last = msgs[msgs.length - 1];
        return {
            count: msgs.length,
            last_len: last ? last.innerText.length : 0,
            generating: !!document.querySelector('button[aria-label="Stop"]'),
            preview: last ? last.innerText.substring(0, 100) : ''
        };
    }""")
    
    with open('output/chatgpt_state.txt', 'w') as f:
        f.write(str(state))
    
    if state['last_len'] > 500 and not state['generating']:
        text = page.evaluate("""() => {
            const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            return msgs[msgs.length - 1].innerText;
        }""")
        with open('output/chatgpt_verdict.txt', 'w', encoding='utf-8') as f:
            f.write(text)
    
    browser.close()
