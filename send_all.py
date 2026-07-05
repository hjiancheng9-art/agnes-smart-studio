from playwright.sync_api import sync_playwright
import time, sys

def send():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        for page in browser.contexts[0].pages:
            url = page.url
            if 'gemini' in url:
                page.bring_to_front(); time.sleep(0.5)
                body = page.evaluate("() => document.body.innerText")
                if 'CRUX' not in body:
                    el = page.evaluate("""() => { const e=document.querySelector('[contenteditable="true"]'); if(e){e.innerHTML='';return true;} return false; }""")
                    if el:
                        page.keyboard.type("CRUX Studio架构审查：367个py文件，multi_agent.py含DAG拓扑+root_trace_id。最该修的3个问题？", delay=2)
                        time.sleep(0.3); page.keyboard.press('Enter')
                        sys.stdout.write("G")
            if 'kimi' in url:
                page.bring_to_front(); time.sleep(0.5)
                body = page.evaluate("() => document.body.innerText")
                if 'CRUX' not in body:
                    el = page.evaluate("""() => { const e=document.querySelector('[contenteditable="true"]'); if(e){e.innerHTML='';return true;} return false; }""")
                    if el:
                        page.keyboard.type("CRUX Studio架构诊断：367个py文件，multi_agent/provider/cost_tracker。最该修的3个问题？", delay=2)
                        time.sleep(0.3); page.keyboard.press('Enter')
                        sys.stdout.write("K")
            if 'zhipu' in url or 'bigmodel' in url:
                page.bring_to_front(); time.sleep(0.5)
                body = page.evaluate("() => document.body.innerText")
                if 'CRUX' not in body:
                    page.click('textarea'); time.sleep(0.2)
                    page.keyboard.type("CRUX Studio架构审查：367个py文件。请指出最严重的3个架构问题。", delay=2)
                    time.sleep(0.3); page.keyboard.press('Enter')
                    sys.stdout.write("Z")
        sys.stdout.write("\nAll sent, waiting...\n")
        time.sleep(30)
        
        for page in browser.contexts[0].pages:
            url = page.url
            text = page.evaluate("() => document.body.innerText")
            if 'gemini' in url and 'CRUX' in text:
                with open('output/gemini_r.txt','w',encoding='utf-8') as f: f.write(text)
                sys.stdout.write("Gemini saved\n")
            if 'kimi' in url and 'CRUX' in text:
                with open('output/kimi_r.txt','w',encoding='utf-8') as f: f.write(text)
                sys.stdout.write("Kimi saved\n")
            if ('zhipu' in url or 'bigmodel' in url) and ('CRUX' in text or 'Studio' in text):
                with open('output/zhipu_r.txt','w',encoding='utf-8') as f: f.write(text)
                sys.stdout.write("Zhipu saved\n")
        
        browser.close()

send()
