"""
Win32 native desktop control provider.
Provides mouse, keyboard, and screen capture operations via Windows API.
No external dependencies beyond pywin32 and Pillow.

Usage:
    ctrl = DesktopControlProvider()
    ctrl.move(100, 200)
    ctrl.left_click()
    ctrl.type("hello world")
    img = ctrl.screenshot()
"""

from __future__ import annotations

import time
from enum import Enum

import win32api
import win32con
import win32gui
from PIL import Image, ImageGrab


class MouseButton(str, Enum):
    """Supported mouse buttons."""

    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class DesktopControlProvider:
    """Win32 native desktop control provider.

    All coordinates are absolute screen coordinates (primary monitor).
    Mouse positions use the Windows convention: origin (0,0) = top-left.
    """

    # Virtual-key code map (subset of common keys)
    VK_MAP: dict[str, int] = {
        "a": 0x41,
        "b": 0x42,
        "c": 0x43,
        "d": 0x44,
        "e": 0x45,
        "f": 0x46,
        "g": 0x47,
        "h": 0x48,
        "i": 0x49,
        "j": 0x4A,
        "k": 0x4B,
        "l": 0x4C,
        "m": 0x4D,
        "n": 0x4E,
        "o": 0x4F,
        "p": 0x50,
        "q": 0x51,
        "r": 0x52,
        "s": 0x53,
        "t": 0x54,
        "u": 0x55,
        "v": 0x56,
        "w": 0x57,
        "x": 0x58,
        "y": 0x59,
        "z": 0x5A,
        "0": 0x30,
        "1": 0x31,
        "2": 0x32,
        "3": 0x33,
        "4": 0x34,
        "5": 0x35,
        "6": 0x36,
        "7": 0x37,
        "8": 0x38,
        "9": 0x39,
        "f1": 0x70,
        "f2": 0x71,
        "f3": 0x72,
        "f4": 0x73,
        "f5": 0x74,
        "f6": 0x75,
        "f7": 0x76,
        "f8": 0x77,
        "f9": 0x78,
        "f10": 0x79,
        "f11": 0x7A,
        "f12": 0x7B,
        "enter": 0x0D,
        "return": 0x0D,
        "esc": 0x1B,
        "escape": 0x1B,
        "tab": 0x09,
        "space": 0x20,
        "backspace": 0x08,
        "delete": 0x2E,
        "insert": 0x2D,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "up": 0x26,
        "down": 0x28,
        "left": 0x25,
        "right": 0x27,
        ".": 0xBE,
        ",": 0xBC,
        " ": 0x20,
        ";": 0xBA,
        "'": 0xDE,
        "[": 0xDB,
        "]": 0xDD,
        "\\": 0xDC,
        "/": 0xBF,
        "-": 0xBD,
        "=": 0xBB,
        "`": 0xC0,
    }

    MODIFIER_MAP: dict[str, int] = {
        "ctrl": win32con.VK_CONTROL,
        "control": win32con.VK_CONTROL,
        "alt": win32con.VK_MENU,
        "shift": win32con.VK_SHIFT,
        "win": win32con.VK_LWIN,
        "meta": win32con.VK_LWIN,
    }

    _MOUSE_DOWN: dict[MouseButton, int] = {
        MouseButton.LEFT: win32con.MOUSEEVENTF_LEFTDOWN,
        MouseButton.RIGHT: win32con.MOUSEEVENTF_RIGHTDOWN,
        MouseButton.MIDDLE: win32con.MOUSEEVENTF_MIDDLEDOWN,
    }
    _MOUSE_UP: dict[MouseButton, int] = {
        MouseButton.LEFT: win32con.MOUSEEVENTF_LEFTUP,
        MouseButton.RIGHT: win32con.MOUSEEVENTF_RIGHTUP,
        MouseButton.MIDDLE: win32con.MOUSEEVENTF_MIDDLEUP,
    }

    _SHIFT_CHARS: set[str] = set('~!@#$%^&*()_+{}|:"<>?')
    _SHIFT_TO_BASE: dict[str, str] = {
        "~": "`",
        "!": "1",
        "@": "2",
        "#": "3",
        "$": "4",
        "%": "5",
        "^": "6",
        "&": "7",
        "*": "8",
        "(": "9",
        ")": "0",
        "_": "-",
        "+": "=",
        "{": "[",
        "}": "]",
        "|": "\\",
        ":": ";",
        '"': "'",
        "<": ",",
        ">": ".",
        "?": "/",
    }

    def __init__(self, type_delay: float = 0.01) -> None:
        self._type_delay = type_delay

    # -- Mouse ----------------------------------------------------------------

    def move(self, x: int, y: int) -> None:
        """Move mouse cursor to absolute screen position (x, y)."""
        win32api.SetCursorPos((x, y))

    def _resolve_button(self, button: str) -> MouseButton:
        try:
            return MouseButton(button)
        except ValueError as err:
            valid = ", ".join(b.value for b in MouseButton)
            raise ValueError(f"Unknown button: {button!r}. Valid buttons: {valid}") from err

    def click(self, button: str = "left") -> None:
        """Click a mouse button at the current cursor position."""
        btn = self._resolve_button(button)
        win32api.mouse_event(self._MOUSE_DOWN[btn] | self._MOUSE_UP[btn], 0, 0, 0, 0)

    def left_click(self) -> None:
        """Left-click at the current cursor position."""
        self.click("left")

    def right_click(self) -> None:
        """Right-click at the current cursor position."""
        self.click("right")

    def double_click(self) -> None:
        """Double left-click at the current cursor position."""
        btn = MouseButton.LEFT
        flags = self._MOUSE_DOWN[btn] | self._MOUSE_UP[btn]
        win32api.mouse_event(flags, 0, 0, 0, 0)
        win32api.mouse_event(flags, 0, 0, 0, 0)

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        """Drag from (start_x, start_y) to (end_x, end_y)."""
        btn = MouseButton.LEFT
        self.move(start_x, start_y)
        win32api.mouse_event(self._MOUSE_DOWN[btn], 0, 0, 0, 0)
        self.move(end_x, end_y)
        win32api.mouse_event(self._MOUSE_UP[btn], 0, 0, 0, 0)

    def scroll(self, delta_x: int = 0, delta_y: int = 1) -> None:
        """Scroll the mouse wheel. Positive delta_y = up."""
        if delta_y:
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, delta_y * 120, 0)
        if delta_x:
            win32api.mouse_event(win32con.MOUSEEVENTF_HWHEEL, 0, 0, delta_x * 120, 0)

    def get_cursor_position(self) -> tuple[int, int]:
        """Return the current cursor position as (x, y)."""
        return win32api.GetCursorPos()

    # -- Keyboard -------------------------------------------------------------

    def _resolve_key(self, key: str) -> int:
        key_lower = key.lower()
        if key_lower in self.VK_MAP:
            return self.VK_MAP[key_lower]
        raise ValueError(f"Unknown key: {key!r}. Use a letter, digit, or a named key (e.g. 'enter', 'tab', 'f1').")

    def key_down(self, key: str) -> None:
        """Press and hold a key. Must pair with key_up()."""
        vk = self._resolve_key(key)
        win32api.keybd_event(vk, 0, 0, 0)

    def key_up(self, key: str) -> None:
        """Release a held key."""
        vk = self._resolve_key(key)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    def _type_char(self, char: str) -> None:
        needs_shift = char.isupper() or char in self._SHIFT_CHARS
        base = self._SHIFT_TO_BASE.get(char, char)
        vk = self._resolve_key(base.lower())
        if needs_shift:
            win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        if needs_shift:
            win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)

    def type(self, text: str) -> None:
        """Type a string of text at the current focus position."""
        for char in text:
            self._type_char(char)
            time.sleep(self._type_delay)

    def press_key(self, key: str, modifiers: list[str] | None = None) -> None:
        """Press a key combination (e.g., Ctrl+C, Alt+Tab)."""
        mods = modifiers or []
        for mod in mods:
            mod_lower = mod.lower()
            if mod_lower not in self.MODIFIER_MAP:
                valid = ", ".join(self.MODIFIER_MAP)
                raise ValueError(f"Unknown modifier: {mod!r}. Valid: {valid}")
            win32api.keybd_event(self.MODIFIER_MAP[mod_lower], 0, 0, 0)
        vk = self._resolve_key(key)
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        for mod in reversed(mods):
            win32api.keybd_event(
                self.MODIFIER_MAP[mod.lower()],
                0,
                win32con.KEYEVENTF_KEYUP,
                0,
            )

    # -- Screen ---------------------------------------------------------------

    def screenshot(self, path: str | None = None) -> Image.Image:
        """Take a screenshot of the primary monitor."""
        img = ImageGrab.grab()
        if path:
            img.save(path)
        return img

    def get_screen_size(self) -> tuple[int, int]:
        """Return the (width, height) of the primary monitor."""
        return (
            win32api.GetSystemMetrics(win32con.SM_CXSCREEN),
            win32api.GetSystemMetrics(win32con.SM_CYSCREEN),
        )

    def get_pixel_color(self, x: int, y: int) -> tuple[int, int, int]:
        """Return the (R, G, B) color of the pixel at (x, y)."""
        hdc = win32gui.GetDC(0)
        try:
            color = win32gui.GetPixel(hdc, x, y)
        finally:
            win32gui.ReleaseDC(0, hdc)
        return (color & 0xFF, (color >> 8) & 0xFF, (color >> 16) & 0xFF)
