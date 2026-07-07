"""Persistent Playwright browser - keeps Edge browser alive for CRUX to control."""
import asyncio
import json
import os
import time

from playwright.async_api import async_playwright

CMD_FILE = r"C:\Users\huangjiancheng\agnes-smart-studio\output\browser_cmd.txt"
RESP_FILE = r"C:\Users\huangjiancheng\agnes-smart-studio\output\browser_resp.txt"
ALIVE_FILE = r"C:\Users\huangjiancheng\agnes-smart-studio\output\browser_alive.txt"

async def keep_alive():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='msedge', headless=False)
        page = await browser.new_page()
        await page.goto('https://chatgpt.com', wait_until='domcontentloaded', timeout=30000)

        # Signal ready
        with open(ALIVE_FILE, 'w') as f:
            f.write(f"ready:{time.time()}")

        # Poll for commands
        last_cmd = ""
        while True:
            try:
                if os.path.exists(CMD_FILE):
                    with open(CMD_FILE, 'r', encoding='utf-8') as f:
                        cmd_text = f.read().strip()

                    if cmd_text and cmd_text != last_cmd:
                        last_cmd = cmd_text
                        cmd = json.loads(cmd_text)
                        action = cmd.get('action')

                        if action == 'screenshot':
                            path = cmd.get('path', r'C:\Users\huangjiancheng\agnes-smart-studio\output\browser_shot.png')
                            await page.screenshot(path=path)
                            with open(RESP_FILE, 'w', encoding='utf-8') as f:
                                f.write(json.dumps({"status": "ok", "path": path}))

                        elif action == 'title':
                            t = await page.title()
                            with open(RESP_FILE, 'w', encoding='utf-8') as f:
                                f.write(json.dumps({"status": "ok", "title": t}))

                        elif action == 'goto':
                            await page.goto(cmd['url'], wait_until='domcontentloaded', timeout=30000)
                            with open(RESP_FILE, 'w', encoding='utf-8') as f:
                                f.write(json.dumps({"status": "ok"}))

                        elif action == 'paste':
                            # Clear and paste text
                            await page.keyboard.press('Control+a')
                            await asyncio.sleep(0.1)
                            await page.keyboard.press('Delete')
                            await asyncio.sleep(0.1)
                            await page.keyboard.type(cmd['text'], delay=3)
                            with open(RESP_FILE, 'w', encoding='utf-8') as f:
                                f.write(json.dumps({"status": "ok"}))

                        elif action == 'enter':
                            await page.keyboard.press('Enter')
                            with open(RESP_FILE, 'w', encoding='utf-8') as f:
                                f.write(json.dumps({"status": "ok"}))

                        elif action == 'read':
                            # Select all and read text content
                            try:
                                text = await page.evaluate("""
                                    () => {
                                        const sel = window.getSelection();
                                        const range = document.createRange();
                                        const all = document.querySelectorAll('body');
                                        if (all[0]) {
                                            range.selectNodeContents(all[0]);
                                            sel.removeAllRanges();
                                            sel.addRange(range);
                                        }
                                        return sel.toString();
                                    }
                                """)
                            except:
                                text = "select_error"
                            with open(RESP_FILE, 'w', encoding='utf-8') as f:
                                f.write(json.dumps({"status": "ok", "text": text}))

                        elif action == 'stop':
                            await browser.close()
                            with open(RESP_FILE, 'w', encoding='utf-8') as f:
                                f.write(json.dumps({"status": "stopped"}))
                            return

                        elif action == 'ping':
                            with open(RESP_FILE, 'w', encoding='utf-8') as f:
                                f.write(json.dumps({"status": "pong"}))

                        # Clear command after processing
                        with open(CMD_FILE, 'w', encoding='utf-8') as f:
                            f.write("")
            except json.JSONDecodeError:
                pass
            except Exception as e:
                try:
                    with open(RESP_FILE, 'w', encoding='utf-8') as f:
                        f.write(json.dumps({"status": "error", "msg": str(e)}))
                except:
                    pass

            await asyncio.sleep(0.5)

if __name__ == '__main__':
    asyncio.run(keep_alive())
