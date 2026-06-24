"""Startup health checks — catch config / tool / API issues before the conversation starts.

Philosophy: fail fast, fail loud. Every check returns (ok: bool, message: str).
Critical checks block startup; warnings are logged but don't block.

Covers:
- tools.json: JSON validity, format-string conflicts, parameter consistency
- models.json: structure, provider URLs, model IDs
- Environment: API keys present, base URLs reachable
- Output dirs: exist and writable
- Dependencies: key packages importable
"""

import json
import os
import re
from pathlib import Path

__all__ = [
    'ROOT',
    'critical_failures', 'print_report', 'run_all', 'wait_for_provider',
]

ROOT = Path(__file__).resolve().parent.parent

# ── Rich theme (single source of truth) ──────────────────────────
from ui.theme import COLORS, console

_results: list[tuple[str, bool, str]] = []

def _add(category: str, ok: bool, msg: str):
    _results.append((category, ok, msg))

def run_all() -> list[tuple[str, bool, str]]:
    """Run all startup checks. Returns list of (category, ok, message)."""
    _results.clear()
    _check_env()
    _check_deps()
    _check_output_dirs()
    _check_models_config()
    _check_tools_config()
    _check_api_connectivity()
    _check_provider_liveness()
    _check_local_llm()
    return list(_results)

def print_report(results: list[tuple[str, bool, str]], show_ok: bool = False):
    """Pretty-print a health check report to the terminal."""
    for category, ok, msg in results:
        if ok and not show_ok:
            continue
        icon = f"[{COLORS['success']}]OK[/]" if ok else f"[{COLORS['error']}]FAIL[/]"
        console.print(f"  [{icon}] [{COLORS['muted']}]{category}[/]: {msg}")

def critical_failures(results: list[tuple[str, bool, str]]) -> list[str]:
    """Return list of failure messages that should block startup."""
    return [msg for cat, ok, msg in results if not ok and cat in (
        "env", "deps", "tools.json"
    )]

def _check_provider_liveness():
    """Verify the active model provider is reachable with a lightweight probe.

    Uses httpx to send a GET /v1/models (OpenAI-compatible) with a short timeout.
    Falls back silently on failure; does not block startup.
    """
    try:
        import httpx

        from core.provider import get_provider_manager
    except ImportError as e:
        _add("provider", False, f"Import error: {e}")
        return
    active: str = ""
    try:
        mgr = get_provider_manager()
        mgr.load()
        active = mgr.state.active
        if active not in mgr.providers:
            _add("provider", False, f"Active provider '{active}' not in providers config")
            return
        cfg = mgr.providers[active]
        base_url = cfg.get("base_url", "")
        if not base_url:
            _add("provider", False, f"Provider '{active}' has no base_url")
            return
        # Strip /v1 suffix for models endpoint
        models_url = base_url.rstrip("/") + "/models"
        with httpx.Client(trust_env=False, timeout=5.0) as client:
            r = client.get(models_url)
            if r.status_code in (200, 401, 403):
                # 200 = open endpoint, 401/403 = reachable but needs auth (fine)
                _add("provider", True,
                     f"Provider '{active}' ({cfg['name']}) reachable at {base_url}")
            else:
                _add("provider", False,
                     f"Provider '{active}' returned HTTP {r.status_code} from {base_url}")
    except httpx.ConnectError:
        _add("provider", False,
             f"Provider '{active}' unreachable — connection refused")
    except httpx.TimeoutException:
        _add("provider", False,
             f"Provider '{active}' unreachable — connection timed out")
    except (httpx.HTTPError, OSError) as e:
        _add("provider", False, f"Provider check failed: {e}")


def wait_for_provider(base_url: str, timeout: float = 60.0,
                      interval: float = 2.0) -> tuple[bool, str]:
    """轮询等待 OpenAI 兼容端点就绪。

    llama-server 启动后加载 GGUF 模型需要 10-30s（取决于模型大小 / NVMe 速度），
    这期间 HTTP 端口可能已开但 /v1/models 还没响应。本函数封装"轮询直到就绪"逻辑，
    复用 `_check_provider_liveness` 的探测内核（裸 GET /models, trust_env=False）。

    Returns: (ok, message)
    """
    import time

    import httpx

    url = base_url.rstrip("/") + "/models"
    deadline = time.time() + timeout
    last_err = ""
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=5.0, trust_env=False)
            if r.status_code in (200, 401, 403):
                return True, f"ready (HTTP {r.status_code})"
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_err = f"{type(e).__name__}: {e}"
        except (httpx.HTTPError, OSError) as e:
            last_err = f"{type(e).__name__}: {e}"
        time.sleep(interval)
    return False, last_err or f"timeout after {timeout:.0f}s"


def _check_local_llm():
    """Probe the local llama.cpp provider (regardless of whether it is active).

    Unlike `_check_provider_liveness` (which only probes the active provider),
    this always checks the `local` entry so users can see at startup whether
    the本地模型 is running — without making it the default. 非阻断（category 不在
    critical_failures 列表里），仅 advisory。
    """
    try:
        from core.provider import get_provider_manager
    except ImportError as e:
        _add("local_llm", False, f"Import error: {e}")
        return
    try:
        mgr = get_provider_manager()
        mgr.load()
        cfg = mgr.providers.get("local")
        if not cfg:
            # 没配 local provider 是合法状态（用户可能没装本地模型），静默跳过
            return
        base_url = cfg.get("base_url", "")
        if not base_url:
            _add("local_llm", False, "local provider 配置缺 base_url")
            return
        ok, msg = wait_for_provider(base_url, timeout=5.0, interval=1.0)
        if ok:
            _add("local_llm", True,
                 f"本地模型 {cfg.get('name', 'local')} 就绪 @ {base_url}")
        else:
            _add("local_llm", False,
                 f"本地模型未启动 ({msg}) — 双击 llama.cpp/launch-qwen3.6.bat 启动后可用")
    except (OSError, ValueError) as e:
        _add("local_llm", False, f"local check failed: {e}")

# ══════════════════════════════════════════════════════════════════════
# Individual checks
# ══════════════════════════════════════════════════════════════════════

def _check_env():
    """Verify .env exists and API key is set."""
    from core.config import SETTINGS
    env_file = ROOT / ".env"

    if not env_file.exists():
        _add("env", False, ".env file missing — copy .env.example and fill in CRUX_API_KEY")
        return

    if not SETTINGS.api_key:
        _add("env", False, "CRUX_API_KEY not set in .env")
        return
    if "sk-your-api-key" in SETTINGS.api_key or len(SETTINGS.api_key) < 10:
        _add("env", False, "CRUX_API_KEY looks like a placeholder — replace with real key")
        return

    _add("env", True, f"CRUX_API_KEY=...{SETTINGS.api_key[-8:]}")

def _check_deps():
    """Verify essential packages are importable."""
    essential = {
        "httpx": "HTTP client",
        "rich": "Terminal UI",
        "PIL": "Image processing (Pillow)",
        "dotenv": "Env file loading (python-dotenv)",
    }
    missing = []
    for mod, desc in essential.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"{mod} ({desc})")

    if missing:
        _add("deps", False, f"Missing packages: {', '.join(missing)}. Run: pip install -r requirements.txt")
    else:
        _add("deps", True, f"{len(essential)} essential packages OK")

def _check_output_dirs():
    """Verify output directories exist and are writable."""
    from core.config import OUTPUT_DIR
    dirs = [
        OUTPUT_DIR,
        OUTPUT_DIR / "images",
        OUTPUT_DIR / "videos",
    ]
    for d in dirs:
        try:
            d.mkdir(exist_ok=True)
            test_file = d / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
        except (OSError, UnicodeDecodeError) as e:
            _add("output", False, f"Cannot write to {d}: {e}")
            return
    _add("output", True, f"Output dirs OK ({OUTPUT_DIR})")

def _check_models_config():
    """Validate models.json structure, provider URLs, and active provider."""
    cfg_path = ROOT / "models.json"
    if not cfg_path.exists():
        _add("models.json", False, "models.json not found")
        return

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _add("models.json", False, f"Invalid JSON: {e}")
        return

    providers = cfg.get("providers", {})
    active = cfg.get("active", "")

    if not providers:
        _add("models.json", False, "No providers defined")
        return

    issues = []
    for pid, p in providers.items():
        if not p.get("base_url", "").startswith("http"):
            issues.append(f"{pid}: invalid base_url")
        if not p.get("models"):
            issues.append(f"{pid}: no models defined")

    if active and active not in providers:
        issues.append(f"active='{active}' not in providers (available: {list(providers.keys())})")

    if issues:
        _add("models.json", False, "; ".join(issues))
        return

    # Check active provider has required keys
    active_provider = providers.get(active, {})
    key_env = f"{active.upper()}_API_KEY"
    api_key = active_provider.get("api_key") or os.getenv(key_env, "")
    if not api_key:
        _add("models.json", True, f"OK ({len(providers)} providers, active={active}, no API key for {active} — will prompt)")
    else:
        _add("models.json", True, f"OK ({len(providers)} providers, active={active})")

def _check_tools_config():
    """Validate tools.json: JSON validity, shell command format strings, parameter consistency."""
    cfg_path = ROOT / "tools.json"
    if not cfg_path.exists():
        _add("tools.json", False, "tools.json not found")
        return

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _add("tools.json", False, f"Invalid JSON: {e}")
        return

    tools = cfg.get("tools", [])
    if not tools:
        _add("tools.json", False, "No tools defined in tools.json")
        return

    broken = []
    for tool in tools:
        name = tool.get("name", "?")
        cmd = tool.get("command", "")
        params = tool.get("parameters", {})
        param_names = set(params.keys())

        # Find all {identifier}-style placeholders in the command
        placeholders = set(re.findall(r"\{([a-zA-Z_]\w*)\}", cmd))
        unexpected = placeholders - param_names

        if unexpected:
            broken.append(f"{name}: unexpected {{{', '.join(sorted(unexpected))}}} in command")

    if broken:
        _add("tools.json", False,
             f"{len(broken)} tool(s) have format-string conflicts: {'; '.join(broken)}")
    else:
        _add("tools.json", True, f"OK ({len(tools)} tools, no format-string conflicts)")

def _check_api_connectivity():
    """Quick check that the CRUX API is reachable."""
    import httpx

    from core.config import SETTINGS

    try:
        r = httpx.get(
            SETTINGS.base_url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {SETTINGS.api_key}"},
            timeout=10,
        )
        if r.status_code == 200:
            models = r.json().get("data", [])
            model_ids = [m["id"] for m in models]
            _add("api", True, f"CRUX API reachable ({len(models)} models: {', '.join(model_ids[:4])})")
        elif r.status_code == 401:
            _add("api", False, "CRUX API: 401 Unauthorized — check CRUX_API_KEY")
        else:
            _add("api", False, f"CRUX API: HTTP {r.status_code}")
    except (httpx.HTTPError, OSError) as e:
        msg = str(e)[:100]
        _add("api", False, f"CRUX API unreachable: {msg}")

# ══════════════════════════════════════════════════════════════════════
# Quick standalone run: python core/startup_checks.py
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    results = run_all()
    print_report(results, show_ok=True)
    failures = [msg for _, ok, msg in results if not ok]
    if failures:
        console.print(f"\n[{COLORS['error']}]{len(failures)} check(s) failed[/]")
        sys.exit(1)
    else:
        console.print(f"\n[{COLORS['success']}]All checks passed[/]")
