from playwright.sync_api import sync_playwright
import time

MSG_TO_ALL = """你是一个AI架构审查官。请审查以下代码架构并指出最严重的3个问题：

CRUX Studio — AI-native平台，367个py文件，核心模块：
1. multi_agent.py (1047行): 多Agent编排，已实现DAG拓扑分层、trace_id链路追踪、root_trace_id语义
2. provider.py (626行): 动态fallback链，4通道deepseek/crux/zhipu/local，已加递归depth防护
3. cost_tracker.py (308行): 记录API token消耗和花费
4. observability.py (306行): span/trace基础

今日已修：无声异常修复、trace_id自动生成、重复ID检测、工具边界trace注入、root_trace_id语义重构。

请指出最该继续修的3个问题，具体到文件名和函数名。"""

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    pages = context.pages
    
    for page in pages:
        url = page.url
        page.bring_to_front()
        time.sleep(0.5)
        
        if 'chatgpt.com/c/' in url:
            # ChatGPT - short follow up
            msg = "最终裁决给了吗？"
            page.click('#prompt-textarea')
            time.sleep(0.2)
            page.keyboard.type(msg, delay=2)
            time.sleep(0.2)
            page.keyboard.press('Enter')
            print("✅ ChatGPT: 已推送")
        
        elif 'gemini.google.com' in url:
            try:
                # Check if textarea exists
                has_input = page.evaluate("() => !!document.querySelector('[contenteditable=\"true\"]')")
                if has_input:
                    page.click('[contenteditable="true"]')
                    time.sleep(0.2)
                    page.keyboard.type(MSG_TO_ALL[:500], delay=1)
                    time.sleep(0.3)
                    page.keyboard.press('Enter')
                    print("✅ Gemini: 已发送")
            except:
                print("❌ Gemini: 发送失败")
        
        elif 'kimi.moonshot' in url:
            try:
                page.click('[contenteditable="true"]')
                time.sleep(0.2)
                page.keyboard.type(MSG_TO_ALL[:400], delay=1)
                time.sleep(0.3)
                page.keyboard.press('Enter')
                print("✅ Kimi: 已发送")
            except:
                print("❌ Kimi: 发送失败")
        
        elif 'zhipu' in url or 'bigmodel' in url:
            try:
                page.click('textarea')
                time.sleep(0.2)
                page.keyboard.type(MSG_TO_ALL[:400], delay=1)
                time.sleep(0.3)
                page.keyboard.press('Enter')
                print("✅ 智谱: 已发送")
            except:
                print("❌ 智谱: 发送失败")
    
    print("\n四线全发，等待回复...")
    time.sleep(30)
    
    # Collect responses
    for page in context.pages:
        url = page.url
        page.bring_to_front()
        time.sleep(0.3)
        
        if 'chatgpt.com/c/' in url:
            state = page.evaluate("""() => {
                const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                const last = msgs[msgs.length - 1];
                return {count: msgs.length, last_len: last ? last.innerText.length : 0, generating: !!document.querySelector('button[aria-label=\"Stop\"]')};
            }""")
            print(f"\nChatGPT: {state['count']}条回复, 最新{state['last_len']}字")
        
        elif 'gemini.google.com' in url:
            body = page.evaluate("() => document.body.innerText")
            # Check if response contains our keywords
            has_crux = 'CRUX' in body or 'multi_agent' in body
            print(f"\nGemini: {'✅ 已回复' if has_crux else '⏳ 等待中'}")
        
        elif 'kimi.moonshot' in url:
            body = page.evaluate("() => document.body.innerText")
            has_crux = 'CRUX' in body or 'multi_agent' in body
            print(f"Kimi: {'✅ 已回复' if has_crux else '⏳ 等待中'}")
        
        elif 'zhipu' in url or 'bigmodel' in url:
            body = page.evaluate("() => document.body.innerText")
            has_crux = 'CRUX' in body or 'multi_agent' in body
            print(f"智谱: {'✅ 已回复' if has_crux else '⏳ 等待中'}")
    
    # Save all responses
    for page in context.pages:
        url = page.url
        if 'chatgpt.com/c/' in url:
            text = page.evaluate("""() => {
                const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                return Array.from(msgs).map(m => m.innerText);
            }""")
            if text:
                with open('output/chatgpt_final.txt', 'w', encoding='utf-8') as f:
                    for i, t in enumerate(text):
                        f.write(f"\n=== #{i+1} ===\n{t}\n")
                print(f"ChatGPT: 已保存{len(text)}条回复")
        
        elif 'gemini.google.com' in url:
            text = page.evaluate("() => document.body.innerText")
            with open('output/gemini_final.txt', 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"Gemini: 已保存{len(text)}字")
        
        elif 'kimi.moonshot' in url:
            text = page.evaluate("() => document.body.innerText")
            with open('output/kimi_final.txt', 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"Kimi: 已保存{len(text)}字")
        
        elif 'zhipu' in url or 'bigmodel' in url:
            text = page.evaluate("() => document.body.innerText")
            with open('output/zhipu_final.txt', 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"智谱: 已保存{len(text)}字")
    
    browser.close()
