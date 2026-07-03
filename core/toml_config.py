"""TOML configuration layer — config.toml / tui.toml for CRUX.

Kimi Code places config at ~/.kimi-code/config.toml.
CRUX mirrors this at project-level config.toml or ~/.crux/config.toml.

Priority (high → low):
    1. Environment variables (CRUX_* / AGNES_*)
    2. Project .env file
    3. Project config.toml
    4. Global ~/.crux/config.toml
    5. Global ~/.crux/auth.json (legacy)

Usage:
    from core.toml_config import load_config, save_config, get_config
    cfg = load_config()
    model = cfg.get("model", "auto")
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from core.config import CRUX_HOME

__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_TUI_CONFIG",
    "TomlConfig",
    "get_config",
    "load_config",
    "save_config",
]

# ── Defaults ─────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "auto",
    "model": "auto",
    "permission_mode": "auto",  # yolo | auto | manual
    "thinking": True,
    "budget_daily_usd": None,
}

DEFAULT_TUI_CONFIG: dict[str, Any] = {
    "theme": "auto",  # auto | dark | light
    "editor": {
        "command": "",
    },
    "notifications": {
        "enabled": True,
        "notification_condition": "unfocused",  # always | unfocused | never
    },
    "upgrade": {
        "auto_install": True,
    },
}


# ── TOML helpers ──────────────────────────────────────────────

def _parse_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML file without external dependencies.

    Uses Python 3.11+ tomllib if available, falls back to a minimal parser.
    """
    if sys.version_info >= (3, 11):
        import tomllib
        try:
            with open(path, "rb") as fh:
                return tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError):
            return {}
    else:
        # Fallback: try tomli (common backport)
        try:
            import tomli
            with open(path, "rb") as fh:
                return tomli.load(fh)
        except ImportError:
            pass
        except (OSError, Exception):
            return {}
        # Minimal inline parser for simple key=value TOML
        return _minimal_toml_parse(path)


def _minimal_toml_parse(path: Path) -> dict[str, Any]:
    """Minimal TOML parser for simple flat key=value files.

    Supports: [section] headers, key = "value", key = number, key = true/false.
    Does NOT support: nested tables, arrays of tables, inline tables, multiline strings.
    """
    result: dict[str, Any] = {}
    current_section: dict[str, Any] = result
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            # Skip comments and blank lines
            if not line or line.startswith("#"):
                continue
            # Section header
            if line.startswith("[") and line.endswith("]"):
                section_name = line[1:-1].strip()
                if "." in section_name:
                    # Dotted key: [editor.command] → result["editor"]["command"]
                    parts = section_name.split(".")
                    target = result
                    for part in parts[:-1]:
                        if part not in target:
                            target[part] = {}
                        target = target[part]
                    if parts[-1] not in target:
                        target[parts[-1]] = {}
                    current_section = target[parts[-1]]
                else:
                    if section_name not in result:
                        result[section_name] = {}
                    current_section = result[section_name]
                continue
            # key = value
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # String value
                if value.startswith('"') and value.endswith('"'):
                    current_section[key] = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    current_section[key] = value[1:-1]
                elif value.lower() == "true":
                    current_section[key] = True
                elif value.lower() == "false":
                    current_section[key] = False
                elif value.lower() in ("null", "none", ""):
                    current_section[key] = None
                else:
                    # Try number
                    try:
                        if "." in value:
                            current_section[key] = float(value)
                        else:
                            current_section[key] = int(value)
                    except ValueError:
                        current_section[key] = value
    except OSError:
        pass
    return result


def _write_toml(data: dict[str, Any], path: Path) -> None:
    """Write a flat dict as TOML. Nested dicts become [section] headers."""
    lines: list[str] = []
    sections: list[tuple[str, dict]] = []
    top_level: dict[str, Any] = {}

    for key, value in data.items():
        if isinstance(value, dict):
            sections.append((key, value))
        else:
            top_level[key] = value

    # Top-level keys
    for key, value in top_level.items():
        lines.append(f"{key} = {_toml_value(value)}")

    # Sections
    for section_name, section_data in sections:
        if lines:
            lines.append("")
        lines.append(f"[{section_name}]")
        for key, value in section_data.items():
            lines.append(f"{key} = {_toml_value(value)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _toml_value(value: Any) -> str:
    """Convert Python value to TOML literal."""
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # String: escape backslashes and quotes
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


# ── Config path resolution ────────────────────────────────────


def _resolve_config_paths() -> tuple[Path, Path, Path]:
    """Return (project_config, global_config, project_tui) paths."""
    cwd = Path.cwd()
    project_config = cwd / "config.toml"
    global_config = CRUX_HOME / "config.toml"
    project_tui = cwd / "tui.toml"
    return project_config, global_config, project_tui


# ── Public API ────────────────────────────────────────────────


class TomlConfig:
    """Merged configuration from all sources."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = dict(DEFAULT_CONFIG)
        self._tui: dict[str, Any] = dict(DEFAULT_TUI_CONFIG)
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        project_cfg, global_cfg, project_tui = _resolve_config_paths()

        # Load global config (lowest priority)
        if global_cfg.exists():
            global_data = _parse_toml(global_cfg)
            _deep_update(self._data, {k: v for k, v in global_data.items() if k != "tui"})
            if "tui" in global_data:
                _deep_update(self._tui, global_data["tui"])

        # Load project config (overrides global)
        if project_cfg.exists():
            proj_data = _parse_toml(project_cfg)
            _deep_update(self._data, {k: v for k, v in proj_data.items() if k != "tui"})
            if "tui" in proj_data:
                _deep_update(self._tui, proj_data["tui"])

        # Load project tui.toml (overrides config.toml tui section)
        if project_tui.exists():
            tui_data = _parse_toml(project_tui)
            _deep_update(self._tui, tui_data)

    def get(self, key: str, default: Any = None) -> Any:
        self._ensure_loaded()
        return self._data.get(key, default)

    def get_tui(self, key: str, default: Any = None) -> Any:
        self._ensure_loaded()
        return self._tui.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._ensure_loaded()
        self._data[key] = value

    def to_dict(self) -> dict[str, Any]:
        self._ensure_loaded()
        return dict(self._data)

    def to_tui_dict(self) -> dict[str, Any]:
        self._ensure_loaded()
        return dict(self._tui)


_config_singleton: TomlConfig | None = None


def get_config() -> TomlConfig:
    """Get the global Config singleton. Lazy-created on first call."""
    global _config_singleton
    if _config_singleton is None:
        _config_singleton = TomlConfig()
    return _config_singleton


def load_config() -> TomlConfig:
    """Force-reload config from disk. Returns the singleton."""
    global _config_singleton
    _config_singleton = TomlConfig()
    _config_singleton._ensure_loaded()
    return _config_singleton


def save_config(data: dict[str, Any] | None = None, *, project_level: bool = True) -> Path:
    """Save config to disk. If data is None, saves the current singleton.

    Returns the path that was written.
    """
    cfg = get_config()
    if data:
        for k, v in data.items():
            cfg.set(k, v)

    if project_level:
        path = Path.cwd() / "config.toml"
    else:
        path = CRUX_HOME / "config.toml"

    _write_toml(cfg.to_dict(), path)
    return path


def _deep_update(target: dict, source: dict) -> None:
    """Recursively update target dict with source values."""
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
