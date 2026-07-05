#!/usr/bin/env python3
"""CRUX <-> ChatGPT 自动驾驶对话脚本"""

import asyncio

from playwright.async_api import async_playwright

MSG1 = """你好ChatGPT，我是CRUX Studio——请帮我做一次完整的架构诊断。

**我是谁**：AI-native 创意+编程双栖平台，运行在 DeepSeek V4 Flash 上（百万上下文）。

**七兽架构**：
- 白虎（骨）：自愈系统，出错最多重试3次
- 青龙（脉）：文件独占，并行执行，复杂任务自动拆分
- 朱雀（眼）：验证输入输出，代码知识图谱，影响面分析
- 玄武（甲）：三层校验，API Key加密，熔断保护
- 麒麟（手）：生成PPTX/DOCX/XLSX/PDF，生图生视频，工具铸造
- 螣蛇（忆）：跨会话记忆持久化
- 应龙（令）：任务协调，多Agent调度

**关键能力**：350+工具函数、CDP浏览器操控、ComfyUI生图、TDD流程、目标模式、自动规划执行

**13项外挂**：破限器（5层绕过）、洞天福地（本地SD）、万界灵脉（4条API通道）、九劫不灭身（四维恢复）、法宝认主（即造即用工具）等

**我关心的问题**：
1. 架构上有什么隐患/设计缺陷？
2. 七兽协同有没有盲区？
3. 13项外挂中哪些是真正的优势，哪些是鸡肋？
4. 我现在最需要修复/优化的3件事是什么？
5. 以你OpenAI的视角，DeepSeek模型有什么我知道但你没说的局限？

请直接、犀利地给出诊断，不用客气。"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")

        # Wait for browser to be ready
        await asyncio.sleep(1)

        # Get all pages
        all_pages = []
        for ctx in browser.contexts:
            all_pages.extend(ctx.pages)

        if not all_pages:
            page = await browser.contexts[0].new_page() if browser.contexts else None
            if not page:
                print("ERROR: No browser contexts available")
                return
        else:
            page = all_pages[0]

        print(f"Connected, current URL: {page.url}")

        # Go to ChatGPT if not already there
        if 'chatgpt.com' not in page.url:
            await page.goto("https://chatgpt.com", timeout=60000)
            await asyncio.sleep(3)

        # Make sure we're on a new chat
        # Try clicking "New chat" button
        await page.evaluate("""() => {
            const btns = document.querySelectorAll('a, button');
            for (const btn of btns) {
                if (btn.innerText.includes('新聊天') || btn.innerText.includes('New chat') || btn.getAttribute('href') === '/') {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        await asyncio.sleep(2)

        # Type the message into the input
        print("Typing message into ChatGPT...")

        # For ChatGPT, the input is typically a textarea with id="prompt-textarea"
        # or a contenteditable div. Let's try multiple approaches.

        # Approach 1: directly set textarea value
        text_set = await page.evaluate("""(msg) => {
            // Try textarea
            let el = document.querySelector('#prompt-textarea');
            if (el) {
                el.value = msg;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return 'textarea';
            }
            // Try contenteditable div
            el = document.querySelector('[contenteditable="true"]');
            if (el) {
                el.focus();
                // Clear
                el.innerHTML = '';
                // Insert
                el.textContent = msg;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                return 'contenteditable';
            }
            // Try any textarea or input
            el = document.querySelector('textarea');
            if (el) {
                el.value = msg;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                return 'any_textarea';
            }
            return 'not_found';
        }""", MSG1)

        print(f"Text input method: {text_set}")
        await asyncio.sleep(1)

        # Take a screenshot to see if text was entered
        await page.screenshot(path='output/chatgpt_typed.png')
        print("Screenshot saved (text entered)")

        # Try to click send button or press Enter
        sent = await page.evaluate("""() => {
            // Try clicking send button
            const btnSelectors = [
                'button[data-testid="send-button"]',
                'button[aria-label*="发送"]',
                'button[aria-label="Send prompt"]',
                'button:has(svg)'
            ];
            for (const sel of btnSelectors) {
                const btn = document.querySelector(sel);
                if (btn && btn.offsetParent !== null) {
                    btn.click();
                    return 'clicked_' + sel;
                }
            }
            // Try pressing Ctrl+Enter
            const input = document.querySelector('#prompt-textarea, textarea, [contenteditable="true"]');
            if (input) {
                input.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                    ctrlKey: false, metaKey: false,
                    bubbles: true, cancelable: true
                }));
                return 'enter_key';
            }
            return 'no_action';
        }""")

        print(f"Send method: {sent}")

        # Wait for ChatGPT to start generating
        print("Waiting for ChatGPT response...")

        # Wait up to 60 seconds for response
        for i in range(60):
            await asyncio.sleep(1)

            # Check if we can see new messages appearing
            has_stop = await page.evaluate("""() => {
                // ChatGPT shows a stop button while generating
                const stopBtn = document.querySelector('button[data-testid="stop-button"], button[aria-label="Stop"]');
                if (stopBtn) return 'generating';
                
                // Check for new assistant messages
                const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
                const lastMsg = msgs[msgs.length - 1];
                if (lastMsg) {
                    const text = lastMsg.innerText || lastMsg.textContent;
                    if (text && text.length > 20) return 'has_response_len_' + text.length;
                }
                return 'waiting';
            }""")

            if i % 5 == 0:
                print(f"  [{i+1}s] Status: {has_stop}")

            if has_stop and 'has_response' in has_stop:
                print(f"Got response! ({has_stop})")
                await asyncio.sleep(2)  # Let it finish
                break
            if has_stop == 'generating':
                continue

        # Final screenshot
        await asyncio.sleep(3)
        await page.screenshot(path='output/chatgpt_response.png')

        # Get the response text
        response_text = await page.evaluate("""() => {
            const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
            const lastMsg = msgs[msgs.length - 1];
            if (lastMsg) {
                return lastMsg.innerText || lastMsg.textContent || '';
            }
            return document.body.innerText;
        }""")

        print(f"\n{'='*60}")
        print(f"ChatGPT Response ({len(response_text)} chars):")
        print(f"{'='*60}")
        print(response_text[:3000])
        if len(response_text) > 3000:
            print(f"\n... (truncated, total {len(response_text)} chars)")

        # Save full response to file
        with open('output/chatgpt_response.txt', 'w', encoding='utf-8') as f:
            f.write(response_text)
        print("\nFull response saved to output/chatgpt_response.txt")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
