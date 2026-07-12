"""
Browser Control — Native capability for CRUX Studio.
=====================================================
Playwright CDP 全浏览器操控：ChatGPT, Gemini, Kling, Jimeng, Runway, Luma
自动填入、提交、读取回复与结果回传。

架构：
    BrowserController (主控)
        ├── PlatformAdapter (抽象)
        │   ├── ChatGPTAdapter
        │   ├── GeminiAdapter
        │   ├── KlingAdapter
        │   ├── JimengAdapter
        │   ├── RunwayAdapter
        │   └── LumaAdapter
        └── CDP连接管理 (已有浏览器 > 启动新浏览器)

用法：
    from core.browser_control import browser_control, send_to_ai, read_from_ai

    # 一行发送
    result = send_to_ai("chatgpt", "写一首关于春天的诗")

    # 或者分步操控
    bc = browser_control()
    bc.navigate("chatgpt")
    bc.fill_prompt("写一首关于春天的诗")
    bc.submit()
    reply = bc.read_response(timeout=120)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# 平台选择器配置 — 从 browser-control.skill.json 提取
# ============================================================

@dataclass
class PlatformConfig:
    """单个 AI 平台的 DOM 选择器与交互策略"""
    name: str
    url: str
    # 输入框选择器（按优先级排列）
    input_selectors: list[str] = field(default_factory=list)
    # 提交方式: "enter" | "click"
    submit_method: str = "enter"
    submit_selectors: list[str] = field(default_factory=list)
    # 回复容器选择器
    response_selectors: list[str] = field(default_factory=list)
    # 等待策略
    wait_strategy: str = "response_appears"  # response_appears | progress_done | element_count
    wait_selector: str = ""
    wait_timeout: int = 240  # 最长等待秒数
    poll_interval: float = 2.0
    # 特殊行为
    new_chat_selector: str = ""
    contenteditable: bool = False
    inject_text_events: bool = False


# 平台配置表
PLATFORMS: dict[str, PlatformConfig] = {
    "chatgpt": PlatformConfig(
        name="ChatGPT",
        url="https://chatgpt.com",
        input_selectors=[
            'div#prompt-textarea[contenteditable="true"]',
            '#prompt-textarea',
            '[data-id="root"] [contenteditable="true"]',
        ],
        submit_method="enter",
        submit_selectors=['[data-testid="send-button"]', 'button[aria-label="Send"]'],
        response_selectors=[
            '[data-message-author-role="assistant"]',
            '.markdown',
        ],
        wait_strategy="response_appears",
        wait_selector='[data-message-author-role="assistant"]',
        wait_timeout=240,
        poll_interval=2.0,
        new_chat_selector='button:has-text("New chat"), a:has-text("New chat")',
        contenteditable=True,
    ),
    "gemini": PlatformConfig(
        name="Gemini",
        url="https://gemini.google.com",
        input_selectors=[
            '.ql-editor[contenteditable="true"]',
            'div.ql-editor',
            'rich-textarea [contenteditable="true"]',
        ],
        submit_method="click",
        submit_selectors=['button[aria-label="Send message"]', 'button.send-button'],
        response_selectors=[
            '.message-content',
            '[class*="response"]',
            '[class*="model-response"]',
        ],
        wait_strategy="response_appears",
        wait_selector='.message-content, [class*="response"]',
        wait_timeout=240,
        poll_interval=2.0,
        contenteditable=True,
        inject_text_events=True,
    ),
    "kling": PlatformConfig(
        name="Kling",
        url="https://klingai.com",
        input_selectors=[
            'textarea',
            '.input-area textarea',
            '[class*="prompt"] textarea',
        ],
        submit_method="click",
        submit_selectors=[
            'button:has-text("生成")',
            'button:has-text("Generate")',
            '[class*="generate"]',
        ],
        response_selectors=[
            'video',
            '[class*="result"] video',
            '[class*="output"]',
        ],
        wait_strategy="progress_done",
        wait_selector='[class*="progress"], [class*="loading"]',
        wait_timeout=600,
        poll_interval=3.0,
    ),
    "jimeng": PlatformConfig(
        name="Jimeng",
        url="https://jimeng.jianying.com",
        input_selectors=[
            'textarea',
            '.prompt-input',
            '[class*="input"] textarea',
        ],
        submit_method="click",
        submit_selectors=[
            'button:has-text("生成")',
            '[class*="generate"]',
            '[class*="submit"]',
        ],
        response_selectors=[
            'img[class*="result"]',
            '[class*="output"] img',
            '.generated-image',
        ],
        wait_strategy="element_count",
        wait_selector='img[class*="result"], [class*="output"] img',
        wait_timeout=300,
        poll_interval=2.0,
    ),
    "runway": PlatformConfig(
        name="Runway",
        url="https://runwayml.com",
        input_selectors=[
            'textarea',
            '.prompt-field textarea',
            '[class*="prompt"] textarea',
        ],
        submit_method="click",
        submit_selectors=[
            'button:has-text("Generate")',
            '[class*="generate"]',
            'button[type="submit"]',
        ],
        response_selectors=[
            'video',
            '[class*="output"] video',
            '[class*="result"]',
        ],
        wait_strategy="progress_done",
        wait_selector='[class*="progress"]',
        wait_timeout=600,
        poll_interval=3.0,
    ),
    "luma": PlatformConfig(
        name="Luma",
        url="https://lumalabs.ai",
        input_selectors=[
            'textarea',
            '.prompt-box textarea',
            '[class*="prompt"] textarea',
        ],
        submit_method="click",
        submit_selectors=[
            'button:has-text("Generate")',
            'button:has-text("Dream")',
            '[class*="generate"]',
        ],
        response_selectors=[
            'video',
            'img[class*="result"]',
            '[class*="output"]',
        ],
        wait_strategy="progress_done",
        wait_selector='[class*="progress"], [class*="loading"]',
        wait_timeout=600,
        poll_interval=3.0,
    ),
}

# ============================================================
# BrowserController — 主控类
# ============================================================

CDP_URL = "http://127.0.0.1:9222"
OUTPUT_DIR = "output"


class BrowserController:
    """Playwright CDP 浏览器主控

    优先连接已有 CDP 浏览器，找不到则启动新的 headless 浏览器。
    """

    def __init__(self, headless: bool = False, cdp_url: str = CDP_URL):
        self._playwright = None
        self._browser = None
        self._page = None
        self._headless = headless
        self._cdp_url = cdp_url
        self._connected_via_cdp = False
        self._platform: PlatformConfig | None = None

    def _ensure_playwright(self):
        """延迟导入 playwright，避免未安装时崩溃"""
        if self._playwright is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as err:
                raise ImportError(
                    "Playwright 未安装。运行: pip install playwright && playwright install chromium"
                ) from err
            self._playwright = sync_playwright().start()

    def connect(self, timeout: float = 5.0) -> bool:
        """连接到浏览器。优先 CDP，失败则启动 Edge（保留用户登录态）。

        Args:
            timeout: CDP 连接超时（秒）
        """
        self._ensure_playwright()

        # 方式1: CDP 连接已有浏览器 (带超时)
        if timeout is not None:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            try:
                s.connect(('127.0.0.1', 9222))
                s.close()
            except Exception:
                s.close()
                logger.debug("CDP 端口不可达，尝试启动 Edge")
                timeout = None  # 跳过 CDP，走启动流程

        if timeout is not None:
            try:
                self._browser = self._playwright.chromium.connect_over_cdp(
                    self._cdp_url, timeout=int(timeout * 1000)
                )
                contexts = self._browser.contexts
                if contexts and contexts[0].pages:
                    self._page = contexts[0].pages[-1]
                else:
                    self._page = contexts[0].new_page() if contexts else self._browser.new_context().new_page()
                self._connected_via_cdp = True
                logger.info(f"CDP 已连接: {self._cdp_url}")
                return True
            except Exception as e:
                logger.debug(f"CDP 连接失败 ({e})，尝试启动 Edge")

        # 方式2: 启动 Edge 浏览器（使用默认 profile，保留用户登录态）
        try:
            from core.cdp_browser import _ensure_cdp, _connect as cdp_connect
            try:
                _ensure_cdp()
            except RuntimeError as e:
                logger.error(f"启动 Edge 失败: {e}")
                return False
            self._playwright.stop()
            self._playwright = None
            self._ensure_playwright()
            self._browser = self._playwright.chromium.connect_over_cdp(
                self._cdp_url, timeout=10000
            )
            contexts = self._browser.contexts
            if contexts and contexts[0].pages:
                self._page = contexts[0].pages[-1]
            else:
                self._page = contexts[0].new_page() if contexts else self._browser.new_context().new_page()
            self._connected_via_cdp = True
            logger.info("已启动 Edge (CDP 模式，默认 profile)")
            return True
        except Exception as e:
            logger.error(f"启动 Edge 失败: {e}")
            return False

    def ensure_page(self, platform_name: str | None = None) -> bool:
        """确保浏览器已连接并有可用页面（不强制重新导航）

        Args:
            platform_name: 可选，指定目标平台

        Returns:
            是否有可用页面
        """
        # 已有可用页面
        if self.is_connected:
            if platform_name and self.current_platform != PLATFORMS.get(platform_name, PlatformConfig(name="?").name):
                return self.navigate(platform_name)
            return True

        # 需要重新连接
        if not self.connect():
            return False

        if platform_name:
            return self.navigate(platform_name)
        return True

    def navigate(self, platform_name: str) -> bool:
        """导航到指定 AI 平台。已在同一平台时跳过导航。"""
        platform_name = platform_name.lower()
        if platform_name not in PLATFORMS:
            raise ValueError(f"未知平台: {platform_name}。可用: {list(PLATFORMS.keys())}")

        self._platform = PLATFORMS[platform_name]

        if not self._page or not self.connect():
            return False

        # 已在同一页面，跳过导航
        try:
            current_url = self._page.url
            target_host = self._platform.url.split("://")[-1].split("/")[0]
            if target_host in current_url:
                logger.info(f"已在 {self._platform.name}，跳过导航")
                return True
        except Exception:
            import logging
            logging.getLogger('crux').debug('silent except', exc_info=True)

        try:
            self._page.goto(self._platform.url, wait_until="domcontentloaded", timeout=30000)
            logger.info(f"已导航到 {self._platform.name}: {self._platform.url}")
            return True
        except Exception as e:
            logger.error(f"导航失败: {e}")
            return False

    def find_input(self) -> Any:
        """多策略查找输入框"""
        if not self._page or not self._platform:
            return None

        config = self._platform

        # 策略1: 按配置的选择器依次尝试
        for selector in config.input_selectors:
            try:
                el = self._page.locator(selector).first
                if el.is_visible(timeout=1000):
                    logger.info(f"输入框已找到: {selector}")
                    return el
            except Exception:
                continue

        # 策略2: 泛化搜索 — 任何 textarea
        try:
            el = self._page.locator('textarea').first
            if el.is_visible(timeout=1000):
                logger.info("输入框已找到 (textarea fallback)")
                return el
        except Exception:
            import logging
            logging.getLogger('crux').debug('silent except', exc_info=True)

        # 策略3: contenteditable
        try:
            el = self._page.locator('[contenteditable="true"]').first
            if el.is_visible(timeout=1000):
                logger.info("输入框已找到 (contenteditable fallback)")
                return el
        except Exception:
            import logging
            logging.getLogger('crux').debug('silent except', exc_info=True)

        # 策略4: role=textbox
        try:
            el = self._page.get_by_role("textbox").first
            if el.is_visible(timeout=1000):
                logger.info("输入框已找到 (role=textbox fallback)")
                return el
        except Exception:
            import logging
            logging.getLogger('crux').debug('silent except', exc_info=True)

        logger.warning("未找到输入框")
        return None

    def find_submit_button(self) -> Any:
        """查找提交按钮"""
        if not self._page or not self._platform:
            return None

        for selector in self._platform.submit_selectors:
            try:
                btn = self._page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    return btn
            except Exception:
                continue
        return None

    def fill_prompt(self, text: str) -> bool:
        """填入提示词到输入框"""
        if not self._page or not self._platform:
            return False

        input_el = self.find_input()
        if not input_el:
            return False

        try:
            config = self._platform

            if config.contenteditable or config.inject_text_events:
                # contenteditable 类型输入框 — 需要特殊处理
                input_el.click()
                time.sleep(0.3)
                # 清空
                self._page.keyboard.press("Control+a")
                self._page.keyboard.press("Backspace")
                time.sleep(0.1)
                # 填入
                input_el.type(text, delay=10)
            else:
                # 标准 textarea
                input_el.click()
                input_el.fill(text)

            # Gemini 特殊：触发 input 事件
            if config.inject_text_events:
                try:
                    input_el.dispatch_event("input")
                except Exception:
                    logger.debug("dispatch_event 失败", exc_info=True)

            logger.info(f"已填入提示词 ({len(text)} 字符)")
            return True
        except Exception as e:
            logger.error(f"填入失败: {e}")
            return False

    def submit(self) -> bool:
        """提交提示词"""
        if not self._page or not self._platform:
            return False

        try:
            if self._platform.submit_method == "enter":
                self._page.keyboard.press("Enter")
                logger.info("已提交 (Enter)")
                return True
            else:
                btn = self.find_submit_button()
                if btn:
                    btn.click()
                    logger.info("已提交 (click)")
                    return True
                # 回退到 Enter
                self._page.keyboard.press("Enter")
                logger.info("已提交 (Enter fallback)")
                return True
        except Exception as e:
            logger.error(f"提交失败: {e}")
            return False

    def read_response(self, timeout: int | None = None) -> str | None:
        """轮询等待并读取 AI 回复

        Args:
            timeout: 最长等待秒数，默认使用平台配置

        Returns:
            回复文本内容，失败返回 None
        """
        if not self._page or not self._platform:
            return None

        config = self._platform
        max_wait = timeout or config.wait_timeout
        poll = config.poll_interval
        deadline = time.time() + max_wait

        strategy = config.wait_strategy

        logger.info(f"等待 {config.name} 回复 (最长 {max_wait}s, 策略: {strategy})")

        while time.time() < deadline:
            try:
                if strategy == "response_appears":
                    result = self._read_response_appears()
                elif strategy == "progress_done":
                    result = self._read_progress_done()
                elif strategy == "element_count":
                    result = self._read_element_count()
                else:
                    result = self._read_response_appears()

                if result:
                    logger.info(f"已获取回复 ({len(result)} 字符)")
                    return result
            except Exception as e:
                logger.debug(f"轮询中: {e}")

            time.sleep(poll)

        logger.warning(f"等待超时 ({max_wait}s)")
        return None

    def _read_response_appears(self) -> str | None:
        """策略: 等待回复容器出现并有内容"""
        for selector in self._platform.response_selectors:
            try:
                elements = self._page.locator(selector).all()
                for el in elements:
                    if el.is_visible():
                        text = el.inner_text().strip()
                        # 至少30字符，且不含 stop-button（防止 ChatGPT 还在生成）
                        if len(text) > 30 and not self._has_stop_button():
                            return text
            except Exception:
                continue
        return None

    def _read_progress_done(self) -> str | None:
        """策略: 等待进度条消失"""
        wait_sel = self._platform.wait_selector
        if wait_sel:
            try:
                # 如果进度条还在，说明没完成
                progress = self._page.locator(wait_sel).first
                if progress.is_visible():
                    return None
            except Exception:
                pass  # 进度条不可见 = 可能已完成

        # 进度条消失，读取结果
        for selector in self._platform.response_selectors:
            try:
                el = self._page.locator(selector).first
                if el.is_visible():
                    text = el.inner_text().strip()
                    if text:
                        return text
                    # 可能是媒体元素（video/img），返回属性
                    src = el.get_attribute("src")
                    if src:
                        return src
            except Exception:
                continue
        return None

    def _read_element_count(self) -> str | None:
        """策略: 等待目标元素出现"""
        wait_sel = self._platform.wait_selector
        if wait_sel:
            try:
                count = self._page.locator(wait_sel).count()
                if count == 0:
                    return None
            except Exception:
                return None

        for selector in self._platform.response_selectors:
            try:
                el = self._page.locator(selector).first
                if el.is_visible():
                    src = el.get_attribute("src") or el.inner_text().strip()
                    if src:
                        return src
            except Exception:
                continue
        return None

    def _has_stop_button(self) -> bool:
        """检测 ChatGPT 是否还在生成中"""
        try:
            btn = self._page.locator('[data-testid="stop-button"], [aria-label="Stop"]').first
            return btn.is_visible()
        except Exception:
            return False

    def new_chat(self) -> bool:
        """在 ChatGPT 中开启新对话"""
        if not self._page or not self._platform:
            return False

        selector = self._platform.new_chat_selector
        if not selector:
            logger.info(f"{self._platform.name} 无需新对话按钮")
            return True

        try:
            btn = self._page.locator(selector).first
            if btn.is_visible(timeout=3000):
                btn.click()
                time.sleep(2)
                logger.info("已开启新对话")
                return True
        except Exception as e:
            logger.warning(f"新对话失败: {e}")
        return False

    def disconnect(self):
        """断开 CDP 连接（不关闭用户浏览器窗口）"""
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            import logging
            logging.getLogger('crux').debug('silent except', exc_info=True)
        finally:
            self._browser = None
            self._page = None
            self._platform = None

    def close(self):
        """关闭浏览器（headless 模式会彻底关闭；CDP 模式只断开连接，保留用户窗口）"""
        self.disconnect()

    @property
    def is_connected(self) -> bool:
        """检查是否已连接且页面可用"""
        if self._page is None or self._browser is None:
            return False
        try:
            # 轻量探活 — 不发网络请求，只检查 page 对象是否还活着
            _ = self._page.url  # 探活
            return True
        except Exception:
            self._browser = None
            self._page = None
            return False

    @property
    def current_platform(self) -> str | None:
        return self._platform.name if self._platform else None


# ============================================================
# 便捷函数 — 一行调用
# ============================================================

# 全局单例
_browser_instance: BrowserController | None = None


def browser_control() -> BrowserController:
    """获取 BrowserController 单例"""
    global _browser_instance
    if _browser_instance is None or not _browser_instance.is_connected:
        _browser_instance = BrowserController()
    return _browser_instance


def send_to_ai(platform: str, prompt: str, timeout: int | None = None) -> dict:
    """向 AI 平台发送提示词并获取回复（一站式，浏览器保持打开）

    重要：调用后浏览器保持连接，不会关闭。重复调用复用同一会话。
    如需关闭，手动调用 browser_control().disconnect()

    Args:
        platform: 平台名称 (chatgpt, gemini, kling, jimeng, runway, luma)
        prompt: 提示词内容
        timeout: 超时秒数

    Returns:
        {
            "success": bool,
            "platform": str,
            "prompt": str,
            "response": str | None,
            "error": str | None,
            "screenshot": str | None,
        }
    """
    result = {
        "success": False,
        "platform": platform,
        "prompt": prompt,
        "response": None,
        "error": None,
    }

    bc = browser_control()

    try:
        # 只在未连接时才连，已连接的复用
        if not bc.is_connected and not bc.connect(timeout=3.0):
            result["error"] = "无法连接到浏览器 (CDP 端口不可达且无法启动 headless)"
            return result

        # 只在平台变化时才导航，减少页面刷新
        if bc.current_platform != PLATFORMS[platform].name:
            if not bc.navigate(platform):
                result["error"] = f"无法导航到 {platform}"
                return result
            time.sleep(2)  # 等待页面加载

        if not bc.fill_prompt(prompt):
            result["error"] = "无法填入提示词 — 请检查页面是否已加载完成，重试"
            return result

        time.sleep(0.5)

        if not bc.submit():
            result["error"] = "提交失败"
            return result

        response = bc.read_response(timeout=timeout)
        if response:
            result["success"] = True
            result["response"] = response
        else:
            result["error"] = "等待回复超时 — 页面可能仍在生成中，请重试"
    except Exception as e:
        result["error"] = f"浏览器操作异常: {str(e)[:200]}"

    # 不关闭浏览器，保持连接供后续复用
    return result


def read_from_ai(platform: str, timeout: int | None = None) -> str | None:
    """从已经打开的平台页面读取回复"""
    bc = browser_control()
    if not bc.is_connected:
        return None
    return bc.read_response(timeout=timeout)


def list_platforms() -> dict[str, str]:
    """列出所有支持的 AI 平台"""
    return {k: v.url for k, v in PLATFORMS.items()}


# ============================================================
# 尝试注册到能力注册表
# ============================================================

def _register_to_capability_registry():
    """将 browser-control 注册到系统的能力注册表"""
    try:
        from core.capability_registry import CapabilityRegistry
        registry = CapabilityRegistry()
        registry.register(
            name="browser-control",
            description="Playwright CDP 全浏览器操控 — ChatGPT, Gemini, Kling, Jimeng, Runway, Luma",
            category="browser",
            permissions=["network", "process"],
            rate_limit_rpm=5,
        )
        logger.info("browser-control 已注册到能力注册表")
    except Exception:
        pass  # 非关键路径


_register_to_capability_registry()
