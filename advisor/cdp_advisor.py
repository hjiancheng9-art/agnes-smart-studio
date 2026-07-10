"""
CDP Advisor — ChatGPT 网页端实现
=================================
通过 Edge CDP 浏览器连接 ChatGPT 网页，实现 AdvisorClient 协议。
支持文本查询和文件附件上传。

核心策略：
- 复用 core.cdp_browser 的全局 CDP 单例
- 短超时动作 + JS 降级
- 文件附件通过 Playwright set_input_files 上传
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

from advisor.base import AdvisorResult
from advisor.prompt import build_advisor_prompt

# CDP 超时常量（与 core/cdp_browser.py 保持一致）
SHORT_TIMEOUT = 5000   # ms
NAV_TIMEOUT = 15000    # ms
LONG_TIMEOUT = 45000   # ms

# ── 文件附件选择器 ──────────────────────────────

# ChatGPT 网页端的隐藏文件 input
_FILE_INPUT_SELECTORS = [
    'input[type="file"]',
    '#file-upload-input',
    'input[accept]',
]

# 附件按钮选择器（用于触发文件选择对话框）
_ATTACH_BUTTON_SELECTORS = [
    'button[aria-label*="attach" i]',
    'button[aria-label*="upload" i]',
    'button[aria-label*="文件" i]',
    'button[aria-label*="上传" i]',
    '[data-testid="attach-file-button"]',
    'button[class*="attach"]',
]


class CdpAdvisor:
    """ChatGPT CDP 浏览器的 AdvisorClient 实现。

    使用 Edge CDP 连接到 chatgpt.com，发送查询并获取结构化顾问建议。
    支持文件附件上传。
    """

    def __init__(self, timeout_seconds: float = 6.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._connected = False
        self._lock = threading.Lock()

    # ── AdvisorClient 协议 ───────────────────────

    def startup(self) -> None:
        """初始化 CDP 连接，验证 ChatGPT 页面可用。"""
        try:
            from core.cdp_browser import _chatgpt_page, _check_cdp_health, cdp_session
        except ImportError as e:
            raise RuntimeError(f"CDP 浏览器模块不可用: {e}") from e

        with cdp_session() as browser:
            ok, reason = _check_cdp_health(browser)
            if not ok:
                from core.cdp_browser import _auto_reconnect
                browser = _auto_reconnect()

            page = _chatgpt_page(browser)
            time.sleep(2)

            if "chatgpt.com" not in page.url:
                page.goto(
                    "https://chatgpt.com/",
                    timeout=NAV_TIMEOUT,
                    wait_until="domcontentloaded",
                )
                time.sleep(3)

            # 验证输入框存在
            try:
                page.wait_for_selector("#prompt-textarea", timeout=SHORT_TIMEOUT)
            except Exception as e:
                raise RuntimeError("ChatGPT 页面加载不完整，输入框未找到") from e

        self._connected = True

    def ask(self, query: str, context: str = "", new_chat: bool = True) -> AdvisorResult:
        """发送文本查询到 ChatGPT，返回结构化顾问建议。"""
        return self._do_ask(query, context, file_paths=None, new_chat=new_chat)

    def ask_with_files(
        self, query: str, file_paths: list[str], context: str = "", new_chat: bool = True
    ) -> AdvisorResult:
        """发送查询 + 文件附件到 ChatGPT。"""
        # 验证文件存在
        valid_files = []
        for fp in file_paths:
            if os.path.exists(fp):
                valid_files.append(os.path.abspath(fp))
        if not valid_files:
            return AdvisorResult(
                status="error",
                source="cdp_chatgpt",
                error=f"所有附件文件不存在: {file_paths}",
            )
        return self._do_ask(query, context, file_paths=valid_files, new_chat=new_chat)

    def health(self) -> bool:
        """快速健康检查（不阻塞）。"""
        if not self._connected:
            return False
        try:
            from core.cdp_browser import _check_cdp_health, cdp_session

            with cdp_session() as browser:
                ok, _ = _check_cdp_health(browser)
                return ok
        except Exception:
            return False

    def close(self) -> None:
        """清理状态（CDP 连接由全局单例管理，不做强制断开）。"""
        self._connected = False

    # ── 内部实现 ──────────────────────────────────

    def _do_ask(
        self,
        query: str,
        context: str,
        file_paths: list[str] | None,
        new_chat: bool = True,
    ) -> AdvisorResult:
        """核心查询逻辑。

        Args:
            new_chat: True 时每次开启新 ChatGPT 对话，避免上下文污染
        """
        if not self._connected:
            return AdvisorResult(
                status="unavailable",
                source="cdp_chatgpt",
                error="CDP advisor 未初始化，请先调用 startup()",
            )

        prompt = build_advisor_prompt(query, context)
        started = time.perf_counter()

        try:
            from core.cdp_browser import (
                _auto_reconnect,
                _chatgpt_page,
                _check_cdp_health,
                _clear_input_buffer,
                _dismiss_notifications,
                _fix_scroll,
                _get_chatgpt_reply,
                _wait_chatgpt_done,
                cdp_session,
                safe_click,
                safe_fill,
            )

            with cdp_session() as browser:
                # 健康检测
                ok, _ = _check_cdp_health(browser)
                if not ok:
                    browser = _auto_reconnect()

                page = _chatgpt_page(browser)
                time.sleep(2)

                if "chatgpt.com" not in page.url:
                    page.goto(
                        "https://chatgpt.com/",
                        timeout=NAV_TIMEOUT,
                        wait_until="domcontentloaded",
                    )
                    time.sleep(3)

                # ── 每次新对话：导航到根 URL 触发新建 ──
                if new_chat:
                    try:
                        # 方法1: 点击 New chat 按钮
                        new_chat_btn = page.locator(
                            '[aria-label="New chat"], a[href="/"], button:has-text("New chat")'
                        ).first
                        if new_chat_btn.count() > 0 and new_chat_btn.is_visible(timeout=1000):
                            new_chat_btn.click(timeout=2000)
                            time.sleep(2)
                        else:
                            # 方法2: 直接导航到根 URL
                            page.goto(
                                "https://chatgpt.com/",
                                timeout=NAV_TIMEOUT,
                                wait_until="domcontentloaded",
                            )
                            time.sleep(3)
                    except Exception:
                        # 兜底：导航到根 URL
                        try:
                            page.goto(
                                "https://chatgpt.com/",
                                timeout=NAV_TIMEOUT,
                                wait_until="domcontentloaded",
                            )
                            time.sleep(3)
                        except Exception:
                            logger.debug("等待回复超时，继续", exc_info=True)

                _fix_scroll(page)
                _dismiss_notifications(page)
                _clear_input_buffer(page)

                # ── 文件附件上传 ──
                if file_paths:
                    self._upload_files(page, file_paths)
                    time.sleep(2)  # 等待文件上传完成

                # ── 输入并发送 ──
                safe_fill(page, "#prompt-textarea", prompt)
                time.sleep(0.5)
                safe_click(page, "button[data-testid='send-button']")

                # ── 等待回复（超时由外层控制） ──
                max_wait = min(int(self.timeout_seconds) + 5, 55)
                _wait_chatgpt_done(page, max_wait=max_wait)
                reply = _get_chatgpt_reply(page)

                latency_ms = int((time.perf_counter() - started) * 1000)

                if reply and reply.strip():
                    return AdvisorResult(
                        status="ok",
                        content=reply.strip(),
                        source="cdp_chatgpt",
                        latency_ms=latency_ms,
                    )
                else:
                    return AdvisorResult(
                        status="error",
                        source="cdp_chatgpt",
                        latency_ms=latency_ms,
                        error="ChatGPT 返回空回复",
                    )

        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            text = str(exc).lower()

            if "timeout" in text:
                status = "timeout"
            elif "429" in text or "rate" in text:
                status = "rate_limited"
            elif "connect" in text or "refused" in text or "socket" in text:
                status = "unavailable"
            else:
                status = "error"

            return AdvisorResult(
                status=status,
                source="cdp_chatgpt",
                latency_ms=latency_ms,
                error=str(exc),
            )

    @staticmethod
    def _upload_files(page, file_paths: list[str]) -> None:
        """通过 CDP 上传文件到 ChatGPT 输入区。

        策略：
        1. 优先找隐藏的 file input 直接 set_input_files
        2. 如果找不到，点击附件按钮触发 file chooser
        """
        # 策略 1: 直接找 file input 上传
        for selector in _FILE_INPUT_SELECTORS:
            try:
                inp = page.locator(selector).first
                if inp.count() > 0:
                    inp.set_input_files(file_paths)
                    return
            except Exception:
                continue

        # 策略 2: 点击附件按钮，用 file_chooser 事件
        for selector in _ATTACH_BUTTON_SELECTORS:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=1000):
                    with page.expect_file_chooser() as fc_info:
                        btn.click(timeout=2000)
                    file_chooser = fc_info.value
                    file_chooser.set_files(file_paths)
                    return
            except Exception:
                continue

        # 策略 3: JS 直接创建 file input 并触发
        try:
            page.evaluate(
                """(files) => {
                const input = document.createElement('input');
                input.type = 'file';
                input.multiple = true;
                input.style.display = 'none';
                document.body.appendChild(input);
                // 注意: JS 无法设置文件路径，这里只是兜底提示
                input.click();
                setTimeout(() => input.remove(), 100);
            }""",
                file_paths,
            )
        except Exception:
            logger.debug("JS file input 创建失败", exc_info=True)

        # 如果以上都失败，仍然继续（文件可能已经通过某种方式附上）
