import os

OUTPUT_DIR = r"C:\Users\huangjiancheng\agnes-smart-studio\output"

# Specific prompt markers for each round
ROUND_PROMPTS = {
    "r3_input": "继续辩论 CRUX TUI v2 的输入体验",
    "r4_performance": "继续辩论 CRUX TUI v2 的性能问题",
    "r5_accessibility": "辩论 CRUX TUI v2 的可访问性",
    "r6_markdown": "辩论 CRUX TUI v2 的消息渲染策略",
    "r7_animation": "辩论 CRUX TUI v2 的动画策略",
    "r8_remote": "辩论 CRUX TUI v2 的远程",
    "r9_overall": "整体评价 CRUX TUI v2",
}

PLATFORMS = [("chatgpt", "ChatGPT"), ("gemini", "Gemini"), ("zhipu", "Zhipu")]

for round_key, prompt_marker in ROUND_PROMPTS.items():
    for p, pl in PLATFORMS:
        path = os.path.join(OUTPUT_DIR, f"tui_debate_{round_key}_{p}.txt")
        if not os.path.exists(path):
            continue

        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Find this round's prompt
        idx = content.find(prompt_marker)
        if idx < 0:
            # Try shorter version
            short = prompt_marker[:15]
            idx = content.find(short)

        if idx >= 0:
            resp = content[idx:]

            # Find where actual AI response starts (skip the echoed prompt)
            # The echoed prompt is around 500-1500 chars
            # Look for analysis content
            ai_indicators = ["正方", "反方", "我推荐", "我建议", "我认为"]
            best = 999999
            for m in ai_indicators:
                pos = resp.find(m, 600)
                if 0 < pos < best:
                    best = pos

            if best < len(resp):
                ai_text = resp[best:]
            else:
                ai_text = resp[1000:]

            # Count meaningful Chinese content
            lines = [l.strip() for l in ai_text.split('\n') if l.strip()]
            chinese_lines = [l for l in lines if sum(1 for c in l if '\u4e00' <= c <= '\u9fff') >= 5]

            print("{}/{}: {} total chars, {} CJK lines, first line: {}".format(
                round_key, pl, len(ai_text), len(chinese_lines),
                chinese_lines[0][:80] if chinese_lines else "(empty)"))

            # Save
            with open(f"_clean_{round_key}_{p}.txt", "w", encoding="utf-8") as f:
                f.write('\n'.join(chinese_lines))
        else:
            print(f"{round_key}/{pl}: prompt marker not found")
