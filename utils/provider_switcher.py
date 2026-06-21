"""Provider switcher -- update models.json AND sync .env for subprocess."""

import json
from pathlib import Path

__all__ = ['ROOT', 'switch_provider']


ROOT = Path(__file__).resolve().parent.parent


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

    # 1. Update models.json active
    data["active"] = key
    models_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Sync .env so subprocess (AgnesClient) picks up correct base_url and key
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").split(chr(10))
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("AGNES_BASE_URL="):
                new_lines.append(f"AGNES_BASE_URL={base_url}")
            elif stripped.startswith("AGNES_API_KEY="):
                if api_key and api_key != "not-needed":
                    new_lines.append(f"AGNES_API_KEY={api_key}")
                else:
                    new_lines.append(line)  # keep existing key for local models
            else:
                new_lines.append(line)
        env_path.write_text(chr(10).join(new_lines), encoding="utf-8")

    return True, f"Switched to {key} ({provider.get('name', key)}) -> {base_url}"
