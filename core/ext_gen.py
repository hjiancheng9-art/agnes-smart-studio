"""外部生成源连接器 — Web、API、CLI

支持的生成源:
  - ChatGPT Web (通过 Playwright 自动化)
  - Gemini Web (通过 Playwright 自动化)
  - 即梦 (jimeng.jianying.com) — 字节跳动/即梦 Web
  - Google Video (通过 Playwright)
  - Opal (opal.google)
  - Gemini API
  - CLI 命令

用法:
  from core.ext_gen import ExternalGenerator
  gen = ExternalGenerator()
  # Web 方式
  result = await gen.chatgpt_web("generate an image of a dragon")
  result = await gen.gemini_web("create a video script")
  # API 方式
  img = await gen.gemini_api("a beautiful sunset over mountains")
  # CLI 方式
  output = await gen.cli_exec("ffmpeg -i input.mp4 -vf scale=1920:1080 output.mp4")
"""

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    'ExternalGenerator', 'GenSource', 'OUTPUT', 'ROOT', 'list_external_sources',
]

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

# ======================================================================
# Source Registry
# ======================================================================

@dataclass
class GenSource:
    """Descriptor for an external generation source."""
    name: str
    kind: str           # "web" | "api" | "cli"
    description: str
    url: str = ""
    enabled: bool = True
    requires_auth: bool = False
    supports: list[str] = field(default_factory=list)  # ["image", "video", "text"]

BUILTIN_SOURCES: dict[str, GenSource] = {
    "chatgpt_web": GenSource(
        name="ChatGPT Web",
        kind="web",
        description="ChatGPT 网页界面，支持图片生成和文本对话",
        url="https://chat.openai.com",
        requires_auth=True,
        supports=["text", "image"],
    ),
    "gemini_web": GenSource(
        name="Gemini Web",
        kind="web",
        description="Google Gemini 网页界面",
        url="https://gemini.google.com",
        requires_auth=True,
        supports=["text"],
    ),
    "jimeng_web": GenSource(
        name="即梦 Web",
        kind="web",
        description="即梦 (jimeng.jianying.com) 网页界面，字节跳动/即梦图片/视频生成",
        url="https://jimeng.jianying.com/ai-tool/home",
        requires_auth=True,
        supports=["image", "video"],
    ),
    "google_video": GenSource(
        name="Google Video",
        kind="web",
        description="Google Video 生成 (docs.google.com/videos)",
        url="https://docs.google.com/videos",
        requires_auth=True,
        supports=["video"],
    ),
    "opal": GenSource(
        name="Opal",
        kind="web",
        description="Opal (opal.google) 聚焦模式",
        url="https://opal.google",
        requires_auth=True,
        supports=["text"],
    ),
    "gemini_api": GenSource(
        name="Gemini API",
        kind="api",
        description="Google Gemini API 直接调用",
        supports=["text", "image"],
    ),
    "cli": GenSource(
        name="CLI",
        kind="cli",
        description="Local command line execution",
        supports=["image", "video", "audio", "text"],
    ),
}

# ======================================================================
# External Generator
# ======================================================================

class ExternalGenerator:
    """Unified interface for external generation sources.

    Features:
    - 统一的 generate_image / generate_video / generate_text 接口
    - 自动选择可用源（从高到低优先级）
    - Web sources via Playwright automation
    - API 源直接调用
    - CLI 源本地执行
    """

    def __init__(self, playwright=None) -> None:
        self._pw = playwright  # Playwright instance (shared)
        self._sources: dict[str, GenSource] = dict(BUILTIN_SOURCES)
        self._source_order = ["chatgpt_web", "gemini_api", "gemini_web",
                               "jimeng_web", "google_video", "opal", "cli"]

    def list_sources(self) -> list[GenSource]:
        return list(self._sources.values())

    def get_source(self, name: str) -> GenSource | None:
        return self._sources.get(name)

    # ---- Top-level API ----

    async def generate_image(self, prompt: str, source: str | None = None,
                              size: str = "1024x1024") -> dict:
        """Generate image from prompt, auto-selecting source."""
        if source and source in self._sources:
            return await self._dispatch(source, "image", prompt, size=size)
        for s in self._source_order:
            src = self._sources.get(s)
            if src and src.enabled and "image" in src.supports:
                try:
                    return await self._dispatch(s, "image", prompt, size=size)
                except (OSError, RuntimeError, ValueError):
                    continue
        raise RuntimeError("No available image generation source")

    async def generate_video(self, prompt: str, source: str | None = None,
                              images: list | None = None) -> dict:
        """Generate video, auto-selecting source."""
        if source and source in self._sources:
            return await self._dispatch(source, "video", prompt, images=images or [])
        for s in self._source_order:
            src = self._sources.get(s)
            if src and src.enabled and "video" in src.supports:
                try:
                    return await self._dispatch(s, "video", prompt, images=images or [])
                except (OSError, ValueError, RuntimeError):
                    continue
        raise RuntimeError("No available video generation source")

    async def generate_text(self, prompt: str, source: str | None = None) -> dict:
        """Generate text, auto-selecting source."""
        if source and source in self._sources:
            return await self._dispatch(source, "text", prompt)
        for s in self._source_order:
            src = self._sources.get(s)
            if src and src.enabled and "text" in src.supports:
                try:
                    return await self._dispatch(s, "text", prompt)
                except (OSError, ValueError, RuntimeError):
                    continue
        raise RuntimeError("No available text generation source")

    async def _dispatch(self, source_name: str, task: str,
                        prompt: str, **kwargs) -> dict:
        """Route to the correct implementation."""
        method_map = {
            "chatgpt_web": self._chatgpt_web,
            "gemini_web": self._gemini_web,
            "jimeng_web": self._jimeng_web,
            "google_video": self._google_video,
            "opal": self._opal,
            "gemini_api": self._gemini_api,
            "cli": self._cli_exec,
        }
        handler = method_map.get(source_name)
        if handler is None:
            raise ValueError(f"Unknown source: {source_name}")
        result = await handler(task, prompt, **kwargs)
        return {"source": source_name, "result": result}

    # ---- Web Sources (Playwright) ----

    async def _chatgpt_web(self, task: str, prompt: str,
                            size: str = "1024x1024") -> dict:
        """Automate ChatGPT web interface."""
        if self._pw is None:
            return {"error": "Playwright not available", "prompt": prompt}
        try:
            page = await self._pw.new_page()
            await page.goto("https://chat.openai.com", wait_until="domcontentloaded",
                            timeout=30000)
            # Type prompt into the message input
            await page.fill('[data-testid="chat-input"]', prompt)
            await page.click('[data-testid="send-button"]')
            # Wait for response
            await page.wait_for_selector('[data-message-author-role="assistant"]',
                                        timeout=120000)
            response_text = await page.text_content(
                '[data-message-author-role="assistant"]')
            await page.close()
            return {"text": response_text}
        except (OSError, RuntimeError, ValueError) as e:
            return {"error": str(e)}

    async def _gemini_web(self, task: str, prompt: str) -> dict:
        """Automate Gemini web interface."""
        if self._pw is None:
            return {"error": "Playwright not available", "prompt": prompt}
        try:
            page = await self._pw.new_page()
            await page.goto("https://gemini.google.com", wait_until="domcontentloaded",
                            timeout=30000)
            await page.fill('textarea, [contenteditable="true"]', prompt)
            await page.keyboard.press("Enter")
            await asyncio.sleep(3)
            # Try to extract response
            response_el = await page.query_selector('.response-content, .message-content')
            text = await response_el.text_content() if response_el else ""
            await page.close()
            return {"text": text[:2000]}
        except (OSError, RuntimeError, ValueError) as e:
            return {"error": str(e)}

    async def _jimeng_web(self, task: str, prompt: str,
                           size: str = "1024x1024") -> dict:
        """Automate 即梦 web interface."""
        if self._pw is None:
            return {"error": "Playwright not available", "prompt": prompt}
        try:
            page = await self._pw.new_page()
            # 即梦 uses jianying.com
            await page.goto("https://jimeng.jianying.com/ai-tool/home",
                            wait_until="domcontentloaded", timeout=30000)
            # Wait for login/prompt area
            await asyncio.sleep(2)
            # Try to find text input
            input_el = await page.query_selector('textarea, input[type="text"]')
            if input_el:
                await input_el.fill(prompt)
                await page.keyboard.press("Enter")
                await asyncio.sleep(10)  # wait for generation
                # Try to get result image URL
                images = await page.query_selector_all('img[src*="generate"]')
                urls = []
                for img in images:
                    src = await img.get_attribute("src")
                    if src:
                        urls.append(src)
                await page.close()
                return {"image_urls": urls, "prompt": prompt}
            await page.close()
            return {"error": "Could not find input element", "prompt": prompt}
        except (OSError, RuntimeError, ValueError) as e:
            return {"error": str(e)}

    async def _google_video(self, task: str, prompt: str,
                            images: list | None = None) -> dict:
        """Automate Google Video web interface."""
        if self._pw is None:
            return {"error": "Playwright not available", "prompt": prompt}
        try:
            page = await self._pw.new_page()
            await page.goto("https://docs.google.com/videos",
                            wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            # This is a simplified automation - real implementation needs auth
            await page.close()
            return {"status": "navigated", "prompt": prompt,
                    "note": "Google Video requires authentication"}
        except (OSError, RuntimeError, ValueError) as e:
            return {"error": str(e)}

    async def _opal(self, task: str, prompt: str) -> dict:
        """Automate Opal (opal.google)."""
        if self._pw is None:
            return {"error": "Playwright not available", "prompt": prompt}
        try:
            page = await self._pw.new_page()
            await page.goto("https://opal.google",
                            wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await page.close()
            return {"status": "navigated", "prompt": prompt,
                    "note": "Opal requires authentication"}
        except (OSError, RuntimeError, ValueError) as e:
            return {"error": str(e)}

    # ---- API Sources ----

    async def _gemini_api(self, task: str, prompt: str, **kwargs) -> dict:
        """Call Gemini API directly."""
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return {"error": "GEMINI_API_KEY not set"}
        try:
            import aiohttp
            url = ("https://generativelanguage.googleapis.com/v1beta/"
                   "models/gemini-pro:generateContent?key=" + api_key)
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.9, "maxOutputTokens": 2048},
            }
            async with aiohttp.ClientSession() as session, session.post(url, json=payload,
                                    headers={"Content-Type": "application/json"}) as resp:
                data = await resp.json()
                if "candidates" in data:
                    text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return {"text": text}
                return {"error": str(data)}
        except ImportError:
            return self._gemini_api_sync(task, prompt, **kwargs)
        except (OSError, ValueError, RuntimeError) as e:
            return {"error": str(e)}

    def _gemini_api_sync(self, task: str, prompt: str, **kwargs) -> dict:
        """Synchronous fallback for Gemini API."""
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return {"error": "GEMINI_API_KEY not set"}
        try:
            import urllib.request
            url = ("https://generativelanguage.googleapis.com/v1beta/"
                   "models/gemini-pro:generateContent?key=" + api_key)
            payload = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}],
            }).encode()
            req = urllib.request.Request(url, data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                if "candidates" in data:
                    return {"text": data["candidates"][0]["content"]["parts"][0]["text"]}
                return {"error": str(data)}
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            return {"error": str(e)}

    # ---- CLI Source ----

    async def _cli_exec(self, task: str, prompt: str, **kwargs) -> dict:
        """Execute a CLI command for generation."""
        # For CLI, prompt is expected to be a command string
        # or we build one from context
        cmd = kwargs.get("cmd", prompt)
        cwd = kwargs.get("cwd", str(OUTPUT))
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=300)
            return {
                "exit_code": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace")[:5000],
                "stderr": stderr.decode("utf-8", errors="replace")[:1000],
            }
        except asyncio.TimeoutError:
            return {"error": "CLI command timed out (300s)"}
        except (subprocess.SubprocessError, OSError) as e:
            return {"error": str(e)}

    def cli_sync(self, cmd: str, cwd: str | None = None,
                 timeout: int = 300) -> dict:
        """Synchronous CLI execution — 用 shlex.split 避免 shell 注入."""
        import shlex
        try:
            parts = shlex.split(cmd)
            result = subprocess.run(
                parts, capture_output=True, text=True,
                cwd=cwd or str(OUTPUT), timeout=timeout,
            )
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:1000],
            }
        except subprocess.TimeoutExpired:
            return {"error": "CLI command timed out"}
        except (subprocess.SubprocessError, OSError) as e:
            return {"error": str(e)}

# ======================================================================
# Quick helpers
# ======================================================================

def list_external_sources() -> dict:
    """Return all external source info."""
    return {k: {
        "name": v.name,
        "kind": v.kind,
        "description": v.description,
        "url": v.url,
        "enabled": v.enabled,
        "supports": v.supports,
    } for k, v in BUILTIN_SOURCES.items()}
