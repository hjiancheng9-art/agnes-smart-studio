"""Tests for core.config — model registry, presets, and settings persistence."""

import json
import os


class TestConstants:
    def test_models_dict_has_required_entries(self):
        from core.config import MODELS
        assert "text_light" in MODELS
        assert "text_pro" in MODELS
        assert "image_hd" in MODELS
        assert "video" in MODELS

    def test_each_model_has_id_and_name(self):
        from core.config import MODELS
        for key, model in MODELS.items():
            assert "id" in model, f"{key} missing id"
            assert "name" in model, f"{key} missing name"
            assert "type" in model, f"{key} missing type"

    def test_video_aspect_ratios_are_tuples(self):
        from core.config import VIDEO_ASPECT_RATIOS
        for _name, dims in VIDEO_ASPECT_RATIOS.items():
            assert isinstance(dims, tuple)
            assert len(dims) == 2
            assert all(isinstance(d, int) for d in dims)

    def test_image_sizes_format(self):
        from core.config import IMAGE_SIZES
        for _name, size in IMAGE_SIZES.items():
            assert "x" in size
            w, h = size.split("x")
            assert w.isdigit() and h.isdigit()

    def test_valid_num_frames_all_conform(self):
        """Each valid num_frames must equal 8n+1 for some integer n (and <=441)."""
        from core.config import VALID_NUM_FRAMES
        for n in VALID_NUM_FRAMES:
            assert (n - 1) % 8 == 0, f"{n} is not 8n+1"
            assert n <= 441

    def test_video_duration_map_keys_subset_of_valid_frames(self):
        from core.config import VALID_NUM_FRAMES, VIDEO_DURATION_MAP
        for n in VIDEO_DURATION_MAP:
            # 441 is allowed in duration map even though not in default list
            assert n == 441 or n in VALID_NUM_FRAMES

    def test_prompt_templates_structure(self):
        from core.config import PROMPT_TEMPLATES
        assert len(PROMPT_TEMPLATES) >= 5
        for name, tpl in PROMPT_TEMPLATES.items():
            assert "image" in tpl, f"{name} missing image prompt"
            assert "negative" in tpl, f"{name} missing negative prompt"

    def test_vision_constants(self):
        from core.config import AGNES_VISION_MODEL, AGNES_VISION_BASE_URL
        assert AGNES_VISION_MODEL.startswith("agnes")
        assert AGNES_VISION_BASE_URL.startswith("https://")

    def test_output_dir_exists(self):
        from core.config import OUTPUT_DIR
        assert OUTPUT_DIR.exists()
        assert (OUTPUT_DIR / "images").exists()
        assert (OUTPUT_DIR / "videos").exists()


class TestSettings:
    def test_settings_has_defaults(self):
        from core.config import Settings
        s = Settings()
        assert s.api_key == os.getenv("AGNES_API_KEY", "")
        assert s.max_retries == 3
        assert s.default_frame_rate == 24

    def test_settings_save_and_load(self, tmp_path):
        from core.config import Settings
        path = str(tmp_path / "settings.json")
        s = Settings(api_key="key123", max_retries=5)
        s.save(path)
        loaded = Settings.load(path)
        assert loaded.api_key == "key123"
        assert loaded.max_retries == 5

    def test_settings_load_missing_returns_defaults(self, tmp_path):
        from core.config import Settings
        path = str(tmp_path / "nonexistent.json")
        loaded = Settings.load(path)
        assert loaded.max_retries == 3  # default

    def test_settings_load_none_falls_back_to_default(self, tmp_path):
        """JSON value of None should fall back to dataclass default."""
        from core.config import Settings
        path = str(tmp_path / "settings.json")
        # Write a settings file with max_retries explicitly null
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"max_retries": None}, f)
        loaded = Settings.load(path)
        assert loaded.max_retries == 3  # falls back to default, not None

    def test_settings_load_preserves_zero(self, tmp_path):
        """Zero is a legitimate value, not 'unset'."""
        from core.config import Settings
        path = str(tmp_path / "settings.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"max_retries": 0}, f)
        loaded = Settings.load(path)
        assert loaded.max_retries == 0

    def test_settings_is_singleton_loaded(self):
        from core.config import SETTINGS
        assert SETTINGS is not None
        assert isinstance(SETTINGS.max_retries, int)
