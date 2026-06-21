"""Tests for utils.templates — prompt template library."""



# ── list_templates ───────────────────────────────────────────────────────


class TestListTemplates:
    """List available prompt templates."""

    def test_returns_list(self):
        from utils.templates import list_templates
        result = list_templates()
        assert isinstance(result, list)

    def test_has_templates(self):
        from utils.templates import list_templates
        result = list_templates()
        assert len(result) > 0

    def test_all_strings(self):
        from utils.templates import list_templates
        for name in list_templates():
            assert isinstance(name, str)
            assert len(name) > 0


# ── get_template ─────────────────────────────────────────────────────────


class TestGetTemplate:
    """Get template by name."""

    def test_existing_template(self):
        from utils.templates import list_templates, get_template
        names = list_templates()
        if names:
            tpl = get_template(names[0])
            assert tpl is not None
            assert isinstance(tpl, dict)

    def test_nonexistent_template(self):
        from utils.templates import get_template
        assert get_template("__nonexistent_xyz__") is None

    def test_template_has_required_keys(self):
        from utils.templates import list_templates, get_template
        names = list_templates()
        if names:
            tpl = get_template(names[0])
            # Templates have image/video/negative keys
            assert tpl and ("image" in tpl or "video" in tpl)


# ── apply_template ───────────────────────────────────────────────────────


class TestApplyTemplate:
    """Apply a template to a user prompt."""

    def test_returns_tuple(self):
        from utils.templates import list_templates, apply_template
        names = list_templates()
        if names:
            result = apply_template(names[0], "a cute cat", target="image")
            assert isinstance(result, tuple)
            assert len(result) == 2

    def test_enhanced_prompt_contains_user_input(self):
        from utils.templates import list_templates, apply_template
        names = list_templates()
        if names:
            enhanced, _ = apply_template(names[0], "a cute cat")
            assert "cat" in enhanced

    def test_nonexistent_template_returns_original(self):
        """Nonexistent template returns the original prompt unchanged."""
        from utils.templates import apply_template
        enhanced, negative = apply_template("__nonexistent__", "test prompt")
        assert enhanced == "test prompt"
        assert negative == ""

    def test_video_target(self):
        from utils.templates import list_templates, apply_template
        names = list_templates()
        if names:
            enhanced, _ = apply_template(names[0], "sunset timelapse", target="video")
            assert isinstance(enhanced, str)
            assert len(enhanced) > 0


# ── get_template_info ───────────────────────────────────────────────────


class TestGetTemplateInfo:
    """Get formatted template description."""

    def test_returns_string(self):
        from utils.templates import list_templates, get_template_info
        names = list_templates()
        if names:
            info = get_template_info(names[0])
            assert isinstance(info, str)
            assert len(info) > 0

    def test_nonexistent_template(self):
        from utils.templates import get_template_info
        info = get_template_info("__nonexistent__")
        assert isinstance(info, str)
