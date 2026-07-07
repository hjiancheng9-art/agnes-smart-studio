import asyncio
import re
import time

from playwright.async_api import async_playwright

with open("v2_keyframe_prompts_en.txt", encoding='utf-8') as f:
    raw = f.read()

idx = raw.find("Shot 1: Ultra-wide")
en = raw[idx:]
shots = re.findall(r'(Shot \d+: [A-Z][^。]*?(?:fantasy animation[^.]*\.))', en, re.DOTALL)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = None
        for pg in browser.contexts[0].pages:
            if "gemini" in pg.url.lower():
                page = pg
                break
        if not page:
            print("no gemini")
            return

        for i, s in enumerate(shots[6:12], 7):  # Shot 7-12
            prompt = s.strip()
            # 去掉 "Shot X:" 前缀
            if f"Shot {i}:" in prompt:
                prompt = prompt.split(f"Shot {i}:", 1)[1].strip()

            print(f"\n{'='*50}\n🎨 Shot {i}/12\n{prompt[:80]}...\n{'='*50}", flush=True)

            input_box = page.locator('[contenteditable="true"], textarea').first
            await input_box.click()
            await input_box.fill("")
            await asyncio.sleep(0.3)

            img_cmd = f"Generate imagen: {prompt[:450]}"
            await input_box.fill(img_cmd)
            await asyncio.sleep(0.3)

            send_btn = page.locator('[aria-label*="Send"], button:has(svg)').first
            if await send_btn.is_visible():
                await send_btn.click()
            else:
                await page.keyboard.press("Enter")
            print("  ✉️ 已发送", flush=True)

            start = time.time()
            while time.time() - start < 60:
                await asyncio.sleep(3)
                has_new = await page.evaluate("""() => {
                    const imgs = document.querySelectorAll('img');
                    return Array.from(imgs).some(i => i.naturalWidth > 500 && i.src.startsWith('blob:'));
                }""")

                if has_new:
                    await asyncio.sleep(2)
                    await page.screenshot(path=f"gemini_shot{i}.png")
                    print(f"  ✅ Shot {i} 已保存!", flush=True)
                    break

                e = time.time()-start
                if int(e)%15==0:
                    print(f"  ⏳ {e:.0f}s", flush=True)

        print("\n🎉 Shot 7-12 全部完成!", flush=True)

asyncio.run(main())
