"""
CRUX 全局 CDP 浏览器控制模块
=============================
统一入口：pw_navigate()、web_fetch_cdp()、ask_chatgpt()

核心策略（ChatGPT 联合调试验证）：
1. 动作超时压短（5s），外层重试
2. JS DOM 直写降级，绕过 Playwright 可操作性检查
3. 导航等待解耦（domcontentloaded 而非 load）
4. CDP 连接保活 + 自动重连
5. 全局单例复用，避免重复启动 Edge
"""

import atexit as _atexit
import contextlib
import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

import shutil as _shutil

EDGE_PATH = (
    _shutil.which("msedge")
    or _shutil.which("microsoft-edge")
    or r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"  # noqa: SIM222
    or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)
USER_DATA = os.environ.get("CRUX_EDGE_PROFILE", os.path.expanduser(r"~\edge_cdp_profile"))
SHORT_TIMEOUT = 5000  # ms
NAV_TIMEOUT = 15000  # ms
LONG_TIMEOUT = 45000  # ms

# ── Browser state ─────────────────────────────────────


@dataclass
class _BrowserState:
    """Global browser runtime state. Only the owning thread may access Playwright objects."""

    playwright: object | None = None  # sync_playwright() instance
    context: object | None = None  # BrowserContext
    owner_thread_id: int | None = None


_lock = threading.Lock()
_global_state = _BrowserState()


# ══════════════════════════════════════════════════════════
#  CRUX 三连 Bug 修复（v6.1）— 输入清理 / 滚动恢复 / 断连重连
# ══════════════════════════════════════════════════════════

_INPUT_LOCK = threading.Lock()
_FIX_SCROLL_INTERVAL = 0  # 自增计数器，避免重复注入


def _clear_input_buffer(page):
    """清空输入区缓冲区，防止历史消息炸出"""
    with contextlib.suppress(Exception):
        page.evaluate("""() => {
            const ta = document.querySelector('#prompt-textarea');
            if (!ta) return;
            // 清空 React 受控状态：修改 value + 触发 input 事件
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            nativeInputValueSetter.call(ta, '');
            ta.dispatchEvent(new Event('input', { bubbles: true }));
            ta.dispatchEvent(new Event('change', { bubbles: true }));
            // 清空剪贴板历史
            try { document.execCommand('delete'); } catch(e) {}
            // 清空选区
            window.getSelection()?.removeAllRanges();
        }""")


def _dismiss_notifications(page):
    """关闭 ChatGPT 页面的通知 toast（如"已就绪"提示），防止挤占输入框"""
    try:
        # 方法1: JS 暴力移除所有 toast/snackbar/notification 元素
        page.evaluate("""() => {
            const selectors = [
                '[role="alert"]', '[role="status"]',
                '[class*="snackbar"]', '[class*="toast"]', '[class*="notification"]',
                '[data-testid*="toast"]', '[data-testid*="notification"]',
                '[class*="Notice"]', '[class*="banner"]'
            ];
            selectors.forEach(sel => {
                try {
                    document.querySelectorAll(sel).forEach(el => {
                        if (el.offsetHeight > 0) el.remove();
                    });
                } catch(e) {}
            });
        }""")
        # 方法2: 点击可能的关闭按钮
        dismiss_btns = [
            '[aria-label="关闭"]',
            '[aria-label="Close"]',
            '[aria-label="Dismiss"]',
            'button[class*="close"]',
            '[class*="close-btn"]',
            '[data-testid="close-button"]',
            'button[aria-label*="close" i]',
        ]
        for sel in dismiss_btns:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=300):
                    btn.click(timeout=500)
            except Exception:
                logger.debug("Exception in cdp_browser", exc_info=True)
    except Exception:
        logger.debug("Exception in cdp_browser", exc_info=True)


def _fix_scroll(page):
    """修复滚动失效：移除遮罩层 + 恢复 wheel/keydown 事件"""
    global _FIX_SCROLL_INTERVAL
    import threading as _threading

    _lock = getattr(_fix_scroll, "_lock", None)
    if _lock is None:
        _fix_scroll._lock = _threading.Lock()  # type: ignore[attr-defined]
        _lock = _fix_scroll._lock
    with _lock:
        _FIX_SCROLL_INTERVAL += 1
        ts = _FIX_SCROLL_INTERVAL
    with contextlib.suppress(Exception):
        page.evaluate(
            """(ts) => {
            // 防重复执行
            if (window.__crux_scroll_fixed && window.__crux_scroll_fixed >= ts) return;
            // 移除可能拦截滚动的遮罩层/悬浮层
            document.querySelectorAll('[class*="overlay"], [class*="modal"], [class*="backdrop"]')
                .forEach(el => { if (el.style) el.style.pointerEvents = 'none'; });
            // 恢复 body 滚动
            document.body.style.overflow = '';
            document.documentElement.style.overflow = '';
            // 重新绑定 wheel 事件（如果被 preventDefault 了）
            const handler = (e) => { if (e.defaultPrevented) return; window.__crux_scroll_ok = true; };
            window.addEventListener('wheel', handler, { passive: true, once: true });
            window.__crux_scroll_fixed = ts;
        }""",
            ts,
        )


def _check_cdp_health(context):
    """检测持久化浏览器是否健康"""
    try:
        for p in context.pages:
            _ = p.url
            return True, ""
        return True, "no_pages"
    except Exception as e:
        return False, str(e)


def _auto_reconnect():
    """强制重建浏览器连接"""
    try:
        if _global_state.playwright:
            _global_state.playwright.stop()
    except Exception:
        logger.warning("playwright.stop() failed during reconnect, may leak browser process", exc_info=True)
    finally:
        _global_state.playwright = None
        _global_state.context = None
        _global_state.owner_thread_id = None
    _pw, ctx = _connect()
    return ctx


def _assert_browser_thread() -> None:
    """Ensure Playwright objects are only accessed from their owning thread."""
    owner = _global_state.owner_thread_id
    if owner is None:
        raise RuntimeError("Browser runtime has not been initialized")
    current = threading.get_ident()
    if current != owner:
        raise RuntimeError(
            f"Playwright objects must only be used from their owning thread. Owner={owner}, current={current}"
        )


def _connect():
    """启动 Playwright 持久化浏览器（launch_persistent_context，无 CDP）。

    Returns:
        (Playwright, BrowserContext) tuple.
    """
    pw = sync_playwright().start()
    try:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=USER_DATA,
            executable_path=EDGE_PATH,
            headless=False,
            args=["--no-first-run"],
            viewport=None,
        )
        _global_state.playwright = pw
        _global_state.context = ctx
        _global_state.owner_thread_id = threading.get_ident()
        return pw, ctx
    except Exception as e:
        try:
            pw.stop()
        except Exception:
            logger.debug("PW stop failed", exc_info=True)
        raise RuntimeError("Browser startup failed (launch_persistent_context)") from e


def is_connected() -> bool:
    """Public API: check if browser runtime is ready."""
    ctx = _global_state.context
    if ctx is None:
        return False
    try:
        pages = ctx.pages  # snapshot before TOCTOU window
        _ = pages
        return True
    except Exception:
        return False


@contextmanager
def cdp_session():
    """Global singleton browser session (context manager). Non-owning — does not close context on exit."""
    with _lock:
        if _global_state.context is None:
            _connect()
    try:
        _assert_browser_thread()
        yield _global_state.context
    finally:
        pass  # non-owning: caller decides when to close


def _get_page(context, url_hint="", goto_url=""):
    """Find existing page or create a new one. Works with BrowserContext directly."""
    for p in context.pages:
        if url_hint and url_hint in p.url:
            p.bring_to_front()
            return p
    page = context.new_page()
    if goto_url:
        page.goto(goto_url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
    return page


# ═══════════════════════════════════════════════
#  原子操作（短超时 + JS 降级）
# ═══════════════════════════════════════════════


def safe_click(page, selector, retries=3):
    """点击：Playwright → JS 降级"""
    for _i in range(retries):
        try:
            el = page.locator(selector).first
            el.click(timeout=SHORT_TIMEOUT)
            return True
        except PwTimeout:
            time.sleep(0.3)
        except Exception:
            break
    try:
        page.evaluate(f"document.querySelector('{selector}')?.click()")
        return True
    except Exception:
        return False


def safe_fill(page, selector, text, retries=3):
    """填入：contenteditable 用 keyboard.type()，普通 textarea/input 用 fill()"""
    with _INPUT_LOCK:
        _clear_input_buffer(page)
        time.sleep(0.1)

        el = page.locator(selector).first
        with contextlib.suppress(PwTimeout):
            el.wait_for(state="visible", timeout=SHORT_TIMEOUT)

        # 检测是否为 contenteditable → 用 keyboard.type()
        try:
            is_ce = el.get_attribute("contenteditable") == "true"
        except Exception:
            is_ce = False
        try:
            is_ce = is_ce or el.evaluate("el => !!el.isContentEditable")
        except Exception:
            import logging

            logging.getLogger("crux").debug("silent except", exc_info=True)

        if is_ce:
            try:
                el.click(timeout=SHORT_TIMEOUT)
                time.sleep(0.15)
                page.keyboard.type(text, delay=0)
                return True
            except Exception:
                logger.debug("safe_fill contenteditable failed, falling back to JS fallback", exc_info=True)

        # 普通 textarea/input → Playwright fill
        for _i in range(retries):
            try:
                el.click(timeout=SHORT_TIMEOUT)
                el.fill(text, timeout=SHORT_TIMEOUT)
                return True
            except PwTimeout:
                time.sleep(0.2)
            except Exception:
                break

        # JS DOM 直写降级
        try:
            page.evaluate(f"""
               (() => {{
                   const el = document.querySelector('{selector}');
                   if (!el) return false;
                   el.focus();
                   const t = {json.dumps(text)};
                   if (el.isContentEditable) {{
                       el.textContent = t;
                   }} else {{
                       el.value = t;
                   }}
                   el.dispatchEvent(new Event('input', {{bubbles: true}}));
                   el.dispatchEvent(new Event('change', {{bubbles: true}}));
                   return true;
               }})()
           """)
            return True
        except Exception:
            return False


def safe_type(page, text, delay=5):
    """键盘逐字输入"""
    page.keyboard.type(text, delay=delay)


# ═══════════════════════════════════════════════
#  导航工具（替代原 pw_navigate）
# ═══════════════════════════════════════════════


def pw_navigate(url: str) -> str:
    """
    CRUX global browser navigation.
    Persistent session, auto-reuses browser instance.
    Returns page title and URL summary.
    """
    with cdp_session() as context:
        page = _get_page(context, url_hint=url, goto_url=url)
        try:
            _fix_scroll(page)
            page.bring_to_front()
            title = page.title()
            body_preview = page.locator("body").inner_text()[:200]
            return json.dumps(
                {
                    "success": True,
                    "url": page.url,
                    "title": title,
                    "preview": body_preview,
                },
                ensure_ascii=False,
            )
        except PwTimeout:
            return json.dumps({"success": False, "error": "Navigation timeout", "url": url}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e), "url": url}, ensure_ascii=False)


def web_fetch_cdp(url: str, max_chars: int = 5000) -> str:
    """
    Fetch web content via persistent browser (supports login-required / SPA pages).
    Complementary fallback for httpx web_fetch.
    """
    with cdp_session() as context:
        page = _get_page(context, goto_url=url)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            text = page.locator("body").inner_text()
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n[Truncated: original {len(text)} chars]"
            return text
        except PwTimeout:
            return f"[Timeout] Cannot load {url}"
        except Exception as e:
            return f"[Error] {e}"


# ═══════════════════════════════════════════════
#  ChatGPT 专用
# ═══════════════════════════════════════════════


def _chatgpt_page(context):
    """Get or create ChatGPT page from BrowserContext."""
    for p in context.pages:
        if "chatgpt.com" in p.url:
            p.bring_to_front()
            return p
    page = context.new_page()
    page.goto("https://chatgpt.com/", timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
    return page


def _get_assistant_count(page) -> int:
    """获取当前 assistant 消息数量（用于判断是否有新回复）"""
    try:
        return page.locator('[data-message-author-role="assistant"]').count()
    except Exception:
        return 0


def _is_generating(page) -> bool:
    """检测 ChatGPT 是否正在生成（停止按钮可见即生成中）"""
    for sel in ('[data-testid="stop-button"]', 'button[aria-label*="Stop"]', 'button[aria-label*="停止"]'):
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                return True
        except Exception:
            continue
    return False


def _extract_last_reply(page) -> str:
    """从最后一条 assistant 消息中提取正文（优先取 .markdown，避免按钮文字污染）"""
    locator = page.locator('[data-message-author-role="assistant"]')
    count = locator.count()
    if count == 0:
        return ""
    latest = locator.nth(count - 1)
    for sel in (".markdown", '[class*="markdown"]', ".prose"):
        try:
            body = latest.locator(sel)
            if body.count() > 0:
                text = body.first.inner_text().strip()
                if text:
                    return text
        except Exception:
            continue
    try:
        return latest.inner_text().strip()
    except Exception:
        return ""


def _wait_chatgpt_done(page, max_wait=180, stable_checks=4, poll_interval=0.7):
    """
    等待 ChatGPT 回复完成：
    1. 等待停止按钮消失
    2. 文本连续 stable_checks 次不变 → 判定完成
    即使超时也返回 True（已有内容总比空好）
    """
    last_text = ""
    stable_count = 0
    for _ in range(int(max_wait / poll_interval)):
        try:
            generating = _is_generating(page)
            text = _extract_last_reply(page)
            if text:
                if text == last_text:
                    stable_count += 1
                else:
                    last_text = text
                    stable_count = 0
                if not generating and stable_count >= stable_checks:
                    return True
        except Exception:
            logger.debug("Exception in cdp_browser", exc_info=True)
        time.sleep(poll_interval)
    return True  # 超时不阻塞，已有部分内容更好


def _get_chatgpt_reply(page):
    """读取最后一条 assistant 回复（Playwright locator 版，不再用 page.evaluate）"""
    return _extract_last_reply(page)


def ask_chatgpt(question: str, wait: bool = True) -> str:
    """
    一键发送问题到 ChatGPT 并返回回复
    自动处理页面导航、填入、发送、等待、读取
    timeout 由内部短超时 + 外层轮询保证不卡死
    """
    with cdp_session() as browser:
        # [Bugfix v6.1] 连接健康检测 + 自动重连
        ok, _reason = _check_cdp_health(browser)
        if not ok:
            browser = _auto_reconnect()

        page = _chatgpt_page(browser)
        page.wait_for_selector("#prompt-textarea", state="visible", timeout=15000)

        if "chatgpt.com" not in page.url:
            page.goto("https://chatgpt.com/", timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
            page.wait_for_selector("#prompt-textarea", state="visible", timeout=15000)

        # [Bugfix v6.1] 修复滚动失效
        _fix_scroll(page)

        # [Bugfix v6.2] 关闭通知 toast，防止挤占输入框
        _dismiss_notifications(page)

        # 记录发送前的 assistant 消息数，只等新增的那条
        baseline_count = _get_assistant_count(page)

        safe_fill(page, "#prompt-textarea", question)
        time.sleep(0.5)
        safe_click(page, "button[data-testid='send-button']")

        if not wait:
            return json.dumps({"status": "sent", "question": question[:80]}, ensure_ascii=False)

        # 等新的 assistant 消息出现
        deadline = time.time() + 180
        while time.time() < deadline:
            if _get_assistant_count(page) > baseline_count:
                break
            time.sleep(0.5)

        _wait_chatgpt_done(page)
        reply = _get_chatgpt_reply(page)
        return reply


def ask_chatgpt_with_image(text: str, image_path: str, wait: bool = True) -> str:
    """
    发送文本 + 图片到 ChatGPT 并返回回复。
    通过剪贴板粘贴图片到 ChatGPT 输入区，配合文本一起提交。

    参数:
        text: 要发送的分析问题
        image_path: 图片文件路径
        wait: 是否等待回复完成
    """
    import io as _io
    import os as _os

    import win32clipboard
    from PIL import Image

    img_path = str(image_path)
    if not _os.path.exists(img_path):
        return f"[Image not found: {img_path}]"

    # ── 将图片写入剪贴板 ──
    try:
        with Image.open(img_path) as img:
            output = _io.BytesIO()
            img.convert("RGB").save(output, "BMP")
            dib_data = output.getvalue()[14:]  # 跳过 BMP 文件头

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib_data)
        finally:
            win32clipboard.CloseClipboard()
    except Exception as e:
        return f"[Clipboard error: {e}]"

    with cdp_session() as browser:
        ok, _reason = _check_cdp_health(browser)
        if not ok:
            browser = _auto_reconnect()

        page = _chatgpt_page(browser)
        page.wait_for_selector("#prompt-textarea", state="visible", timeout=15000)

        if "chatgpt.com" not in page.url:
            page.goto("https://chatgpt.com/", timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
            page.wait_for_selector("#prompt-textarea", state="visible", timeout=15000)

        _fix_scroll(page)
        # [Bugfix v6.2] 关闭通知 toast
        _dismiss_notifications(page)
        _clear_input_buffer(page)

        # 聚焦输入区并粘贴图片
        page.click("#prompt-textarea")
        time.sleep(0.5)
        page.keyboard.press("Control+v")
        # Wait for image upload to complete (upload button / preview appears)
        page.wait_for_timeout(3000)

        # 输入分析文本
        safe_type(page, text)
        time.sleep(0.5)

        # 记录发送前的 assistant 消息数
        baseline_count = _get_assistant_count(page)

        # 提交
        page.keyboard.press("Enter")

        # 等新的 assistant 消息出现
        deadline = time.time() + 180
        while time.time() < deadline:
            if _get_assistant_count(page) > baseline_count:
                break
            time.sleep(0.5)

        _wait_chatgpt_done(page)
        reply = _get_chatgpt_reply(page)
        return reply


def cdp_ask_chatgpt(
    question: str | None = None,
    text: str | None = None,
    prompt: str | None = None,
    message: str | None = None,
    query: str | None = None,
    input: str | None = None,
    properties: str | dict | None = None,
) -> str:
    """
    注册到 tools.json 的公开工具
    从 CDP 浏览器向 ChatGPT 提问并获取回复

    接受 question/text/prompt/message/query/input/properties 任一参数名，
    自动归一化为 question。
    """
    # properties 兼容：可能是 JSON 字符串 {"question":"..."} 或原始字符串
    if properties:
        if isinstance(properties, dict):
            q = properties.get("question") or properties.get("text") or properties.get("prompt") or ""
        elif isinstance(properties, str):
            try:
                d = json.loads(properties)
                if isinstance(d, dict):
                    q = d.get("question") or d.get("text") or d.get("prompt") or d.get("properties") or ""
                else:
                    q = str(d)
            except (json.JSONDecodeError, TypeError):
                q = properties
    else:
        q = ""
    q = q or question or text or prompt or message or query or input
    if not q or not q.strip():
        return "[CDP ChatGPT 错误] 缺少问题参数（question/text/prompt/message/query/input/properties）"
    try:
        return ask_chatgpt(q.strip(), wait=True)
    except Exception as e:
        return f"[CDP ChatGPT 错误] {type(e).__name__}: {e}"


def cdp_cleanup():
    """Force cleanup of global Playwright browser."""
    with _lock:
        if _global_state.context is not None:
            try:
                _global_state.context.close()
            except Exception:
                logger.debug("Exception in cdp_browser", exc_info=True)
            _global_state.context = None
        if _global_state.playwright is not None:
            try:
                _global_state.playwright.stop()
            except Exception:
                logger.debug("Exception in cdp_browser", exc_info=True)
            _global_state.playwright = None
        _global_state.owner_thread_id = None


# Register cleanup on normal interpreter exit
_atexit.register(cdp_cleanup)


def fetch_reply_already_generated() -> str:
    """
    GPT 已生成回复，直接从现有 ChatGPT 页面抓取最新 assistant 消息。
    不发送新问题，不触发新生成。
    适用于 CRUX 掉线后重连取回的场景。
    """
    with cdp_session() as browser:
        ok, _reason = _check_cdp_health(browser)
        if not ok:
            browser = _auto_reconnect()
        page = _chatgpt_page(browser)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            logger.debug("Exception in cdp_browser", exc_info=True)
        count = _get_assistant_count(page)
        if count == 0:
            return "[CDP ChatGPT] 未找到 assistant 消息，请确认 ChatGPT 页面有对话记录"
        _wait_chatgpt_done(page, max_wait=10)
        reply = _get_chatgpt_reply(page)
        if not reply:
            return "[CDP ChatGPT] 回复内容为空，可能页面未完全加载"
        return reply
