"""Codex-parity tool suite — browser, deploy, documents, speech, screenshot."""

import subprocess
import sys
import time
from pathlib import Path

__all__ = [
    "ROOT",
    "browser_fetch",
    "browser_screenshot",
    "create_html",
    "create_markdown",
    "create_pdf",
    "deploy_netlify",
    "deploy_vercel",
    "desktop_screenshot",
    "text_to_speech",
]
ROOT = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════════
# Browser Automation (Playwright-based)
# ═══════════════════════════════════════════════════════════════════


def browser_screenshot(url: str, output: str = "") -> str:
    """Take a screenshot of a web page. Requires: pip install playwright && playwright install chromium"""
    from core.file_tools import _validate_url

    err = _validate_url(url)
    if err:
        return f"[安全拒绝] {err}"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "[错误] Playwright 未安装。运行: pip install playwright && playwright install chromium"
    out_path = Path(output) if output else ROOT / "output" / f"screenshot_{int(time.time())}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, timeout=30000)
        page.screenshot(path=str(out_path), full_page=True)
        browser.close()
    return str(out_path)


def browser_fetch(url: str, selector: str = "body") -> str:
    """Fetch text content from a web page element. Requires playwright."""
    from core.file_tools import _validate_url

    err = _validate_url(url)
    if err:
        return f"[安全拒绝] {err}"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "[错误] Playwright 未安装"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, timeout=30000)
        text = page.text_content(selector) or ""
        browser.close()
    return text[:10000]


# ═══════════════════════════════════════════════════════════════════
# Deploy Helpers
# ═══════════════════════════════════════════════════════════════════


def deploy_vercel(project_dir: str = ".", token: str = "") -> str:
    """Deploy to Vercel. Requires: npm install -g vercel"""
    target = (ROOT / project_dir).resolve()
    cmd = ["vercel", str(target), "--prod", "--confirm"]
    if token:
        cmd = ["vercel", str(target), "--prod", "--token", token, "--confirm"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(target))
        return r.stdout[-1000:] or r.stderr[-1000:]
    except FileNotFoundError:
        return "[错误] Vercel CLI 未安装。运行: npm install -g vercel"


def deploy_netlify(project_dir: str = ".", token: str = "") -> str:
    """Deploy to Netlify. Requires: npm install -g netlify-cli"""
    try:
        cmd = ["npx", "netlify-cli", "deploy", "--prod", f"--dir={project_dir}"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        return r.stdout[-1000:] or r.stderr[-1000:]
    except FileNotFoundError:
        return "[错误] Netlify CLI 未安装"


# ═══════════════════════════════════════════════════════════════════
# Document Generation (Office files)
# ═══════════════════════════════════════════════════════════════════


def create_markdown(title: str, content: str) -> str:
    """Create a .md file. Returns the written file path."""
    out = ROOT / "output" / f"{title.replace(' ', '_')[:50]}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    full = f"# {title}\n\n{content}"
    out.write_text(full, encoding="utf-8")
    return str(out)


def create_html(title: str, body: str) -> str:
    """Create a standalone .html file. Returns the written file path."""
    out = ROOT / "output" / f"{title.replace(' ', '_')[:50]}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>{title}</title>
<style>body{{font-family:system-ui;max-width:800px;margin:40px auto;padding:20px;line-height:1.6}}</style>
</head><body><h1>{title}</h1>{body}</body></html>"""
    out.write_text(html, encoding="utf-8")
    return str(out)


def create_pdf(content: str, output: str = "") -> str:
    """Create a PDF from text content using reportlab or weasyprint."""
    out_path = Path(output) if output else ROOT / "output" / f"doc_{int(time.time())}.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(out_path), pagesize=A4)
        y = 800
        for line in content.split(chr(10))[:200]:
            c.drawString(50, y, line[:120])
            y -= 14
            if y < 50:
                c.showPage()
                y = 800
        c.save()
        return str(out_path)
    except ImportError:
        try:
            import weasyprint  # type: ignore[import-not-found]

            html = f"<html><body><pre>{content[:50000]}</pre></body></html>"
            weasyprint.HTML(string=html).write_pdf(str(out_path))
            return str(out_path)
        except ImportError:
            return "[错误] 需要 reportlab 或 weasyprint: pip install reportlab"


# ═══════════════════════════════════════════════════════════════════
# Speech / TTS
# ═══════════════════════════════════════════════════════════════════


def text_to_speech(text: str, output: str = "", lang: str = "zh") -> str:
    """Convert text to speech using edge-tts (free, no API key needed)."""
    out_path = Path(output) if output else ROOT / "output" / f"tts_{int(time.time())}.mp3"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import asyncio

        import edge_tts

        voice = "zh-CN-XiaoxiaoNeural" if lang == "zh" else "en-US-JennyNeural"

        async def _run():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(out_path))

        asyncio.run(_run())
        return str(out_path)
    except ImportError:
        return "[错误] edge-tts 未安装: pip install edge-tts"


# ═══════════════════════════════════════════════════════════════════
# Desktop Screenshot
# ═══════════════════════════════════════════════════════════════════


def desktop_screenshot(output: str = "") -> str:
    """Take a screenshot of the entire desktop. Uses platform-specific tools."""
    out_path = Path(output) if output else ROOT / "output" / f"desktop_{int(time.time())}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    system = sys.platform
    try:
        if system == "win32":
            from PIL import ImageGrab

            img = ImageGrab.grab()
            img.save(str(out_path))
            return str(out_path)
        elif system == "darwin":
            subprocess.run(["screencapture", "-x", str(out_path)], timeout=10)
            return str(out_path)
        else:
            subprocess.run(["import", "-window", "root", str(out_path)], timeout=10)
            return str(out_path)
    except (subprocess.SubprocessError, OSError) as e:
        return f"[错误] 截图失败: {e}"
