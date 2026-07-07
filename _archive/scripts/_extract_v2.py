import os

OUTPUT_DIR = r"C:\Users\huangjiancheng\agnes-smart-studio\output"

# Known prompt signatures for each round (unique identifying phrases)
PROMPT_SIGS = {
    "r3_input": [
        "继续辩论 CRUX TUI v2 的输入体验",
        "【单行 vs 多行】默认单行自动扩展",
    ],
    "r4_performance": [
        "继续辩论 CRUX TUI v2 的性能问题",
        "【虚拟滚动】是否必须",
    ],
    "r5_accessibility": [
        "辩论 CRUX TUI v2 的可访问性",
        "【色盲兼容】七兽色中#f2cdcd",
    ],
    "r6_markdown": [
        "辩论 CRUX TUI v2 的消息渲染策略",
        "【Markdown子集】AI编程助手最常用的",
    ],
    "r7_animation": [
        "辩论 CRUX TUI v2 的动画策略",
        "【Spinner】braille动画保留还是去掉",
    ],
    "r8_remote": [
        "辩论 CRUX TUI v2 的远程/SSH兼容性",
        "【SSH场景】SSH下应该关闭哪些功能",
    ],
    "r9_overall": [
        "整体评价 CRUX TUI v2",
        "【竞品对比】与Cursor、Copilot CLI",
    ],
}

PLATFORMS = [("chatgpt","ChatGPT"),("gemini","Gemini"),("zhipu","Zhipu")]

for round_key, sigs in PROMPT_SIGS.items():
    for p, pl in PLATFORMS:
        path = os.path.join(OUTPUT_DIR, f"tui_debate_{round_key}_{p}.txt")
        if not os.path.exists(path):
            continue

        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Find the prompt by its unique signature
        prompt_start = -1
        for sig in sigs:
            idx = content.find(sig)
            if idx >= 0:
                # Find the beginning of this paragraph
                # Search backwards for double newline
                para_start = content.rfind('\n\n', 0, idx)
                if para_start < 0:
                    para_start = max(0, idx - 100)
                prompt_start = para_start
                break

        if prompt_start < 0:
            print(f"❌ {round_key}/{pl}: prompt not found")
            continue

        # Find where the prompt ends (next double newline after the prompt)
        # The prompt is about 1000-1500 chars. Find the end by looking for
        # the next user/AI boundary after the prompt
        prompt_content = content[prompt_start:]

        # Find where AI response starts - look after the prompt echo
        # The response typically has opinionated language
        response_start = -1
        for marker in ["正方：", "反方：", "我推荐", "我建议", "我认为",
                       "先回答", "下面回答", "好问题", "我的观点"]:
            idx = prompt_content.find(marker, 800)  # Skip echoed prompt
            if 0 < idx < 5000:
                response_start = prompt_start + idx
                break

        if response_start < 0:
            # Fallback: skip ahead 1500 chars from prompt start
            response_start = prompt_start + 1500

        ai_response = content[response_start:]

        # Count Chinese chars in response
        cc = sum(1 for c in ai_response if '\u4e00' <= c <= '\u9fff')

        # Save
        with open(f"_clean_R{round_key[1]}_{p}.txt", "w", encoding="utf-8") as f:
            f.write(ai_response)

        print(f"✅ {round_key}/{pl}: {len(ai_response)} chars, {cc} CJK")
        print(f"   Starts: {ai_response[:150]}...")
