"""最小冒烟测试 — 验证 CRUX 核心模块可导入且基本功能正常。

注意：这些测试依赖 provider 全局单例状态，前面测试文件若修改了
MODEL_REGISTRY 或 active_provider 会导致断言失败。reset_provider_manager()
在 import 前调用确保隔离。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_provider_import():
    from core.provider import MODEL_REGISTRY, get_provider_manager, reset_provider_manager
    reset_provider_manager()  # 隔离：清除前面测试可能的污染
    mgr = get_provider_manager()
    assert mgr.active_provider in ("deepseek", "crux"), f"unexpected active provider: {mgr.active_provider}"
    assert len(MODEL_REGISTRY) >= 6, f"MODEL_REGISTRY too small: {len(MODEL_REGISTRY)}"


def test_model_routing():
    from core.agent import ModelRouter
    r = ModelRouter()
    light = r.select_for_tier("light")
    pro = r.select_for_tier("pro")
    assert light is not None, "select_for_tier('light') returned None"
    assert pro is not None, "select_for_tier('pro') returned None"
    assert r.select(task_type="image_generation") is not None, "select(image_generation) returned None"


def test_audit():
    from core.self_audit import audit
    report = audit()
    assert isinstance(report, dict)
    assert "total_findings" in report


def test_lsp_available():
    from core.lsp import LSPClient, get_lsp_client
    client = get_lsp_client()
    assert isinstance(client, LSPClient)


def test_pytest_runner():
    from core.pytest_runner import parse_test_summary
    p, f = parse_test_summary("3 passed in 0.10s")
    assert p == 3 and f == 0
