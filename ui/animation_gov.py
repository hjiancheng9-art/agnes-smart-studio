"""
CRUX TUI v2 — Animation Governance
===================================
Implements debate consensus: max 1 animation at a time,
disable during streaming, 24fps cap, auto-disable on SSH.

Rules:
    1. Only ONE animation element active at any time
    2. ALL non-essential animations OFF during streaming output
    3. ALL animations OFF in SSH/tmux environments
    4. Global frame rate cap: 24fps
    5. Spinner has priority over decorative animations
"""

from __future__ import annotations

import threading
import time
from enum import Enum, auto


class AnimType(Enum):
    """Animation element types, ordered by priority (lower = higher priority)."""

    SPINNER = auto()  # highest priority - shows activity
    PROGRESS_BAR = auto()  # task progress
    THINKING_FOLD = auto()  # thinking panel expand/collapse
    PULSE_TEXT = auto()  # pulse/flash (deprecated per debate)
    ANIMATED_BORDER = auto()  # decorative border (optional per debate)


# Animation priority: lower number = higher priority
ANIM_PRIORITY = {
    AnimType.SPINNER: 0,
    AnimType.PROGRESS_BAR: 1,
    AnimType.THINKING_FOLD: 2,
    AnimType.PULSE_TEXT: 3,
    AnimType.ANIMATED_BORDER: 4,
}


class AnimationGovernor:
    """
    Central animation controller.

    Ensures:
    - Only 1 animation active at a time
    - Animations disabled during streaming
    - Frame rate cap at 24fps
    - Auto-disable on SSH
    """

    # Target frame rate (per debate: 24fps)
    FRAME_INTERVAL = 1.0 / 24.0  # ~41.7ms

    def __init__(self, ssh_mode: bool = False):
        self._ssh_mode = ssh_mode
        self._streaming = False
        self._active: AnimType | None = None
        self._active_lock = threading.Lock()
        self._frame_count = 0
        self._last_frame_time = 0.0
        self._enabled = not ssh_mode

    # ── Public API ────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled and not self._ssh_mode

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value and not self._ssh_mode
        if not self._enabled:
            self._active = None

    @property
    def streaming(self) -> bool:
        return self._streaming

    @streaming.setter
    def streaming(self, value: bool):
        """When streaming starts, kill all decorative animations."""
        self._streaming = value
        if value and self._active not in (None, AnimType.SPINNER, AnimType.PROGRESS_BAR):
            self._active = None

    def can_animate(self, anim_type: AnimType) -> bool:
        """
        Check whether an animation of given type can start.

        Rules:
        1. If animations globally disabled → False
        2. If streaming and anim is not SPINNER/PROGRESS_BAR → False
        3. If another animation is active and has higher priority → False
        4. Otherwise → True (kicks the lower-priority one)
        """
        if not self.enabled:
            return False

        if self._streaming and anim_type not in (AnimType.SPINNER, AnimType.PROGRESS_BAR):
            return False

        with self._active_lock:
            if self._active is None:
                return True

            my_priority = ANIM_PRIORITY.get(anim_type, 99)
            active_priority = ANIM_PRIORITY.get(self._active, 99)

            return my_priority <= active_priority

    def start(self, anim_type: AnimType) -> bool:
        """Try to start an animation. Returns True if started."""
        if not self.can_animate(anim_type):
            return False

        with self._active_lock:
            self._active = anim_type

        self._last_frame_time = time.monotonic()
        return True

    def stop(self, anim_type: AnimType):
        """Stop an animation if it's the active one."""
        with self._active_lock:
            if self._active == anim_type:
                self._active = None

    def stop_all(self):
        """Stop all animations."""
        with self._active_lock:
            self._active = None

    def should_frame(self) -> bool:
        """Check if enough time has passed for next frame (24fps cap)."""
        now = time.monotonic()
        if now - self._last_frame_time >= self.FRAME_INTERVAL:
            self._last_frame_time = now
            self._frame_count += 1
            return True
        return False

    @property
    def active_type(self) -> AnimType | None:
        return self._active

    # ── Convenience methods ───────────────────────────

    def can_spin(self) -> bool:
        return self.can_animate(AnimType.SPINNER)

    def can_decorate(self) -> bool:
        """Whether decorative animations (border, pulse) are allowed."""
        return self.can_animate(AnimType.ANIMATED_BORDER) and not self._streaming

    def is_active(self, anim_type: AnimType) -> bool:
        return self._active == anim_type
