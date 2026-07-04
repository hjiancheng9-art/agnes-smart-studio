"""共享 test fixtures — pytest 自动发现。

提供跨测试文件的公共 setup，消除重复的 mock 工厂和 sys.path hack。
pythonpath=["."] 已在 pyproject.toml 的 [tool.pytest.ini_options] 中配置，
pytest 运行时自动把项目根加入 sys.path，无需各测试文件手动 sys.path.insert。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── 项目根目录 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# pytest pythonpath=["."] 应该已经把项目根加入了 sys.path，
# 但作为安全网再确认一次（向后兼容直接 python test_xxx.py 场景）。
_PROJECT_ROOT_STR = str(PROJECT_ROOT)
if _PROJECT_ROOT_STR not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT_STR)


# ── Provider 隔离 fixture ──
@pytest.fixture()
def clean_provider():
    """重置 provider 单例后返回新的 manager，用于需要干净 provider 状态的测试。

    test_smoke 等测试依赖 get_provider_manager() 返回值，但前面测试的
    import 链可能改变全局状态。在测试函数签名里声明此 fixture 即可隔离。
    """
    from core.provider import get_provider_manager, reset_provider_manager

    reset_provider_manager()
    return get_provider_manager()


# ── UI 测试公共 mock fixtures ──
# 以下 fixtures 消除 test_zcode_ui_input / _layout / _stream 中
# 三处重复定义的 _make_mock_session / _make_mock_cli。


@pytest.fixture()
def mock_session():
    """返回一个模拟 ChatSession（send_stream 返回空列表）。"""
    session = MagicMock()
    session.send_stream.return_value = []
    session.model = "test-model"
    session.history = []
    return session


@pytest.fixture()
def mock_cli(mock_session):
    """返回一个模拟 TUI 应用（Application），绑定 mock_session。"""
    cli = MagicMock()
    cli.session = mock_session
    return cli
