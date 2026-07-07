"""Round 1: CWIM Methodology debate - send to ChatGPT, Gemini, Zhipu"""
import time

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

pages = {}
for ctx in browser.contexts:
    for pg in ctx.pages:
        if 'chatgpt.com' in pg.url: pages['chatgpt'] = pg
        elif 'gemini' in pg.url: pages['gemini'] = pg
        elif 'bigmodel' in pg.url: pages['zhipu'] = pg

CWIM_QUESTION = """继续我们关于CRUX Studio v5.0的评审。现在聚焦"CWIM方法论"这个维度。

CRUX 的 CWIM（ComfyUI Workflow Intelligent Methodology）方法论有 10 条核心原则：

1. 永远不要先生成 Workflow — 先理解任务类型/输入输出/约束
2. 优先复用成熟 Workflow — 模板 > Motif组合 > 子图 > 最后才生成
3. LLM 不直接生成 ComfyUI JSON — 必须经过 TaskSpec → WorkflowIR → GraphCompiler
4. 所有 Workflow 必须经过 Validator 校验
5. 失败不是结束，而是学习 — 保存错误/参数/patch
6. 参数不是数字，而是语义 — 按语义维度推荐
7. 所有推荐必须可解释 — 告诉用户"为什么推荐这个"
8. LoRA 是项目，不是文件 — 全生命周期管理
9. Workflow 是图，不是 JSON — 基于图结构操作
10. 用户面对任务，不是节点 — 术语面向任务

请以正反方答辩格式评审 CWIM 方法论：
【正方-CWIM的优势】
- 论点1: 
- 论点2:
- 论点3:

【反方-CWIM的问题】
- 论点1:
- 论点2:
- 论点3:

【正反交锋】
【你的最终评分】1-10分，并说明理由"""

def type_and_send(page, text, send_selector=None, press_enter=False):
    """Type text into a page and send it"""
    page.bring_to_front()
    time.sleep(0.8)

    # Find input
    selectors = ['[contenteditable="true"]', 'textarea', '[role="textbox"]']
    input_el = None
    for s in selectors:
        try:
            el = page.query_selector(s)
            if el and el.is_visible():
                input_el = el
                break
        except:
            pass

    if not input_el:
        print(f"  ❌ No input found on {page.url[:40]}")
        return False

    input_el.click()
    time.sleep(0.3)
    input_el.fill('')
    time.sleep(0.2)
    page.keyboard.insert_text(text)
    time.sleep(1)

    if send_selector:
        btn = page.query_selector(send_selector)
        if btn and not btn.is_disabled():
            btn.click()
            return True

    if press_enter:
        page.keyboard.press('Enter')
        return True

    # Auto-detect send button
    is_gemini = 'gemini' in page.url
    is_zhipu = 'bigmodel' in page.url
    result = page.evaluate("""(args) => {
        const isGemini = args.isGemini;
        const isZhipu = args.isZhipu;
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            const aria = b.getAttribute('aria-label') || '';
            const text = b.innerText.trim();
            if (isGemini && aria === '发送' && !b.disabled) { b.click(); return 'gemini_send'; }
            if (isZhipu && (text === '发送' || b.querySelector('.icon-send1'))) { b.click(); return 'zhipu_send'; }
        }
        const input = document.querySelector('[contenteditable="true"]') || document.querySelector('textarea');
        if (input) {
            input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', bubbles: true}));
            return 'enter';
        }
        return 'none';
    }""", {"isGemini": is_gemini, "isZhipu": is_zhipu})

    print(f"  Send method: {result}")
    return True

# === Send to ChatGPT ===
if 'chatgpt' in pages:
    print("\n🚀 Sending to ChatGPT...")
    type_and_send(pages['chatgpt'], CWIM_QUESTION, press_enter=True)
    print("  ✅ ChatGPT sent!")

# === Send to Gemini ===
if 'gemini' in pages:
    print("\n🚀 Sending to Gemini...")
    type_and_send(pages['gemini'], CWIM_QUESTION)
    print("  ✅ Gemini sent!")

# === Send to Zhipu ===
if 'zhipu' in pages:
    print("\n🚀 Sending to Zhipu...")
    type_and_send(pages['zhipu'], CWIM_QUESTION)
    print("  ✅ Zhipu sent!")

p.stop()
print("\n✅ Round 1 sent to all 3 AIs!")
