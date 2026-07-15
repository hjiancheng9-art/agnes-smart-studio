"""Provider switcher -- update models.json AND sync .env for subprocess."""

import json
import os
import tempfile
from pathlib import Path

__all__ = ["ROOT", "switch_provider"]


ROOT = Path(__file__).resolve().parent.parent


def _atomic_write_text(path: Path, text: str) -> None:
    """原子写入文本文件（temp + os.replace），防止并发写入导致损坏。"""
    tmp_fd, tmp_name = tempfile.mkstemp(suffix=".tmp", prefix=".cfg_", dir=str(path.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_name, str(path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def switch_provider(key: str) -> tuple:
    """Activate a provider and sync .env so subprocess picks it up.

    Returns (success: bool, message: str).
    """
    models_path = ROOT / "models.json"
    env_path = ROOT / ".env"

    try:
        data = json.loads(models_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return False, f"models.json error: {e}"

    providers = data.get("providers", {})
    if key not in providers:
        return False, f"Unknown provider: {key}. Options: {list(providers.keys())}"

    provider = providers[key]
    base_url = provider.get("base_url", "")
    api_key = provider.get("api_key", "")

    # 1. Update models.json active (atomic write)
    data["active"] = key
    _atomic_write_text(models_path, json.dumps(data, ensure_ascii=False, indent=2))

    # 2. Sync .env so subprocess (CruxClient) picks up correct base_url and key
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").split(chr(10))
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("CRUX_BASE_URL=") or stripped.startswith("AGNES_BASE_URL="):
                new_lines.append(f"CRUX_BASE_URL={base_url}")
            elif stripped.startswith("CRUX_API_KEY=") or stripped.startswith("AGNES_API_KEY="):
                if api_key and api_key != "not-needed":
                    new_lines.append(f"CRUX_API_KEY={api_key}")
                else:
                    new_lines.append(line)  # keep existing key for local models
            else:
                new_lines.append(line)
        _atomic_write_text(env_path, chr(10).join(new_lines))

    return True, f"Switched to {key} ({provider.get('name', key)}) -> {base_url}"
