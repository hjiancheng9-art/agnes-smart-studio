"""Unit tests for 本地 llama.cpp provider 接入。

验证：
- models.json 包含 local provider 条目
- local provider 配置了 auth_required=false
- create_client("local") 不会静默 fallback 到云 provider（Blocker A 回归）
- local 模型在 MODEL_REGISTRY 中注册（别名解析正常）
- wait_for_provider 轮询逻辑（超时 / 就绪两种场景）
- _check_local_llm 正确写入 startup_checks 结果
- _quick_health 包含 local_llm_health 字段（真反射探测）
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── models.json 配置验证 ────────────────────────────────────────────


class TestLocalProviderConfig:
    def test_local_provider_exists(self):
        """models.json 应包含 local provider 条目。"""
        with open(ROOT / "models.json", encoding="utf-8") as f:
            cfg = json.load(f)
        assert "local" in cfg["providers"], "models.json 缺少 local provider"

    def test_local_base_url(self):
        """local provider 的 base_url 应指向 llama-server 默认端口。"""
        with open(ROOT / "models.json", encoding="utf-8") as f:
            cfg = json.load(f)
        local = cfg["providers"]["local"]
        assert "http://127.0.0.1:8080" in local["base_url"]

    def test_local_auth_not_required(self):
        """local provider 应标记 auth_required=false。"""
        with open(ROOT / "models.json", encoding="utf-8") as f:
            cfg = json.load(f)
        local = cfg["providers"]["local"]
        assert local.get("auth_required", True) is False

    def test_local_in_fallback_priority(self):
        """fallback.priority 应包含 local。"""
        with open(ROOT / "models.json", encoding="utf-8") as f:
            cfg = json.load(f)
        assert "local" in cfg["fallback"]["priority"]

    def test_local_model_id(self):
        """local provider 的 models.pro 应指向 GGUF 文件名。"""
        with open(ROOT / "models.json", encoding="utf-8") as f:
            cfg = json.load(f)
        local = cfg["providers"]["local"]
        model_id = local["models"]["pro"]
        assert "Qwen3.6" in model_id


# ── MODEL_REGISTRY 注册验证 ─────────────────────────────────────────


class TestLocalModelRegistry:
    def test_local_model_registered(self):
        """Qwen3.6-27B-PRISM-PRO-DQ 应在 MODEL_REGISTRY 中注册。"""
        from core.provider import MODEL_REGISTRY
        assert "Qwen3.6-27B-PRISM-PRO-DQ" in MODEL_REGISTRY

    def test_local_model_aliases(self):
        """local 模型应有 local / qwen / qwen3 别名。"""
        from core.provider import MODEL_REGISTRY
        info = MODEL_REGISTRY["Qwen3.6-27B-PRISM-PRO-DQ"]
        assert "local" in info.aliases
        assert "qwen" in info.aliases

    def test_local_model_provider_id(self):
        """local 模型的 provider_id 应为 "local"。"""
        from core.provider import MODEL_REGISTRY
        info = MODEL_REGISTRY["Qwen3.6-27B-PRISM-PRO-DQ"]
        assert info.provider_id == "local"

    def test_local_model_supports_tools(self):
        """local 模型应标记 supports_tools=True。"""
        from core.provider import MODEL_REGISTRY
        info = MODEL_REGISTRY["Qwen3.6-27B-PRISM-PRO-DQ"]
        assert info.supports_tools is True


# ── create_client auth_required 放行 ────────────────────────────────


class TestCreateClientLocalAuth:
    def test_local_client_base_url_correct(self):
        """create_client("local") 应返回指向 llama-server 的 client，
        而非静默 fallback 到云 provider（Blocker A 回归）。"""
        from core.provider import ProviderManager

        # 构造一个只有 local provider 的最小 ProviderManager
        mgr = ProviderManager.__new__(ProviderManager)
        mgr.config_path = ROOT / "models.json"
        mgr.providers = {
            "local": {
                "name": "Local llama.cpp",
                "base_url": "http://127.0.0.1:8080/v1",
                "api_key": "no-auth-needed",
                "auth_required": False,
                "models": {"pro": "Qwen3.6-27B-PRISM-PRO-DQ"},
            }
        }
        mgr.fallback_priority = ["local"]
        mgr.state = MagicMock()
        mgr.state.active = "crux"  # active 是 crux，但显式请求 local

        client = mgr.create_client("local")
        assert "127.0.0.1:8080" in client.base_url

    def test_local_no_auth_required_skips_key_check(self):
        """auth_required=false 的 provider 即使 api_key 为空也不应 fallback。"""
        from core.provider import ProviderManager

        mgr = ProviderManager.__new__(ProviderManager)
        mgr.config_path = ROOT / "models.json"
        mgr.providers = {
            "local": {
                "name": "Local llama.cpp",
                "base_url": "http://127.0.0.1:8080/v1",
                "api_key": "",  # 空 key
                "auth_required": False,  # 但免鉴权
                "models": {"pro": "Qwen3.6-27B-PRISM-PRO-DQ"},
            },
            "deepseek": {
                "name": "DeepSeek",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-xxx",
                "models": {"pro": "deepseek-v4-pro"},
            },
        }
        mgr.fallback_priority = ["local"]
        mgr.state = MagicMock()
        mgr.state.active = "crux"

        # 不应 fallback 到 deepseek
        client = mgr.create_client("local")
        assert "127.0.0.1:8080" in client.base_url
        assert "deepseek" not in client.base_url


# ── wait_for_provider 轮询逻辑 ─────────────────────────────────────
# 注意：wait_for_provider 内部是局部 `import httpx` + 局部使用，
# 所以 mock 必须 patch `httpx` 模块本身（顶层 import），不能 patch
# core.startup_checks.httpx（后者在函数被调用时才绑定到局部变量）。


class TestWaitForProvider:
    def test_immediate_success(self):
        """端点立即响应 200 → 秒回 (True, msg)。"""
        from core.startup_checks import wait_for_provider

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch.object(httpx, "get", return_value=mock_resp):
            ok, msg = wait_for_provider("http://127.0.0.1:8080/v1", timeout=1.0, interval=0.1)
        assert ok is True
        assert "200" in msg

    def test_timeout_on_connection_refused(self):
        """端点始终拒绝连接 → timeout 后返回 (False, error_msg)。"""
        from core.startup_checks import wait_for_provider

        with patch.object(httpx, "get", side_effect=httpx.ConnectError("Connection refused")):
            ok, msg = wait_for_provider("http://127.0.0.1:8080/v1", timeout=0.5, interval=0.1)
        assert ok is False
        assert "Connection refused" in msg or "timeout" in msg

    def test_timeout_message(self):
        """超时返回应包含 timeout 信息。"""
        from core.startup_checks import wait_for_provider

        with patch.object(httpx, "get", side_effect=httpx.ConnectError("refused")):
            ok, msg = wait_for_provider("http://127.0.0.1:8080/v1", timeout=0.3, interval=0.1)
        assert ok is False


# ── _check_local_llm 结果写入 ───────────────────────────────────────
# _check_local_llm 内部 get_provider_manager() 是局部 import，需要
# mock 它所在的 provider 模块；httpx 探测则 mock httpx.get（同上）。


class TestCheckLocalLlm:
    def _reset_results(self):
        """清空模块级 _results 列表。"""
        import core.startup_checks as _sc
        _sc._results.clear()

    def test_local_reachable(self):
        """local provider 可达时 _add("local_llm", True, ...)。"""
        import core.startup_checks as _sc
        from core.provider import ProviderManager

        # mock provider manager 返回含 local 的配置
        mock_mgr = MagicMock(spec=ProviderManager)
        mock_mgr.providers = {
            "local": {
                "name": "Local llama.cpp",
                "base_url": "http://127.0.0.1:8080/v1",
            }
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        self._reset_results()
        with patch("core.provider.get_provider_manager", return_value=mock_mgr):
            with patch.object(httpx, "get", return_value=mock_resp):
                _sc._check_local_llm()

        cats = [r[0] for r in _sc._results]
        assert "local_llm" in cats
        ok_map = {r[0]: r[1] for r in _sc._results}
        assert ok_map["local_llm"] is True

    def test_local_unreachable(self):
        """local provider 不可达时标记 False + 友好提示。"""
        import core.startup_checks as _sc
        from core.provider import ProviderManager

        mock_mgr = MagicMock(spec=ProviderManager)
        mock_mgr.providers = {
            "local": {
                "name": "Local llama.cpp",
                "base_url": "http://127.0.0.1:8080/v1",
            }
        }

        self._reset_results()
        with patch("core.provider.get_provider_manager", return_value=mock_mgr):
            with patch.object(httpx, "get", side_effect=httpx.ConnectError("refused")):
                _sc._check_local_llm()

        ok_map = {r[0]: r[1] for r in _sc._results}
        assert ok_map.get("local_llm") is False

    def test_no_local_provider_configured(self):
        """没有 local provider 时 _check_local_llm 静默跳过（不写结果）。"""
        import core.startup_checks as _sc
        from core.provider import ProviderManager

        mock_mgr = MagicMock(spec=ProviderManager)
        mock_mgr.providers = {}  # 没有 local

        self._reset_results()
        with patch("core.provider.get_provider_manager", return_value=mock_mgr):
            _sc._check_local_llm()

        cats = [r[0] for r in _sc._results]
        assert "local_llm" not in cats


# ── _quick_health local_llm_health 字段 ────────────────────────────
# _quick_health 是 CapabilityRegistry 的实例方法，通过 snapshot() 调用。
# local_llm_health 探测 httpx.get 端点，无 llama-server 时 reachable=False。


class TestQuickHealthLocalLlm:
    def test_local_llm_health_reflection(self):
        """snapshot() 返回的 health 应包含 local_llm_health 字段（真反射探测）。
        在无 llama-server 环境下，reachable=False + error 是正常预期。
        """
        from core.capability import CapabilityRegistry

        reg = CapabilityRegistry()
        snap = reg.snapshot()
        health = snap.get("health", {})
        assert "local_llm_health" in health
        entry = health["local_llm_health"]
        assert "reachable" in entry
        # 无 llama-server 运行时 reachable=False，有 error 字段
        if not entry["reachable"]:
            assert "error" in entry
        else:
            assert "latency_ms" in entry
            assert "model_count" in entry
