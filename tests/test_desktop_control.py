"""Tests for Win32 DesktopControlProvider."""

from __future__ import annotations

import platform

import PIL.Image
import pytest

from tools.desktop_control import DesktopControlProvider, MouseButton


@pytest.fixture
def ctrl():
    """Provide a provider instance."""
    return DesktopControlProvider()


class TestReadOnly:
    """Tests that do NOT move the mouse or click anything."""

    def test_get_screen_size(self, ctrl):
        w, h = ctrl.get_screen_size()
        assert isinstance(w, int) and w > 0
        assert isinstance(h, int) and h > 0
        assert w >= 800
        assert h >= 600

    def test_get_cursor_position(self, ctrl):
        x, y = ctrl.get_cursor_position()
        assert isinstance(x, int)
        assert isinstance(y, int)

    def test_screenshot_returns_image(self, ctrl):
        img = ctrl.screenshot()
        assert isinstance(img, PIL.Image.Image)
        assert img.size == ctrl.get_screen_size()

    def test_screenshot_saves_to_path(self, ctrl, tmp_path):
        path = str(tmp_path / "test_scr.png")
        ctrl.screenshot(path)
        assert tmp_path.joinpath("test_scr.png").exists()

    def test_get_pixel_color(self, ctrl):
        r, g, b = ctrl.get_pixel_color(0, 0)
        assert isinstance(r, int) and 0 <= r <= 255
        assert isinstance(g, int) and 0 <= g <= 255
        assert isinstance(b, int) and 0 <= b <= 255

    def test_move_to_random_position_is_undoable(self, ctrl):
        orig = ctrl.get_cursor_position()
        target = (42, 315)
        ctrl.move(*target)
        pos = ctrl.get_cursor_position()
        ctrl.move(*orig)
        assert pos == target, f"Cursor should be at {target}, got {pos}"


class TestInputValidation:
    def test_move_non_int_raises(self, ctrl):
        with pytest.raises(TypeError):
            ctrl.move("a", 100)

    def test_move_non_int_y_raises(self, ctrl):
        with pytest.raises(TypeError):
            ctrl.move(100, "b")

    def test_click_invalid_button_raises(self, ctrl):
        with pytest.raises(ValueError, match="Unknown button"):
            ctrl.click("unknown")

    def test_drag_invalid_coords_raises(self, ctrl):
        with pytest.raises(TypeError):
            ctrl.drag(0, 0, "x", 100)


class TestMouse:
    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_click_left_does_not_crash(self, ctrl):
        ctrl.click("left")

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_left_click_does_not_crash(self, ctrl):
        ctrl.left_click()

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_right_click_does_not_crash(self, ctrl):
        ctrl.right_click()

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_double_click_does_not_crash(self, ctrl):
        ctrl.double_click()

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_drag_does_not_crash(self, ctrl):
        orig = ctrl.get_cursor_position()
        target = (orig[0] + 50, orig[1] + 50)
        ctrl.drag(orig[0], orig[1], target[0], target[1])

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_scroll_does_not_crash(self, ctrl):
        ctrl.scroll(delta_y=1)
        ctrl.scroll(delta_y=-1)

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_type_does_not_crash(self, ctrl):
        ctrl.type("hello world")


class TestKeyboard:
    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_key_down_up_does_not_crash(self, ctrl):
        ctrl.key_down("a")
        ctrl.key_up("a")

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_press_key_does_not_crash(self, ctrl):
        ctrl.press_key("c", modifiers=["ctrl"])

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_press_key_no_modifiers(self, ctrl):
        ctrl.press_key("enter")

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_press_key_invalid_modifier_raises(self, ctrl):
        with pytest.raises(ValueError, match="Unknown modifier"):
            ctrl.press_key("a", modifiers=["foo"])

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_key_down_invalid_key_raises(self, ctrl):
        with pytest.raises(ValueError, match="Unknown key"):
            ctrl.key_down("__NOT_A_KEY__")

    @pytest.mark.skipif(platform.system() != "Windows", reason="Win32 only")
    def test_press_key_unknown_key_raises(self, ctrl):
        with pytest.raises(ValueError, match="Unknown key"):
            ctrl.press_key("__NOT_A_KEY__")


class TestMouseButton:
    def test_enum_values(self):
        assert MouseButton.LEFT.value == "left"
        assert MouseButton.RIGHT.value == "right"
        assert MouseButton.MIDDLE.value == "middle"
