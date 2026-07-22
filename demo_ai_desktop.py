"""AI Desktop Automation Demo — see → think → act → loop"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))


from tools.browser_ai import send_to_ai
from tools.desktop_control import DesktopControlProvider

dc = DesktopControlProvider()

TASK = "打开记事本，计算 128 + 256 等于多少，把结果打出来"


def capture_frame():
    """Take screenshot and describe current state (text agent — no vision API)."""
    img = dc.screenshot()
    cx, cy = dc.get_cursor_position()
    w, h = dc.get_screen_size()
    img.save("demo_screenshot.png")
    return {"screen": f"{w}x{h}", "cursor": (cx, cy)}


def think(step_num, context):
    frame = capture_frame()
    prompt = (
        f"You control Windows 11 via Python. Step #{step_num}.\n"
        f"Task: {TASK}\n"
        f"Screen: {frame['screen']}, Cursor at {frame['cursor']}\n\n"
        f"Context:\n{context}\n\n"
        "Reply EXACTLY one action per step:\n"
        "---\n"
        "ACTION: press|type|click|wait|done\n"
        "PARAMS: JSON\n"
        "---\n\n"
        "Examples:\n"
        'ACTION: press | PARAMS: {"key": "r", "mods": ["win"]}\n'
        'ACTION: type | PARAMS: {"text": "notepad"}\n'
        'ACTION: press | PARAMS: {"key": "enter", "mods": []}\n'
        'ACTION: click | PARAMS: {"x": 500, "y": 400}\n'
        'ACTION: wait | PARAMS: {"sec": 1.5}\n'
        'ACTION: done | PARAMS: {"result": "128+256=384"}\n\n'
        "Your next step:"
    )
    reply = send_to_ai("chatgpt", prompt, timeout=120)
    return reply.strip()


def parse_action(reply):
    action, params_str = None, "{}"
    for line in reply.split("\n"):
        line = line.strip()
        if line.startswith("ACTION:"):
            action = line.replace("ACTION:", "").strip()
        elif line.startswith("PARAMS:"):
            params_str = line.replace("PARAMS:", "").strip()
    try:
        params = json.loads(params_str)
    except json.JSONDecodeError:
        params = {"text": params_str}
    return action, params


def execute(action, params):
    try:
        if action == "press":
            k = params.get("key", params.get("keys", ""))
            mods = params.get("mods", params.get("modifiers", []))
            dc.press_key(k, mods)
            return f"Pressed {mods}+{k}"
        elif action == "type":
            dc.type(params.get("text", ""))
            return f"Typed '{params.get('text', '')[:60]}'"
        elif action == "click":
            dc.move(int(params["x"]), int(params["y"]))
            dc.click("left")
            return f"Clicked ({params['x']}, {params['y']})"
        elif action == "wait":
            time.sleep(float(params.get("sec", 1)))
        elif action == "done":
            return f"DONE: {params.get('result', '')}"
    except Exception as e:
        return f"ERROR: {e}"


print("=" * 60)
print("  AI Desktop Automation - SEE > THINK > ACT > LOOP")
print("=" * 60)
print(f"  Task: {TASK}")
print("  Starting in 3s... (switch to desktop)")
print("=" * 60)
time.sleep(3)

context = "Desktop visible, nothing open yet."

for step in range(1, 15):
    print(f"\n--- STEP {step} ---")

    print("[THINK] Asking ChatGPT...")
    reply = think(step, context)
    print(f"AI: {reply[:250]}")

    action, params = parse_action(reply)
    if not action:
        print("? Could not parse, retrying...")
        continue

    print(f"[ACT] {action}({params})")
    result = execute(action, params)
    if result:
        print(f"[RESULT] {result}")
        if result.startswith("DONE"):
            print(f"\n{'=' * 60}")
            print(f"  TASK COMPLETE! {result}")
            print(f"{'=' * 60}")
            break
        context += f"\nStep {step}: {result}"

    time.sleep(1.5)
else:
    print("\nMax steps reached")
