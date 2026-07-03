"""最小冒烟测试 — 验证 CRUX 核心模块可导入且基本功能正常。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_provider_import():
    from core.provider import get_provider_manager, MODEL_REGISTRY
    mgr = get_provider_manager()
    assert mgr.active_provider == "deepseek"
    assert len(MODEL_REGISTRY) == 7


def test_model_routing():
    from core.agent import ModelRouter
    r = ModelRouter()
    assert r.select_for_tier("light") == "deepseek-v4-flash"
    assert r.select_for_tier("pro") == "deepseek-v4-pro"
    assert r.select(task_type="image_generation") == "agnes-image-2.1-flash"


def test_audit():
    from core.self_audit import audit
    report = audit()
    assert isinstance(report, dict)
    assert "total_findings" in report


def test_lsp_available():
    from core.lsp import get_lsp_client, LSPClient
    client = get_lsp_client()
    assert isinstance(client, LSPClient)


def test_pytest_runner():
    from core.pytest_runner import run_pytest_safe, parse_test_summary
    p, f = parse_test_summary("3 passed in 0.10s")
    assert p == 3 and f == 0
