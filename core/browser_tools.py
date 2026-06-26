"""Browser Companion — 全自动网页生图生视频

⚠ EXPERIMENTAL — 未接通 runtime：本模块仅被 tests/manual 引用，
ChatSession/tools.json 尚未注册。Playwright 自动化逻辑完整但需接入后才生效。

CRUX 大脑：选择 provider、生成 prompt、决定策略
Playwright：打开网页、填入提示词、点击生成、轮询结果、下载文件
API Provider：有官方API的直接调用（更快更稳定）

架构：
  Provider 层 → 8 个适配器（API 优先，Playwright 后备）
  Session 层 → 浏览器登录态管理
  Task 层 → 任务生命周期 + 持久化

覆盖 8 个在线服务：
  可灵 Kling  |  即梦 Jimeng  |  Runway  |  Luma
  DALL-E       |  Gemini       |  Opal    |  Veo/Flow
"""

import contextlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

__all__ = [
    "BROWSER_EXECUTOR_MAP",
    "BROWSER_TOOL_DEFS",
    "OUTPUT_ROOT",
    "PROVIDER_CONFIGS",
    "SESSION_DIR",
    "TASK_FILE",
    "execute_browser_cancel",
    "execute_browser_check",
    "execute_browser_download",
    "execute_browser_generate",
    "execute_browser_providers",
    "execute_browser_setup",
    "reset_browser_tools",
]

# ── 输出目录 ──
OUTPUT_ROOT = Path(__file__).parent.parent / "output"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
SESSION_DIR = OUTPUT_ROOT / "browser_sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)
TASK_FILE = OUTPUT_ROOT / "browser_tasks.json"


# ── subprocess 安全封装 ──
def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    # 默认 60s 超时兜底：外部命令（chromium/playwright 等）卡住不会永久阻塞主进程
    kwargs.setdefault("timeout", 60)
    return subprocess.run(cmd, **kwargs)


# ============================================================
#  Provider 配置
# ============================================================

PROVIDER_CONFIGS = {
    "kling": {
        "name": "可灵 Kling",
        "url": "https://klingai.com",
        "has_api": True,
        "type": "video",
        "api_doc": "https://platform.klingai.com/docs",
        "env_key": "KLING_API_KEY",
    },
    "jimeng": {
        "name": "即梦 Jimeng",
        "url": "https://jimeng.jianying.com",
        "has_api": True,
        "type": "image_video",
        "api_doc": "https://www.volcengine.com/docs/6791",
        "env_key": "JIMENG_API_KEY",
    },
    "runway": {
        "name": "Runway",
        "url": "https://runwayml.com",
        "has_api": True,
        "type": "video",
        "api_doc": "https://docs.runwayml.com",
        "env_key": "RUNWAY_API_KEY",
    },
    "luma": {
        "name": "Luma",
        "url": "https://lumalabs.ai",
        "has_api": True,
        "type": "video",
        "api_doc": "https://docs.lumalabs.ai",
        "env_key": "LUMA_API_KEY",
    },
    "dalle": {
        "name": "ChatGPT DALL-E",
        "url": "https://chat.openai.com",
        "has_api": True,
        "type": "image",
        "api_doc": "https://platform.openai.com/docs",
        "env_key": "OPENAI_API_KEY",
        "alias": "openai",
    },
    "gemini": {
        "name": "Gemini",
        "url": "https://gemini.google.com",
        "has_api": True,
        "type": "image_video",
        "api_doc": "https://ai.google.dev",
        "env_key": "GEMINI_API_KEY",
    },
    "opal": {
        "name": "Google Opal",
        "url": "https://opal.withgoogle.com",
        "has_api": False,
        "type": "video",
    },
    "veo": {
        "name": "Veo / Flow",
        "url": "https://labs.google/fx",
        "has_api": False,
        "type": "video",
    },
}

# ============================================================
#  任务持久化
# ============================================================


def _load_tasks() -> list[dict]:
    if TASK_FILE.exists():
        try:
            return json.loads(TASK_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _save_tasks(tasks: list[dict]):
    TASK_FILE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_task(task_id: str) -> dict | None:
    tasks = _load_tasks()
    for t in tasks:
        if t["task_id"] == task_id:
            return t
    return None


def _update_task(task_id: str, updates: dict):
    tasks = _load_tasks()
    for i, t in enumerate(tasks):
        if t["task_id"] == task_id:
            tasks[i].update(updates)
            tasks[i]["updated_at"] = time.time()
            _save_tasks(tasks)
            return tasks[i]
    return None


# ============================================================
#  Playwright Session 管理 — 自带 Chromium + 持久化登录态
# ============================================================

# ── 事件循环兼容已在 crux_studio.py / launcher.py 入口统一处理 ──
# 此处不再重复调用 nest_asyncio.apply()

# 模块级延迟导入
_playwright_module = None
_active_playwright = None
_active_browsers: dict[str, object] = {}
_chromium_checked = False


def _get_playwright():
    global _playwright_module
    if _playwright_module is None:
        try:
            from playwright.sync_api import sync_playwright

            _playwright_module = sync_playwright
        except ImportError:
            return None
    return _playwright_module


def _ensure_chromium():
    """确保 Playwright Chromium 已安装"""
    global _chromium_checked
    if _chromium_checked:
        return None
    _chromium_checked = True
    try:
        r = subprocess.run(
            ["playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            return f"Chromium 安装失败: {r.stderr[-200:]}"
    except FileNotFoundError:
        return "playwright 未安装，请运行: pip install playwright"
    except subprocess.TimeoutExpired:
        return "Chromium 安装超时，请手动运行: playwright install chromium"
    return None


def _get_browser_context(provider_id: str):
    """获取持久化浏览器上下文（自带 Chromium，保持登录态）"""
    global _active_playwright, _active_browsers

    pw = _get_playwright()
    if not pw:
        return None, None, "playwright 未安装，请运行: pip install playwright"

    # 确保 Chromium 已安装
    err = _ensure_chromium()
    if err:
        return None, None, err

    # 复用已有浏览器上下文
    if provider_id in _active_browsers:
        return _active_playwright, _active_browsers[provider_id], None

    user_data_dir = SESSION_DIR / provider_id
    user_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        playwright = pw().start()
        browser = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        _active_playwright = playwright
        _active_browsers[provider_id] = browser
        return playwright, browser, None
    except (AttributeError, TypeError) as e:
        return None, None, f"浏览器启动失败: {e}"


def reset_browser_tools() -> None:
    """Tear down all persistent browser contexts (test isolation / hot reload).

    browser_tools holds one Playwright BrowserContext per provider (each a
    real visible Chromium subprocess with its own user_data_dir). Failing to
    close them leaks Chromium processes across test runs. Each context is
    closed best-effort, then the Playwright driver is stopped and the module
    globals are reset to their import-time state.
    """
    global _active_playwright, _active_browsers, _chromium_checked
    for ctx in list(_active_browsers.values()):
        with contextlib.suppress(Exception):
            ctx.close()  # type: ignore[union-attr]
    _active_browsers.clear()
    if _active_playwright is not None:
        with contextlib.suppress(Exception):
            _active_playwright.stop()  # type: ignore[union-attr]
    _active_playwright = None
    _chromium_checked = False


# ============================================================
#  Playwright 通用操作
# ============================================================


def _playwright_generate(
    provider_id: str, prompt: str, image_path: str = "", config: dict | None = None, timeout_minutes: int = 15
) -> str:
    """用 Playwright 在网页上自动提交生成任务"""
    config = config or {}
    provider = PROVIDER_CONFIGS.get(provider_id)
    if not provider:
        return json.dumps({"success": False, "error": f"未知 provider: {provider_id}"}, ensure_ascii=False)

    pw, ctx, err = _get_browser_context(provider_id)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if not ctx:
        return json.dumps({"success": False, "error": "无法创建浏览器"}, ensure_ascii=False)

    page = None
    timeout_ms = timeout_minutes * 60 * 1000
    ctx.set_default_timeout(timeout_ms)  # type: ignore[attribute-access]  # Playwright BrowserContext at runtime

    try:
        page = ctx.new_page()  # type: ignore[attribute-access]
        provider_url = provider["url"]
        page.goto(provider_url, wait_until="domcontentloaded")

        # ── 通用策略：查找输入框并填入 prompt ──
        # 大多数平台的 prompt 输入框特征
        selectors_to_try = [
            'textarea[placeholder*="prompt" i]',
            'textarea[placeholder*="描述" i]',
            'textarea[placeholder*="输入" i]',
            'textarea[aria-label*="prompt" i]',
            '[contenteditable="true"]',
            'textarea:not([style*="display: none"])',
        ]

        filled = False
        for sel in selectors_to_try:
            try:
                el = page.wait_for_selector(sel, timeout=10000)
                if el:
                    el.click()
                    el.fill(prompt)
                    filled = True
                    break
            except (OSError, RuntimeError, ValueError):
                continue

        if not filled:
            return json.dumps(
                {
                    "success": False,
                    "error": f"无法在 {provider['name']} 上找到输入框。请用 browser_setup 手动登录并确认网站结构。",
                    "hint": f"访问 {provider_url} 确认页面布局",
                },
                ensure_ascii=False,
            )

        # ── 如果有参考图，尝试上传 ──
        if image_path and Path(image_path).exists():
            try:
                file_input = page.locator('input[type="file"]').first
                file_input.set_input_files(image_path)
                time.sleep(2)
            except (json.JSONDecodeError, TypeError, KeyError):
                pass  # 图片上传失败不阻断，继续尝试文字生成

        # ── 点击生成按钮 ──
        gen_selectors = [
            'button:has-text("生成")',
            'button:has-text("Generate")',
            'button:has-text("Create")',
            'button:has-text("Submit")',
            '[aria-label*="生成" i]',
            '[aria-label*="generate" i]',
        ]

        clicked = False
        for sel in gen_selectors:
            try:
                btn = page.wait_for_selector(sel, timeout=5000)
                if btn and btn.is_enabled():
                    btn.click()
                    clicked = True
                    time.sleep(3)
                    break
            except (OSError, RuntimeError, ValueError):
                continue

        if not clicked:
            return json.dumps(
                {
                    "success": False,
                    "error": "已填入提示词但未找到生成按钮。请用 browser_setup 完成首次配置。",
                    "hint": f"在 {provider_url} 上手动点一次生成，之后 CRUX 可记住按钮位置",
                },
                ensure_ascii=False,
            )

        # ── 轮询等待结果 ──
        result_selectors = [
            "video source",
            "video",
            'img[src*="output"]',
            'img[src*="result"]',
            'img[src*="generated"]',
            '[data-testid="result"] img',
            ".result-container img",
        ]

        result_url = None
        poll_start = time.time()
        while time.time() - poll_start < timeout_minutes * 60:
            for sel in result_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        src = el.get_attribute("src")
                        if src and src.startswith("http"):
                            result_url = src
                            break
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
            if result_url:
                break
            time.sleep(5)

        if not result_url:
            return json.dumps(
                {
                    "success": False,
                    "error": f"等待 {timeout_minutes} 分钟后未检测到生成结果。请检查 {provider_url} 页面状态。",
                    "hint": "生成可能仍在进行中，或网站结构有变化。手动登录确认。",
                },
                ensure_ascii=False,
            )

        # ── 下载结果 ──
        import urllib.request

        output_dir = OUTPUT_ROOT / "browser_output" / provider_id
        output_dir.mkdir(parents=True, exist_ok=True)
        ext = ".mp4" if provider["type"] in ("video", "image_video") else ".png"
        output_path = output_dir / f"{uuid.uuid4().hex[:8]}{ext}"

        urllib.request.urlretrieve(result_url, str(output_path))

        return json.dumps(
            {
                "success": True,
                "provider": provider_id,
                "provider_name": provider["name"],
                "method": "playwright",
                "output_path": str(output_path),
                "url": result_url,
                "prompt": prompt[:200],
            },
            ensure_ascii=False,
        )

    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"success": False, "error": f"Playwright 错误: {e}"}, ensure_ascii=False)
    finally:
        try:
            if page:
                page.close()
        except (json.JSONDecodeError, TypeError, KeyError):
            pass


# ============================================================
#  API Provider（优先路径）
# ============================================================


def _api_generate(provider_id: str, prompt: str, image_path: str = "", config: dict | None = None) -> str:
    """通过官方 API 提交生成任务。返回 task_id 用于轮询。"""
    config = config or {}
    provider = PROVIDER_CONFIGS.get(provider_id, {})

    if provider_id == "dalle":
        return _dalle_generate(prompt, image_path, config)
    elif provider_id == "gemini":
        return _gemini_generate(prompt, image_path, config)
    # Kling / Runway / Luma / Jimeng：优先 API（需用户配置 key），无 API key 时降级 Playwright
    api_key = os.environ.get(provider.get("env_key", ""))
    if not api_key:
        return json.dumps(
            {
                "success": False,
                "fallback": "playwright",
                "error": f"未配置 {provider.get('env_key', provider_id.upper() + '_API_KEY')} 环境变量，降级到 Playwright",
            },
            ensure_ascii=False,
        )

    # 通用 API 调用框架（各 provider API 格式不同，此为骨架）
    return json.dumps(
        {
            "success": False,
            "error": f"{provider['name']} API 集成待完善。请先用 Playwright 方案。",
            "hint": f"设置 {provider.get('env_key', '')} 环境变量后重试",
        },
        ensure_ascii=False,
    )


def _dalle_generate(prompt: str, image_path: str = "", config: dict | None = None) -> str:
    """OpenAI DALL-E API"""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return json.dumps(
            {"success": False, "fallback": "playwright", "error": "未配置 OPENAI_API_KEY，降级到 Playwright"},
            ensure_ascii=False,
        )

    import urllib.request

    cfg = config or {}
    body = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": cfg.get("size", "1024x1024"),
        "quality": cfg.get("quality", "standard"),
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
        url = resp["data"][0]["url"]
        # 下载到本地
        output_dir = OUTPUT_ROOT / "browser_output" / "dalle"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"dalle_{uuid.uuid4().hex[:8]}.png"
        urllib.request.urlretrieve(url, str(output_path))
        return json.dumps(
            {
                "success": True,
                "provider": "dalle",
                "method": "api",
                "output_path": str(output_path),
                "url": url,
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"success": False, "error": f"DALL-E API 错误: {e}"}, ensure_ascii=False)


def _gemini_generate(prompt: str, image_path: str = "", config: dict | None = None) -> str:
    """Google Gemini API (imagen)"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return json.dumps(
            {"success": False, "fallback": "playwright", "error": "未配置 GEMINI_API_KEY，降级到 Playwright"},
            ensure_ascii=False,
        )

    # Gemini Imagen API
    import urllib.request

    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1},
    }
    req = urllib.request.Request(
        "https://us-central1-aiplatform.googleapis.com/v1/projects/YOUR_PROJECT/locations/us-central1/publishers/google/models/imagen:predict",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
        return json.dumps(
            {
                "success": True,
                "provider": "gemini",
                "method": "api",
                "raw_response": resp,
                "hint": "Gemini Imagen 结果需解析 predictions 字段，按 base64 图片解码保存",
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"success": False, "error": f"Gemini API 错误: {e}"}, ensure_ascii=False)


# ============================================================
#  工具执行器
# ============================================================


def execute_browser_generate(provider: str, prompt: str, image_path: str = "", config: str = "{}") -> str:
    """browser_generate 工具：提交生成任务到指定 Web 服务"""
    if provider not in PROVIDER_CONFIGS:
        return json.dumps(
            {
                "success": False,
                "error": f"未知 provider: {provider}",
                "available": list(PROVIDER_CONFIGS.keys()),
            },
            ensure_ascii=False,
        )

    try:
        cfg = json.loads(config) if isinstance(config, str) else (config or {})
    except json.JSONDecodeError:
        cfg = {}

    pcfg = PROVIDER_CONFIGS[provider]

    # 1. 尝试 API 优先
    if pcfg.get("has_api"):
        result = _api_generate(provider, prompt, image_path, cfg)
        data = json.loads(result)
        if data.get("success"):
            return result
        if data.get("fallback") != "playwright":
            return result  # 真正的 API 错误，不降级

    # 2. Playwright 后备
    return _playwright_generate(provider, prompt, image_path, cfg)


def execute_browser_check(task_id: str) -> str:
    """browser_check 工具：查询任务状态"""
    task = _find_task(task_id)
    if not task:
        return json.dumps({"error": f"任务不存在: {task_id}", "success": False}, ensure_ascii=False)
    return json.dumps(task, ensure_ascii=False)


def execute_browser_download(task_id: str) -> str:
    """browser_download 工具：下载已完成任务的结果"""
    task = _find_task(task_id)
    if not task:
        return json.dumps({"error": f"任务不存在: {task_id}", "success": False}, ensure_ascii=False)
    if task.get("status") != "completed":
        return json.dumps(
            {
                "success": False,
                "error": f"任务状态为 {task.get('status')}，不是 completed",
                "task": task,
            },
            ensure_ascii=False,
        )

    output_path = task.get("output_path", "")
    if output_path and Path(output_path).exists():
        return json.dumps(
            {
                "success": True,
                "task_id": task_id,
                "output_path": output_path,
                "file_size": Path(output_path).stat().st_size,
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "success": False,
            "error": "输出文件不存在，可能需要重新下载",
            "task": task,
        },
        ensure_ascii=False,
    )


def execute_browser_providers() -> str:
    """browser_providers 工具：列出所有可用 Web 服务"""
    providers = []
    for pid, pcfg in PROVIDER_CONFIGS.items():
        api_ok = False
        if pcfg.get("has_api") and pcfg.get("env_key"):
            api_ok = bool(os.environ.get(pcfg["env_key"], ""))
        providers.append(
            {
                "id": pid,
                "name": pcfg["name"],
                "url": pcfg["url"],
                "type": pcfg["type"],
                "api_available": api_ok,
                "playwright_available": True,
            }
        )
    return json.dumps({"providers": providers, "total": len(providers)}, ensure_ascii=False)


def execute_browser_setup(provider: str) -> str:
    """browser_setup 工具：打开浏览器让用户登录"""
    if provider not in PROVIDER_CONFIGS:
        return json.dumps(
            {"success": False, "error": f"未知 provider: {provider}", "available": list(PROVIDER_CONFIGS.keys())},
            ensure_ascii=False,
        )

    pcfg = PROVIDER_CONFIGS[provider]
    pw, ctx, err = _get_browser_context(provider)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)

    page = None
    try:
        page = ctx.new_page()  # type: ignore[attribute-access]
        page.goto(pcfg["url"])
        return json.dumps(
            {
                "success": True,
                "message": f"已打开 {pcfg['name']} 登录页。在浏览器窗口登录后关闭该标签页即可，session 自动保存。",
                "provider": provider,
                "url": pcfg["url"],
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def execute_browser_cancel(task_id: str) -> str:
    """browser_cancel 工具：取消进行中的任务"""
    updated = _update_task(task_id, {"status": "cancelled"})
    if not updated:
        return json.dumps({"error": f"任务不存在: {task_id}", "success": False}, ensure_ascii=False)
    return json.dumps({"success": True, "task_id": task_id, "status": "cancelled"}, ensure_ascii=False)


# ============================================================
#  工具定义（供 tools.py 注册）
# ============================================================

BROWSER_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "browser_generate",
            "description": "在网页平台（可灵/即梦/Runway/Luma/DALL-E/Gemini/Opal/Veo）上全自动生成图片或视频。优先用官方API，无API时用Playwright浏览器自动化。首次使用某个平台需先 browser_setup 登录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "description": "目标平台ID: kling/jimeng/runway/luma/dalle/gemini/opal/veo",
                        "enum": list(PROVIDER_CONFIGS.keys()),
                    },
                    "prompt": {"type": "string", "description": "生成提示词"},
                    "image_path": {"type": "string", "description": "可选，参考图片路径（图生视频/图生图）"},
                    "config": {"type": "string", "description": "可选，额外配置JSON（如size/quality/duration）"},
                },
                "required": ["provider", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_check",
            "description": "查询浏览器生成任务的当前状态和结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_download",
            "description": "下载浏览器生成任务的完成结果文件到本地。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_providers",
            "description": "列出所有可用的网页生成平台及状态。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_setup",
            "description": "打开浏览器让用户首次登录指定平台。登录后关闭浏览器窗口即可，session自动保存。下次browser_generate可自动复用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "description": "要登录的平台ID",
                        "enum": list(PROVIDER_CONFIGS.keys()),
                    },
                },
                "required": ["provider"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_cancel",
            "description": "取消正在进行的浏览器生成任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务ID"},
                },
                "required": ["task_id"],
            },
        },
    },
]

# ── 执行器映射 ──
BROWSER_EXECUTOR_MAP = {
    "browser_generate": lambda **kw: execute_browser_generate(
        provider=kw.get("provider", ""),
        prompt=kw.get("prompt", ""),
        image_path=kw.get("image_path", ""),
        config=kw.get("config", "{}"),
    ),
    "browser_check": lambda **kw: execute_browser_check(task_id=kw.get("task_id", "")),
    "browser_download": lambda **kw: execute_browser_download(task_id=kw.get("task_id", "")),
    "browser_providers": lambda **kw: execute_browser_providers(),
    "browser_setup": lambda **kw: execute_browser_setup(provider=kw.get("provider", "")),
    "browser_cancel": lambda **kw: execute_browser_cancel(task_id=kw.get("task_id", "")),
}
