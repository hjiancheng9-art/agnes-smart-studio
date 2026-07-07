47: def cmd_send(text):
48:     p, browser = get_browser()
49:     page = browser.contexts[0].pages[-1]
50:     # Try multiple selectors for ChatGPT input
51:     selectors = [
52:         'div[contenteditable="true"][data-placeholder*="消息"]',
53:         'div[contenteditable="true"][data-placeholder*="Message"]',
54:         'div[contenteditable="true"][role="textbox"]',
55:         '#prompt-textarea',
56:         'div[contenteditable="true"]',
57:     ]
58:     input_el = None
59:     for sel in selectors:
60:         try:
61:             input_el = page.wait_for_selector(sel, timeout=3000)
62:             if input_el:
63:                 break
64:         except:
65:             continue
66:     
67:     if not input_el:
68:         print("❌ 找不到 ChatGPT 输入框")
69:         page.screenshot(path="_error.png")
70:         p.stop()
71:         return
72:     
73:     input_el.click()
74:     input_el.fill("")
75:     page.keyboard.type(text, delay=10)
76:     time.sleep(0.5)
77:     page.keyboard.press("Enter")
78:     print(f"✅ 已发送消息 ({len(text)} 字符)")
79:     time.sleep(2)
80:     p.stop()
81: 
82: def cmd_read(lines=30):
83:     p, browser = get_browser()
84:     page = browser.contexts[0].pages[-1]
85:     time.sleep(1)
86:     # Get all message elements
87:     texts = page.evaluate("""
88:         () => {
89:             const msgs = document.querySelectorAll('[data-message-content]');
90:             return Array.from(msgs).slice(-30).map(m => m.innerText).join('\\n---\\n');
91:         }
92:     """)
93:     if texts:
94:         print(texts[:3000])
95:     else:
96:         # Fallback: get body text
97:         print(page.inner_text("body")[:2000])
98:     p.stop()
99: 
100: def cmd_js(code):
101:     p, browser = get_browser()
102:     page = browser.contexts[0].pages[-1]
103:     result = page.evaluate(code)
104:     print(f"Result:\n{json.dumps(result, indent=2, ensure_ascii=False)[:2000]}")
105:     p.stop()
106: 
107: def cmd_list():
108:     p, browser = get_browser()
