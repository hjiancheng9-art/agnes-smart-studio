"""Send CRUX debate prompt to Zhipu and wait for response"""
import time

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
p = sync_playwright().start()
browser = p.chromium.connect_over_cdp(CDP_URL)

prompt = """你是一位资深技术架构评审专家。请以"正反方答辩"形式，对 CRUX Studio v5.0 进行深度评审。

CRUX是AI-native创意+编程双栖平台，核心特点：图片/视频生成、ComfyUI工作流智能体(CWIM方法论10条原则)、多智能体协调、TRM工具路由网格、技能市场(51技能包)、MCP协议、CDP浏览器控制。运行于deepseek-v4-pro (1M上下文)。

关键问题：100+工具利用率低、TRM路由不准、技能市场未充分利用、长对话信息衰减、多智能体开销大。

请严格按此格式：
【正方-为CRUX辩护】
- 论点1:
- 论点2:
- 论点3:

【反方-批判CRUX】
- 论点1:
- 论点2:
- 论点3:

【正方反驳】
【反方最后陈述】
【你的最终裁决-核心问题Top3+最优先修复项+具体方案】"""

for ctx in browser.contexts:
    for pg in ctx.pages:
        if 'open.bigmodel' in pg.url:
            pg.bring_to_front()
            time.sleep(1)

            # Click "新建对话"
            try:
                new_btn = pg.query_selector('button:has-text("新建对话")')
                if new_btn:
                    new_btn.click()
                    print("✅ 智谱: 新建对话")
                    time.sleep(1.5)
            except:
                pass

            # Find textarea and fill
            ta = pg.query_selector('textarea')
            if ta:
                ta.click()
                time.sleep(0.3)
                ta.fill('')
                time.sleep(0.3)
                ta.fill(prompt)
                print(f"✅ 智谱: 已输入 ({len(prompt)} chars)")
                time.sleep(1)

                # Click submit button - find the icon-send1 or submit-btn
                submit = pg.evaluate("""() => {
                    const icon = document.querySelector('.icon-send1, .submit-btn');
                    if (icon) {
                        const r = icon.getBoundingClientRect();
                        return {found: true, x: r.x + r.width/2, y: r.y + r.height/2};
                    }
                    return {found: false};
                }""")

                if submit['found']:
                    pg.mouse.click(submit['x'], submit['y'])
                    print("✅ 智谱: 已点击发送")
                else:
                    pg.keyboard.press('Control+Enter')
                    print("✅ 智谱: Ctrl+Enter发送")

                # Wait for response
                print("⏳ 智谱: 等待回复...")
                for i in range(40):
                    time.sleep(3)
                    status = pg.evaluate("""() => {
                        const stopBtn = document.querySelector('button:has-text("停止生成")');
                        const allText = document.body.innerText;
                        return {
                            generating: !!stopBtn,
                            textLen: allText.length,
                            hasDebate: allText.includes('正方') || allText.includes('反方') || allText.includes('裁决')
                        };
                    }""")

                    if not status['generating'] and status['textLen'] > 300:
                        text = pg.evaluate("() => document.body.innerText")
                        with open('tools/edge/zhipu_full_verdict.txt', 'w', encoding='utf-8') as f:
                            f.write(text)
                        print(f"✅ 智谱: 完成! ({len(text)} chars)")
                        print(text[:3000])
                        break
                    else:
                        print(f"  ⏳ 等待... ({status['textLen']} chars, gen={status['generating']})")
                else:
                    print("⚠️ 智谱: 超时")
            break

p.stop()
