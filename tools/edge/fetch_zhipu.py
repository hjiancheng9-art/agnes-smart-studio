"""Fetch Zhipu response"""

import time

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

for ctx in browser.contexts:
    for pg in ctx.pages:
        if "open.bigmodel" in pg.url:
            pg.bring_to_front()
            time.sleep(1)

            # Check for stop button first
            info = pg.evaluate("""() => {
                const stopBtn = document.querySelector('button:has-text("停止生成")');
                const mainText = document.body.innerText;
                return {generating: !!stopBtn, length: mainText.length, text: mainText};
            }""")

            print(f"generating={info['generating']}, {info['length']}chars")

            # Get conversation messages
            msgs = pg.evaluate("""() => {
                const chatContainer = document.querySelector('.chat-messages, .message-list, .conversation, [class*="message"], main') || document.body;
                const allDivs = chatContainer.querySelectorAll('div');
                const texts = [];
                allDivs.forEach(d => {
                    const t = d.innerText.trim();
                    if (t && t.length > 10) texts.push(t);
                });
                return [...new Set(texts)].join('\\n---\\n');
            }""")

            path = "tools/edge/zhipu_full_verdict.txt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(msgs if len(msgs) > len(info["text"]) else info["text"])
            print(f"Saved {len(msgs)} chars")
            print(msgs[:2000])
            break

p.stop()
