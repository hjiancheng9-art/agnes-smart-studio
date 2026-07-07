from playwright.sync_api import sync_playwright
CDP_URL = "http://127.0.0.1:9222"
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

for ctx in browser.contexts:
    for pg in ctx.pages:
        url = pg.url
        if 'gemini' in url:
            texts = pg.evaluate("""() => {
                var els = document.querySelectorAll('.model-response-text');
                var output = '';
                els.forEach(function(el, i) {
                    output += '== Gemini Response ' + (i+1) + ' ==\n';
                    output += el.innerText;
                    output += '\n\n';
                });
                return output;
            }""")
            with open('tools/edge/r2_gemini_complete.txt','w',encoding='utf-8') as f:
                f.write(texts)
            print('Gemini: ' + str(texts.count('Response')) + ' responses, ' + str(len(texts)) + ' chars')
            parts = texts.split('== Gemini Response')
            if len(parts) > 1:
                last = parts[-1]
                print('\n=== 最新回复 ===')
                print(last[:2000])
                
        elif 'bigmodel' in url:
            t = pg.evaluate("() => document.body.innerText")
            with open('tools/edge/r2_zhipu_complete.txt','w',encoding='utf-8') as f:
                f.write(t)
            print('\nZhipu: ' + str(len(t)) + ' chars')
            for kw in ['正方', '反方', 'TRM', '路由']:
                idx = t.find(kw)
                if idx >= 0:
                    print('  [' + kw + '] at ' + str(idx) + ': ' + t[idx:idx+400])
                    break

p.stop()
