from playwright.sync_api import sync_playwright
import os, time

CDP_URL = "http://127.0.0.1:9222"
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

for ctx in browser.contexts:
    for pg in ctx.pages:
        if 'gemini' in pg.url:
            pg.bring_to_front()
            time.sleep(0.3)
            
            # Get model response text
            text = pg.evaluate("""() => {
                const els = document.querySelectorAll('.model-response-text');
                let output = '';
                els.forEach((el, i) => {
                    output += `========== Gemini Response ${i+1} ==========\n`;
                    output += el.innerText;
                    output += '\n\n';
                });
                return output || document.querySelector('main')?.innerText || 'No response found';
            }""")
            
            # Save with unique name
            path = os.path.join('tools', 'edge', 'gemini_full_verdict.txt')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"SAVED to {path}: {len(text)} chars")
            print(text[:500])
            print("...")
            print(text[-500:])

p.stop()
