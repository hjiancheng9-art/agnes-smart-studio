"""
发送 CRUX 辩论提示到 Gemini 和 智谱，并读取回复
"""

import logging

logger = logging.getLogger(__name__)

import time

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"

DEBATE_PROMPT = """你是一位资深技术架构评审专家。请以"正反方答辩"形式，对 CRUX Studio v5.0 进行深度评审。

CRUX是AI-native创意+编程双栖平台，核心特点：图片/视频生成、ComfyUI工作流智能体(CWIM方法论10条原则)、多智能体协调、TRM工具路由网格、技能市场(51技能包)、MCP协议、CDP浏览器控制。运行于deepseek-v4-pro (1M上下文)。

关键问题：100+工具利用率低、TRM路由不准、技能市场未充分利用、长对话信息衰减、多智能体开销大。

请严格按此格式输出：
【正方-为CRUX辩护】
- 论点1:
- 论点2:

【反方-批判CRUX】
- 论点1:
- 论点2:

【正方反驳】
【反方最后陈述】
【你的最终裁决-核心问题Top3+最优先修复项+具体方案】"""


def send_to_gemini(p, browser):
    """Send prompt to Gemini and wait for response"""
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if "gemini" in pg.url:
                pg.bring_to_front()
                time.sleep(1)

                # Click new conversation if exists
                try:
                    new_btn = pg.query_selector('button[aria-label="发起新对话"]')
                    if new_btn:
                        new_btn.click()
                        time.sleep(1)
                except Exception as e:
                    logger.debug("Non-critical: %s", e, exc_info=True)

                # Find and fill the input
                input_el = pg.query_selector('[contenteditable="true"]')
                if not input_el:
                    print("❌ Gemini: 找不到输入框")
                    return None

                input_el.click()
                time.sleep(0.3)
                input_el.fill("")
                time.sleep(0.3)

                # Type the prompt
                pg.keyboard.insert_text(DEBATE_PROMPT)
                print(f"✅ Gemini: 已输入提示 ({len(DEBATE_PROMPT)} chars)")
                time.sleep(2)

                # Check for send button now that text is entered
                send_btn = pg.query_selector('button[aria-label="发送"]')
                if send_btn and not send_btn.is_disabled():
                    send_btn.click()
                    print("✅ Gemini: 已点击发送按钮")
                else:
                    # Try pressing Enter
                    pg.keyboard.press("Enter")
                    print("✅ Gemini: 已按 Enter")

                # Wait for response
                print("⏳ Gemini: 等待回复...")
                for _i in range(30):
                    time.sleep(3)
                    result = pg.evaluate("""() => {
                        const stopBtn = document.querySelector('[aria-label="停止"]');
                        const allText = document.body.innerText;
                        // Check if we got a response (more than just the prompt)
                        if (allText.includes('正方') || allText.includes('反方') || allText.includes('裁决') || allText.includes('CRUX')) {
                            // Check if still generating
                            if (!stopBtn && allText.length > 200) {
                                return {done: true, text: allText};
                            }
                        }
                        return {done: false, textLen: allText.length, hasStop: !!stopBtn};
                    }""")

                    if result.get("done"):
                        print(f"✅ Gemini: 回复完成! ({len(result['text'])} chars)")
                        return result["text"]
                    else:
                        print(f"  ⏳ 等待... ({result.get('textLen', 0)} chars, stop={result.get('hasStop')})")

                print("⚠️ Gemini: 超时")
                return pg.evaluate("() => document.body.innerText")


def send_to_zhipu(p, browser):
    """Send prompt to 智谱清言 and wait for response"""
    for ctx in browser.contexts:
        for pg in ctx.pages:
            if "open.bigmodel" in pg.url:
                pg.bring_to_front()
                time.sleep(1)

                # Find and fill textarea
                ta = pg.query_selector("textarea")
                if not ta:
                    print("❌ 智谱: 找不到输入框")
                    return None

                # Click "新建对话" to start fresh
                try:
                    new_btn = pg.query_selector('button:has-text("新建对话")')
                    if new_btn:
                        new_btn.click()
                        print("✅ 智谱: 已新建对话")
                        time.sleep(1.5)
                except Exception as e:
                    logger.debug("Non-critical: %s", e, exc_info=True)

                # Re-find textarea after new conversation
                ta = pg.query_selector("textarea")
                if ta:
                    ta.click()
                    time.sleep(0.3)
                    ta.fill("")
                    time.sleep(0.3)
                    ta.fill(DEBATE_PROMPT)
                    print(f"✅ 智谱: 已输入提示 ({len(DEBATE_PROMPT)} chars)")
                    time.sleep(1)

                    # Click the submit button
                    submit_btn = pg.evaluate("""() => {
                        // Find the submit div
                        const submitDiv = document.querySelector('.submit-btn');
                        if (submitDiv && submitDiv.offsetParent !== null) {
                            const r = submitDiv.getBoundingClientRect();
                            return {found: true, x: r.x + r.width/2, y: r.y + r.height/2};
                        }
                        // Try icon
                        const icon = document.querySelector('.icon-send1');
                        if (icon) {
                            const r = icon.getBoundingClientRect();
                            return {found: true, x: r.x + r.width/2, y: r.y + r.height/2};
                        }
                        return {found: false};
                    }""")

                    if submit_btn["found"]:
                        pg.mouse.click(submit_btn["x"], submit_btn["y"])
                        print("✅ 智谱: 已点击发送按钮")
                    else:
                        # Try Ctrl+Enter
                        pg.keyboard.press("Control+Enter")
                        print("✅ 智谱: 已按 Ctrl+Enter")

                    # Wait for response
                    print("⏳ 智谱: 等待回复...")
                    for _i in range(30):
                        time.sleep(3)
                        result = pg.evaluate("""() => {
                            const stopBtn = document.querySelector('button:has-text("停止生成")');
                            const allText = document.body.innerText;
                            if (!stopBtn && (allText.includes('正方') || allText.includes('反方') || allText.includes('裁决') || allText.includes('CRUX'))) {
                                if (allText.length > 400) {
                                    return {done: true, text: allText};
                                }
                            }
                            return {done: false, textLen: allText.length, hasStop: !!stopBtn};
                        }""")

                        if result.get("done"):
                            print(f"✅ 智谱: 回复完成! ({len(result['text'])} chars)")
                            return result["text"]
                        else:
                            print(f"  ⏳ 等待... ({result.get('textLen', 0)} chars, stop={result.get('hasStop')})")

                    print("⚠️ 智谱: 超时")
                    return pg.evaluate("() => document.body.innerText")


# Main
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

# Save debate prompt for reference
with open("tools/edge/debate_prompt.txt", "w", encoding="utf-8") as f:
    f.write(DEBATE_PROMPT)

# Send to Gemini
print("\n" + "=" * 50)
print("🚀 发送到 Gemini...")
print("=" * 50)
gemini_result = send_to_gemini(p, browser)
if gemini_result:
    with open("tools/edge/gemini_verdict.txt", "w", encoding="utf-8") as f:
        f.write(gemini_result)
    print(f"\n📝 Gemini 回复已保存 ({len(gemini_result)} chars)")

# Send to Zhipu
print("\n" + "=" * 50)
print("🚀 发送到 智谱清言...")
print("=" * 50)
# Need to reconnect browser after page switching
browser2 = p.chromium.connect_over_cdp(CDP_URL)
zhipu_result = send_to_zhipu(p, browser2)
if zhipu_result:
    with open("tools/edge/zhipu_verdict.txt", "w", encoding="utf-8") as f:
        f.write(zhipu_result)
    print(f"\n📝 智谱回复已保存 ({len(zhipu_result)} chars)")

p.stop()
print("\n✅ 全部完成!")
