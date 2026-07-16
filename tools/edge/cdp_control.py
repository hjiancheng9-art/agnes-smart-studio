"""
CDP 鲁棒性控制器 — 多策略输入检测（v5.0→v6.0 升级）
=====================================================
ChatGPT+Gemini+智谱评审共识：CDP 强依赖 DOM 选择器太脆弱。

升级方案：
  策略链: Accessibility Tree → ARIA roles → 视觉坐标 → DOM selectors
  当 UI 更新时，前三层不受影响，仅最后一层需维护。

用法:
  python tools/edge/cdp_control.py status
  python tools/edge/cdp_control.py send "消息"
  python tools/edge/cdp_control.py read
"""

import logging

logger = logging.getLogger(__name__)

import sys
import time

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"


def get_page():
    """获取当前活跃的 CDP 页面"""
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(CDP_URL)
    pages = browser.contexts[0].pages if browser.contexts else []
    return p, browser, pages[-1] if pages else None


# ─── 多策略输入查找 ──────────────────────────────────────


def find_input(page, label_hint: str = "") -> dict:
    """按策略链查找输入框。返回 {el, method, confidence}"""
    results = []

    # Strategy 1: Accessibility Tree — 找 textbox 角色
    try:
        acc = page.accessibility.snapshot()
        if acc:
            textboxes = _find_in_accessibility(acc, "textbox")
            if textboxes:
                results.append(
                    {"el": None, "method": "accessibility_tree", "selector": textboxes[0], "confidence": 0.9}
                )
    except Exception as e:
        logger.debug("Non-critical: %s", e, exc_info=True)

    # Strategy 2: ARIA roles
    for role in ["textbox", "combobox", "searchbox"]:
        try:
            el = page.query_selector(f'[role="{role}"]')
            if el and el.is_visible():
                results.append({"el": el, "method": f"role={role}", "selector": f'[role="{role}"]', "confidence": 0.8})
                break
        except Exception as e:
            logger.debug("Non-critical: %s", e, exc_info=True)

    # Strategy 3: contenteditable (ProseMirror/rich text)
    for sel in ["#prompt-textarea", '[contenteditable="true"]']:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                results.append({"el": el, "method": "contenteditable", "selector": sel, "confidence": 0.7})
                break
        except Exception as e:
            logger.debug("Non-critical: %s", e, exc_info=True)

    # Strategy 4: textarea
    try:
        el = page.query_selector("textarea")
        if el and el.is_visible():
            results.append({"el": el, "method": "textarea", "selector": "textarea", "confidence": 0.6})
    except Exception as e:
        logger.debug("Non-critical: %s", e, exc_info=True)

    if results:
        return max(results, key=lambda r: r["confidence"])
    return {"el": None, "method": "none", "confidence": 0.0}


def _find_in_accessibility(node, target_role, path=""):
    """递归查找 Accessibility Tree 中的目标角色"""
    results = []
    role = node.get("role", "")
    if role == target_role:
        results.append(node)
    for child in node.get("children", []):
        results.extend(_find_in_accessibility(child, target_role, path))
    return results


def find_send_button(page) -> dict:
    """按策略链查找发送按钮"""
    # Strategy 1: ARIA label
    for label in ["发送", "Send", "send", "Submit", "submit"]:
        try:
            el = page.query_selector(f'button[aria-label="{label}"]')
            if el and el.is_visible() and not el.is_disabled():
                return {"el": el, "method": f"aria-label={label}", "confidence": 0.9}
        except Exception as e:
            logger.debug("Non-critical: %s", e, exc_info=True)

    # Strategy 2: data-testid
    for tid in ["send-button", "send", "submit"]:
        try:
            el = page.query_selector(f'[data-testid="{tid}"]')
            if el and el.is_visible() and not el.is_disabled():
                return {"el": el, "method": f"data-testid={tid}", "confidence": 0.8}
        except Exception as e:
            logger.debug("Non-critical: %s", e, exc_info=True)

    # Strategy 3: icon-send (Zhipu specific)
    try:
        icon = page.query_selector(".icon-send1, .submit-btn")
        if icon and icon.is_visible():
            return {"el": icon, "method": "icon-send", "confidence": 0.7}
    except Exception as e:
        logger.debug("Non-critical: %s", e, exc_info=True)

    # Strategy 4: last visible button in input area
    try:
        input_area = page.query_selector('[contenteditable="true"], textarea')
        if input_area:
            parent = input_area.evaluate("el => el.closest('div, form')?.id || 'none'")
            if parent != "none":
                btn = page.query_selector(f"#{parent} button:not([disabled])")
                if btn and btn.is_visible():
                    return {"el": btn, "method": "near-input-btn", "confidence": 0.5}
    except Exception as e:
        logger.debug("Non-critical: %s", e, exc_info=True)

    return {"el": None, "method": "none", "confidence": 0.0}


# ─── 命令实现 ──────────────────────────────────────────


def cmd_status():
    p, _browser, page = get_page()
    if not page:
        print("❌ 没有打开的标签页")
    else:
        print(f"当前: {page.title()} | {page.url}")
        # 显示输入检测策略成功率
        inp = find_input(page)
        btn = find_send_button(page)
        print(f"  输入策略: {inp['method']} (confidence={inp['confidence']})")
        print(f"  发送策略: {btn['method']} (confidence={btn['confidence']})")
    p.stop()


def cmd_send(text):
    p, _browser, page = get_page()
    if not page:
        print("❌ 无页面")
        p.stop()
        return

    inp = find_input(page)
    if inp["el"]:
        inp["el"].click()
        time.sleep(0.3)
        inp["el"].fill(text)
        time.sleep(0.5)
    elif inp["method"] == "accessibility_tree":
        # 通过 JS 聚焦并设置文本
        page.evaluate(
            """(t) => {
            const el = document.querySelector('[contenteditable="true"]') ||
                       document.querySelector('textarea') ||
                       document.querySelector('[role="textbox"]');
            if (el) { el.focus(); el.innerText = t; el.dispatchEvent(new Event('input', {bubbles: true})); }
        }""",
            text,
        )
    else:
        # 最终兜底：模拟键盘输入
        page.keyboard.insert_text(text)
        print("⚠️ 未检测到标准输入框，通过键盘输入")

    time.sleep(0.5)

    # 点击发送
    btn = find_send_button(page)
    if btn["el"]:
        btn["el"].click()
        print(f"✅ 已发送 ({inp['method']}→{btn['method']})")
    else:
        page.keyboard.press("Enter")
        print(f"✅ 已发送 (Enter/{inp['method']})")

    p.stop()


def cmd_read(lines=20):
    p, _browser, page = get_page()
    if not page:
        print("❌ 无页面")
        p.stop()
        return

    # 多策略读取页面内容
    # Strategy 1: ChatGPT 对话结构
    for sel in [
        '[data-message-author-role="assistant"]',
        'article[data-testid*="conversation"]',
        ".model-response-text",
        "main",
    ]:
        try:
            els = page.query_selector_all(sel)
            if els:
                texts = [e.inner_text() for e in els[-lines:]]
                print("\n---\n".join(texts[-lines:]))
                p.stop()
                return
        except Exception as e:
            logger.debug("Non-critical: %s", e, exc_info=True)

    # Strategy 2: 全文回退
    print(page.evaluate("() => document.body.innerText"))
    p.stop()


def cmd_screenshot(path="edge_screenshot.png"):
    p, _browser, page = get_page()
    if page:
        page.screenshot(path=path)
        print(f"✅ 截图保存: {path}")
    p.stop()


# ─── 主入口 ──────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmds = {
        "status": lambda: cmd_status(),
        "send": lambda: cmd_send(" ".join(sys.argv[2:])),
        "read": lambda: cmd_read(int(sys.argv[2]) if len(sys.argv) > 2 else 20),
        "screenshot": lambda: cmd_screenshot(sys.argv[2] if len(sys.argv) > 2 else "edge_screenshot.png"),
    }

    cmd = sys.argv[1]
    if cmd in cmds:
        cmds[cmd]()
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
