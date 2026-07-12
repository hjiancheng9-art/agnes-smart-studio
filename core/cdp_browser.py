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
import contextlib
import json
import logging
import os
import socket
import subprocess
import threading
import time
from contextlib import contextmanager

from playwright.sync_api import TimeoutError as PwTimeout
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

CDP_URL = "http://127.0.0.1:9222"
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
# Edge CDP 用户数据目录，从环境变量读取，默认 ~/edge_cdp_profile
USER_DATA = os.environ.get(
    "CRUX_EDGE_PROFILE",
    os.path.expanduser(r"~\edge_cdp_profile")
)
SHORT_TIMEOUT = 5000   # ms — 单次动作超时
NAV_TIMEOUT = 15000    # ms — 页面导航超时
LONG_TIMEOUT = 45000   # ms — ChatGPT 生成等待

# 全局单例
_lock = threading.Lock()
_global_state = {"pw": None, "browser": None, "refcount": 0}



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
            '[aria-label="关闭"]', '[aria-label="Close"]', '[aria-label="Dismiss"]',
            'button[class*="close"]', '[class*="close-btn"]',
            '[data-testid="close-button"]', 'button[aria-label*="close" i]'
        ]
        for sel in dismiss_btns:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=300):
                    btn.click(timeout=500)
            except Exception:
                pass
    except Exception:
        pass


def _fix_scroll(page):
    """修复滚动失效：移除遮罩层 + 恢复 wheel/keydown 事件"""
    global _FIX_SCROLL_INTERVAL
    _FIX_SCROLL_INTERVAL += 1
    with contextlib.suppress(Exception):
        page.evaluate("""(ts) => {
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
        }""", _FIX_SCROLL_INTERVAL)

def _check_cdp_health(browser):
    """检测 CDP 连接是否健康，返回 (ok, reason)"""
    try:
        for ctx in browser.contexts:
            for p in ctx.pages:
                _ = p.url
                return True, ""
        # 没页面也算健康（只是没开页面）
        return True, "no_pages"
    except Exception as e:
        return False, str(e)

def _auto_reconnect():
    """强制重建 CDP 连接"""
    global _global_state
    try:
        if _global_state["pw"]:
            _global_state["pw"].stop()
    except Exception:
        pass
    _global_state["pw"] = None
    _global_state["browser"] = None
    _global_state["refcount"] = 0
    # 重新连接
    pw, browser = _connect()
    _global_state["pw"] = pw
    _global_state["browser"] = browser
    _global_state["refcount"] = 1
    return browser

def _edge_running() -> bool:
    """检测用户是否已有 Edge 在运行（不含 CDP 端口）。"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq msedge.exe", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        return "msedge.exe" in result.stdout
    except Exception:
        return False  # 无法检测时假设没有运行，让后续逻辑自行处理


def _ensure_cdp():
    """确保 Edge CDP 端口在线。

    策略（按优先级）：
    1. 9222 端口已开放 → 直接返回（用户已启动 CDP Edge）
    2. 端口关闭 + Edge 未运行 → 用默认 profile 启动 Edge + CDP（保留用户登录态）
    3. 端口关闭 + Edge 已在运行 → 报清晰错误，不盲启新实例
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    ok = s.connect_ex(("127.0.0.1", 9222)) == 0
    s.close()
    if ok:
        return

    if _edge_running():
        raise RuntimeError(
            "Edge 已在运行，但未开启远程调试端口 (9222)。\n"
            "请关闭所有 Edge 窗口后重试，CRUX 将自动以 CDP 模式启动 Edge。\n"
            "或手动启动 Edge: msedge.exe --remote-debugging-port=9222"
        )

    # Edge 未运行 → 使用默认 profile 启动（保留用户登录态、Cookie）
    subprocess.Popen(
        [EDGE_PATH,
         "--remote-debugging-port=9222",
         "--no-first-run", "--no-default-browser-check"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(1)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        if s.connect_ex(("127.0.0.1", 9222)) == 0:
            s.close()
            return
        s.close()
    raise RuntimeError("CDP 启动超时（20s）")


def _connect(retries=3):
   """连接 CDP，带重试 + 指数退避"""
   _ensure_cdp()
   pw = sync_playwright().start()
   for i in range(retries):
       try:
           browser = pw.chromium.connect_over_cdp(CDP_URL)
           return pw, browser
       except Exception:
           if i == retries - 1:
               # 最后一次失败：重启 CDP 再试一次
               try:
                   pw.stop()
               except Exception:
                   logger.debug("CDP stop failed", exc_info=True)
               time.sleep(1)
               _ensure_cdp()
               pw2 = sync_playwright().start()
               browser = pw2.chromium.connect_over_cdp(CDP_URL)
               return pw2, browser
           backoff = 2 ** (i + 1)  # 2s, 4s
           time.sleep(backoff)
   raise RuntimeError("CDP 连接失败（已重试+重启）")


@contextmanager
def cdp_session():
   """全局单例 CDP 会话（context manager，自动引用计数）"""
   global _global_state
   with _lock:
       if _global_state["browser"] is None:
           pw, browser = _connect()
           _global_state["pw"] = pw
           _global_state["browser"] = browser
       _global_state["refcount"] += 1
   try:
       yield _global_state["browser"]
   finally:
       with _lock:
           _global_state["refcount"] -= 1
           if _global_state["refcount"] <= 0:
               with contextlib.suppress(Exception):
                   _global_state["pw"].stop()
               _global_state["pw"] = None
               _global_state["browser"] = None
               _global_state["refcount"] = 0


def _get_page(browser, url_hint="", goto_url=""):
   """找已有页面或创建新页面"""
   for ctx in browser.contexts:
       for p in ctx.pages:
           if url_hint and url_hint in p.url:
               p.bring_to_front()
               return p
   ctx = browser.contexts[0] if browser.contexts else browser.new_context()
   page = ctx.new_page()
   if goto_url:
       page.goto(goto_url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
   return page


# ═══════════════════════════════════════════════
#  原子操作（短超时 + JS 降级）
# ═══════════════════════════════════════════════

def safe_click(page, selector, retries=3):
   """点击：Playwright → JS 降级"""
   for i in range(retries):
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
   """填入：Playwright fill → JS DOM 直写（带输入缓冲清理 + 互斥锁）"""
   with _INPUT_LOCK:
       # [Bugfix v6.1] 清空输入区缓冲区，防止历史消息炸出
       _clear_input_buffer(page)
       time.sleep(0.1)

       for i in range(retries):
           try:
               el = page.locator(selector).first
               el.click(timeout=SHORT_TIMEOUT)
               el.fill(text, timeout=SHORT_TIMEOUT)
               return True
           except PwTimeout:
               time.sleep(0.2)
           except Exception:
               break
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
   CRUX 全局浏览器导航（替换原 subprocess 方案）
   持久化会话，自动复用浏览器实例
   返回页面标题和 URL 摘要
   """
   with cdp_session() as browser:
       # 找已有页面或新开
       page = None
       for ctx in browser.contexts:
           for p in ctx.pages:
               if p.url and p.url != "about:blank":
                   page = p
                   break
           if page:
               break
       if not page:
           ctx = browser.contexts[0] if browser.contexts else browser.new_context()
           page = ctx.new_page()
       try:
           # [Bugfix v6.1] 修复滚动失效
           _fix_scroll(page)
           page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
           page.bring_to_front()
           title = page.title()
           body_preview = page.locator("body").inner_text()[:200]
           return json.dumps({
               "success": True,
               "url": page.url,
               "title": title,
               "preview": body_preview,
           }, ensure_ascii=False)
       except PwTimeout:
           return json.dumps({"success": False, "error": "导航超时", "url": url}, ensure_ascii=False)
       except Exception as e:
           return json.dumps({"success": False, "error": str(e), "url": url}, ensure_ascii=False)


def web_fetch_cdp(url: str, max_chars: int = 5000) -> str:
   """
   通过 CDP 浏览器获取网页内容（支持需登录/Spa 页面）
   作为 httpx web_fetch 的补充降级方案
   """
   with cdp_session() as browser:
       page = _get_page(browser, goto_url=url)
       try:
           page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
           time.sleep(1)  # 额外等待 JS 渲染
           text = page.locator("body").inner_text()
           if len(text) > max_chars:
               text = text[:max_chars] + f"\n\n[截断：原 {len(text)} 字符]"
           return text
       except PwTimeout:
           return f"[超时] 无法加载 {url}"
       except Exception as e:
           return f"[错误] {e}"


# ═══════════════════════════════════════════════
#  ChatGPT 专用
# ═══════════════════════════════════════════════

def _chatgpt_page(browser):
   """获取或创建 ChatGPT 页面"""
   for ctx in browser.contexts:
       for p in ctx.pages:
           if "chatgpt.com" in p.url:
               p.bring_to_front()
               return p
   ctx = browser.contexts[0] if browser.contexts else browser.new_context()
   page = ctx.new_page()
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
           pass
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
       ok, reason = _check_cdp_health(browser)
       if not ok:
           browser = _auto_reconnect()

       page = _chatgpt_page(browser)
       time.sleep(2)

       if "chatgpt.com" not in page.url:
           page.goto("https://chatgpt.com/", timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
           time.sleep(3)

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
        img = Image.open(img_path)
        output = _io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        dib_data = output.getvalue()[14:]  # 跳过 BMP 文件头
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib_data)
        win32clipboard.CloseClipboard()
    except Exception as e:
        return f"[Clipboard error: {e}]"

    with cdp_session() as browser:
        ok, _reason = _check_cdp_health(browser)
        if not ok:
            browser = _auto_reconnect()

        page = _chatgpt_page(browser)
        time.sleep(2)

        if "chatgpt.com" not in page.url:
            page.goto("https://chatgpt.com/", timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
            time.sleep(3)

        _fix_scroll(page)
        # [Bugfix v6.2] 关闭通知 toast
        _dismiss_notifications(page)
        _clear_input_buffer(page)

        # 聚焦输入区并粘贴图片
        page.click("#prompt-textarea")
        time.sleep(0.5)
        page.keyboard.press("Control+v")
        time.sleep(3)  # 等待图片上传完成

        # 输入分析文本
        safe_type(page, "#prompt-textarea", text)
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
   """强制清理全局 CDP 连接"""
   global _global_state
   with _lock:
       if _global_state["pw"]:
           try:
               _global_state["pw"].stop()
           except Exception:
               pass
       _global_state["pw"] = None
       _global_state["browser"] = None
       _global_state["refcount"] = 0


def fetch_reply_already_generated() -> str:
   """
   GPT 已生成回复，直接从现有 ChatGPT 页面抓取最新 assistant 消息。
   不发送新问题，不触发新生成。
   适用于 CRUX 掉线后重连取回的场景。
   """
   with cdp_session() as browser:
       ok, reason = _check_cdp_health(browser)
       if not ok:
           browser = _auto_reconnect()
       page = _chatgpt_page(browser)
       try:
           page.wait_for_load_state("domcontentloaded", timeout=10_000)
       except Exception:
           pass
       count = _get_assistant_count(page)
       if count == 0:
           return "[CDP ChatGPT] 未找到 assistant 消息，请确认 ChatGPT 页面有对话记录"
       _wait_chatgpt_done(page, max_wait=10)
       reply = _get_chatgpt_reply(page)
       if not reply:
           return "[CDP ChatGPT] 回复内容为空，可能页面未完全加载"
       return reply
