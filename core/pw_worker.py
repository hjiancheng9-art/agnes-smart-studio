"""
Playwright standalone worker — solves sync_playwright + asyncio conflicts.
Usage: python core/pw_worker.py <action> <arg1=val1> <arg2=val2> ...
Each invocation is a fresh process — no persistence, no threading issues.
Prints JSON result to stdout.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
OUTPUT.mkdir(parents=True, exist_ok=True)


def parse_args():
    """Parse command-line: action key=val key=val ..."""
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: pw_worker.py <action> [key=val ...]"}))
        sys.exit(1)

    action = sys.argv[1]
    kwargs = {}
    for arg in sys.argv[2:]:
        if "=" in arg:
            k, v = arg.split("=", 1)
            kwargs[k] = v
    return action, kwargs


def main():
    action, kwargs = parse_args()

    from playwright.sync_api import sync_playwright

    result = {"action": action}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            if action == "navigate":
                url = kwargs.get("url", "about:blank")
                page.goto(url, timeout=30000)
                result["ok"] = True
                result["url"] = page.url
                result["title"] = page.title()

            elif action == "screenshot":
                path = kwargs.get("path", str(OUTPUT / f"browser_{time.time():.0f}.png"))
                # Navigate first if url given
                if "url" in kwargs:
                    page.goto(kwargs["url"], timeout=30000)
                page.screenshot(path=path, full_page=True)
                result["ok"] = True
                result["path"] = str(path)

            elif action == "click":
                sel = kwargs.get("selector", "")
                page.click(sel, timeout=10000)
                result["ok"] = True

            elif action == "fill":
                sel = kwargs.get("selector", "")
                text = kwargs.get("text", "")
                page.fill(sel, text, timeout=10000)
                result["ok"] = True

            elif action == "js":
                code = kwargs.get("code", "")
                ret = page.evaluate(code)
                result["ok"] = True
                result["value"] = json.dumps(ret, ensure_ascii=False)

            else:
                result["error"] = f"Unknown action: {action}"

            browser.close()

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
