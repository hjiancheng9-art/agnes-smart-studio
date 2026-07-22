"""Tests for vision model resolution.

RED phase: these tests assert agnes-2.5-flash is the vision model.
They should FAIL currently because the code still uses agnes-2.0-flash.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch


def test_models_json_vision_is_agnes_2_5_flash():
    """models.json should declare vision=agnes-2.5-flash."""
    models_path = Path(__file__).resolve().parent.parent / "models.json"
    assert models_path.exists()
    with open(models_path, encoding="utf-8") as f:
        data = json.load(f)
    vision = data["providers"]["crux"]["models"]["vision"]
    assert vision == "agnes-2.5-flash"


def test_get_crux_vision_model_with_key():
    """get_crux_vision_model returns vision model when CRUX key is set."""
    from core.config import get_crux_vision_model

    mock_providers = {"crux": {"api_key": "tk", "models": {"vision": "agnes-2.5-flash"}}}
    with (
        patch("core.provider.get_provider_manager") as mm,
        patch.dict(os.environ, {"CRUX_API_KEY": "tk"}, clear=True),
    ):
        mm.return_value.load.return_value = None
        mm.return_value.providers = mock_providers
        assert get_crux_vision_model() == "agnes-2.5-flash"


def test_default_vision_with_key():
    """ModelRouter._default_vision returns vision model when CRUX key is set."""
    from core.agent import ModelRouter

    mock_providers = {"crux": {"api_key": "tk", "models": {"vision": "agnes-2.5-flash"}}}
    with (
        patch("core.provider.get_provider_manager") as mm,
        patch.dict(os.environ, {"CRUX_API_KEY": "tk"}, clear=True),
    ):
        mm.return_value.load.return_value = None
        mm.return_value.providers = mock_providers
        assert ModelRouter._default_vision() == "agnes-2.5-flash"
