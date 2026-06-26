import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)


@pytest.fixture(autouse=True)
def _reset_global_singletons():
    """Reset CRUX global singletons before each test for isolation.

    Many core modules expose a ``get_*()`` lazy singleton backed by a module
    level ``_xxx`` variable. Without reset, state (registered hooks, MCP/LSP
    child processes, daemon flag, event handlers) leaks across tests and can
    also leave orphan subprocesses behind. Each reset function is optional:
    if a module fails to import (optional dependency missing) we skip it.
    """
    yield

    # ── post-test cleanup (after yield so both setup-failures and test body
    #    exceptions still trigger teardown) ──────────────────────────────────
    # Each reset is isolated: a failure in one must not block the others.
    _safe_clear("core.event_bus", "bus", "clear")
    _safe_reset("core.hooks", "reset_hook_manager")
    _safe_reset("core.lsp", "reset_lsp_client")
    _safe_reset("core.mcp_client", "reset_mcp_client")
    _safe_reset("core.daemon", "reset_daemon")
    # prompt_lab carries a session and user memory — reset it too.
    _safe_reset("core.prompt_lab", "reset_prompt_lab")
    # Reflection engine singleton (independent of hooks).
    _safe_reset("core.hooks", "reset_reflection_engine")
    # Tool registry singleton.
    _safe_reset("core.tools", "reload_registry")
    # ── orchestration / capability singletons (in-memory dicts) ──
    _safe_reset("core.orchestra", "reset_orchestra")
    _safe_reset("core.provider", "reset_provider_manager")
    _safe_reset("core.rules", "reset_rules")
    _safe_reset("core.marketplace", "reset_marketplace")
    _safe_reset("core.skills", "reset_skill_manager")
    # ── thread-bearing singletons (ordered teardown before nulling) ──
    _safe_reset("core.scheduler", "reset_scheduler")
    _safe_reset("core.watchdog", "reset_watchdog")
    # ── eagerly-instantiated singletons (reset internal state in place) ──
    _safe_reset("core.semantic_memory", "reset_memory")
    _safe_reset("core.observability", "reset_observability")
    _safe_reset("core.capability_registry", "reset_capability_registry")
    # ── browser singletons (Playwright / Chromium subprocesses) ──
    _safe_reset("core.web_browser", "reset_web_browser")
    _safe_reset("core.browser_tools", "reset_browser_tools")


def _safe_clear(module_name: str, attr: str, method: str) -> None:
    """Call ``<module>.<attr>.<method>()`` swallowing ImportError/AttributeError."""
    try:
        mod = __import__(module_name, fromlist=[attr])
        obj = getattr(mod, attr)
        getattr(obj, method)()
    except (ImportError, AttributeError):
        pass
    except Exception:  # noqa: BLE001 — best-effort teardown, never fail the test
        pass


def _safe_reset(module_name: str, func_name: str) -> None:
    """Call ``<module>.<func_name>()`` swallowing ImportError/AttributeError."""
    try:
        mod = __import__(module_name, fromlist=[func_name])
        getattr(mod, func_name)()
    except (ImportError, AttributeError):
        pass
    except Exception:  # noqa: BLE001 — best-effort teardown, never fail the test
        pass
