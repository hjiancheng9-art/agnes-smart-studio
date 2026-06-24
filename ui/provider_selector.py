"""Provider selection & activation — extracted from ui/cli.py"""

import contextlib
import json
import os
from pathlib import Path

from rich.prompt import Prompt
from rich.table import Table

from ui.display import show_info, show_success, show_warning
from ui.theme import COLORS, console

__all__ = ['ProviderSelector']



class ProviderSelector:
    """Scans models.json for available providers and handles selection/activation."""

    def __init__(self, on_client_swap):
        """on_client_swap(api_key: str, base_url: str) — callback to swap the chat client."""
        self._on_client_swap = on_client_swap

    # ── 配置加载 ──────────────────────────────────

    @staticmethod
    def load_models_config() -> dict:
        """安全加载 models.json（项目根），文件缺失/空/损坏时返回默认配置"""
        root = Path(__file__).resolve().parent.parent
        cfg_path = root / "models.json"

        def _default_cfg():
            return {
                "providers": {
                    "crux": {"name": "CRUX AI", "base_url": "https://apihub.agnes-ai.com/v1",
                              "api_key": "", "models": {"light": "agnes-1.5-flash", "pro": "agnes-2.0-flash"}},
                    "deepseek": {"name": "DeepSeek V4 Pro (1M)", "base_url": "https://api.deepseek.com/v1",
                                 "api_key": "", "models": {"pro": "deepseek-v4-pro", "light": "deepseek-v4-pro"}},
                    "siliconflow": {"name": "SiliconFlow (Kimi-K2.6)", "base_url": "https://api.siliconflow.cn/v1",
                                    "api_key": "", "models": {"pro": "Pro/moonshotai/Kimi-K2.6", "light": "Pro/moonshotai/Kimi-K2.6"}},
                },
                "active": "crux",
                "fallback": {"enabled": True, "priority": ["deepseek", "siliconflow"]},
            }

        if not os.path.exists(cfg_path):
            # 新建默认文件
            cfg = _default_cfg()
            with contextlib.suppress(OSError, TypeError):
                Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            return cfg

        raw = ""
        try:
            raw = Path(cfg_path).read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("空文件")
            cfg = json.loads(raw)
            # 确保必要字段存在
            if "providers" not in cfg:
                cfg["providers"] = _default_cfg()["providers"]
            if "active" not in cfg:
                cfg["active"] = "crux"
            return cfg
        except (json.JSONDecodeError, ValueError) as e:
            # 文件损坏或为空 → 重建
            show_warning(f"models.json 损坏 ({e})，已自动重建默认配置")
            cfg = _default_cfg()
            with contextlib.suppress(OSError, TypeError):
                Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            return cfg

    # ── 供应商选择 ──────────────────────────────────

    def select_provider(self):
        """交互式供应商选择（多 Key 时弹出菜单，单 Key 自动激活）

        1. 扫描所有 providers，收集有 API Key 的
        2. 1 个外部供应商 → 自动激活
        3. ≥2 个外部供应商 → 弹出菜单让用户选择
        4. 0 个外部供应商 → 使用 CRUX

        Returns: (provider_id, model_id)
        """
        cfg = self.load_models_config()
        cfg_path = Path(__file__).resolve().parent.parent / "models.json"

        providers = cfg.get("providers", {})

        # 收集所有有 Key 的供应商
        available = []
        for pid, p in providers.items():
            key_env = f"{pid.upper()}_API_KEY"
            api_key = p.get("api_key") or os.getenv(key_env)
            if api_key:
                model = p.get("models", {}).get("pro", "unknown")
                available.append((pid, p, model, api_key))

        if not available:
            # 没有任何 Key → CRUX
            p = providers.get("crux", providers.get(list(providers.keys())[0], {}))
            model = p.get("models", {}).get("light", "agnes-1.5-flash")
            show_info("无外部供应商 Key，使用默认 CRUX light")
            return ("crux", model)

        # 只有 CRUX → 直接用
        if len(available) == 1 and available[0][0] == "crux":
            pid, p, model, _ = available[0]
            return (pid, model)

        # 过滤出非 CRUX 的外部供应商
        external = [(pid, p, m, k) for pid, p, m, k in available if pid != "crux"]

        if len(external) == 1:
            # 只有一个外部供应商 → 自动激活
            pid, p, model, api_key = external[0]
            self._activate_provider(pid, p, model, api_key, cfg, cfg_path)
            return (pid, model)

        # ≥2 个外部供应商 → 弹出菜单
        console.print()
        table = Table(title="[bold cyan]选择主对话供应商[/]（视觉始终走 CRUX 独立通道）",
                       border_style=COLORS["primary"])
        table.add_column("#", style="bold cyan", width=3)
        table.add_column("供应商", style="white", width=16)
        table.add_column("模型", style="dim")
        table.add_column("说明", style="dim")

        choices = []
        idx = 1
        for pid, p, model, _ in available:
            label = f"{idx}"
            desc = ""
            if pid == "deepseek":
                desc = "百万上下文 · 代码/推理"
            elif pid == "siliconflow":
                desc = "Kimi-K2.6 · 备选链路"
            elif pid == "crux":
                desc = "原生模型 · 轻量快速"
            table.add_row(label, p["name"], model, desc)
            choices.append((str(idx), pid, p, model))
            idx += 1

        console.print(table)
        console.print()

        choice = Prompt.ask(
            "[cyan]选择供应商[/]",
            choices=[c[0] for c in choices] + ["q"],
            default="1",
        )
        if choice == "q":
            show_info("已取消，使用默认 CRUX light")
            p = providers.get("crux", {})
            return ("crux", p.get("models", {}).get("light", "agnes-1.5-flash"))

        # 找到选中的供应商
        for num, pid, p, model in choices:
            if num == choice:
                if pid == "crux":
                    return (pid, model)
                # 外部供应商需要激活
                key_env = f"{pid.upper()}_API_KEY"
                api_key = p.get("api_key") or os.getenv(key_env)
                self._activate_provider(pid, p, model, api_key, cfg, cfg_path)
                return (pid, model)

        return ("crux", "agnes-1.5-flash")

    # ── 激活 ──────────────────────────────────────

    def _activate_provider(self, pid, p, model, api_key, cfg, cfg_path):
        """激活指定供应商：切换 client 并写入 models.json"""
        self._on_client_swap(api_key, p["base_url"])
        cfg["active"] = pid
        with contextlib.suppress(OSError, TypeError):
            Path(cfg_path).write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        from core.chat import MODEL_INFO
        cap = MODEL_INFO.get(model, pid)
        show_success(f"已激活 {p['name']} → {model}（{cap}）")
