import asyncio, json, time, sys, re
from playwright.async_api import async_playwright

with open("v2_keyframe_prompts_en.txt", encoding='utf-8') as f:
    raw = f.read()

idx = raw.find("Shot 1: Ultra-wide")
en = raw[idx:]
shots = re.findall(r'Shot \d+:.*?(?=Shot \d+:|$)', en, re.DOTALL)

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
        
        for i, s in enumerate(shots[1:6], 2):  # Shot 2-6
            prompt = s.replace(f"Shot {i}:", "").strip()
            short = prompt[:80]
            print(f"\n{'='*50}\n🎨 Shot {i}/6\n{short}...\n{'='*50}", flush=True)
            
            # 发送
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
            
            # 等出图
            start = time.time()
            img_count = 0
            while time.time() - start < 60:
                await asyncio.sleep(3)
                imgs = await page.evaluate("() => document.querySelectorAll('img').length")
                txt = await page.evaluate("() => document.body.innerText")
                
                if 'cannot' in txt.lower() or "can't" in txt.lower():
                    print(f"  ⚠️ Gemini 拒绝: {txt[-200:]}", flush=True)
                    break
                
                # 检查是否出现 blob 图片
                has_new = await page.evaluate("""() => {
                    const imgs = document.querySelectorAll('img');
                    return Array.from(imgs).some(i => i.naturalWidth > 500 && i.src.startsWith('blob:'));
                }""")
                
                if has_new and imgs > img_count:
                    await asyncio.sleep(2)
                    await page.screenshot(path=f"gemini_shot{i}.png")
                    print(f"  ✅ Shot {i} 已保存!", flush=True)
                    break
                    
                img_count = max(img_count, imgs)
                e = time.time()-start
                if int(e)%15==0:
                    print(f"  ⏳ {e:.0f}s", flush=True)
        
        print("\n🎉 全部镜头生成完成!", flush=True)

asyncio.run(main())
