"""Abstract Browser interface — CDP/Playwright abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .errors import BrowserError


@dataclass
class BrowserConfig:
    """Configuration for browser automation."""

    headless: bool = True
    browser_type: str = "chromium"  # chromium | firefox | webkit
    cdp_port: int = 9222
    viewport_width: int = 1280
    viewport_height: int = 720
    timeout_ms: int = 30000


@dataclass
class BrowserResult:
    """Unified result from browser operations."""

    success: bool
    url: str = ""
    title: str = ""
    content: str = ""
    screenshot_path: str = ""
    error: BrowserError | None = None
    elapsed_ms: float = 0.0


class Browser(ABC):
    """Abstract browser — CDP and Playwright both implement this."""

    @abstractmethod
    async def navigate(self, url: str) -> BrowserResult:
        """Navigate to a URL."""
        ...

    @abstractmethod
    async def get_content(self) -> str:
        """Get the current page content."""
        ...

    @abstractmethod
    async def fill(self, selector: str, text: str) -> BrowserResult:
        """Fill a form field."""
        ...

    @abstractmethod
    async def click(self, selector: str) -> BrowserResult:
        """Click an element."""
        ...

    @abstractmethod
    async def screenshot(self, path: str) -> BrowserResult:
        """Take a screenshot."""
        ...

    @abstractmethod
    async def wait_for(self, selector: str, timeout_ms: int = 10000) -> BrowserResult:
        """Wait for an element to appear."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the browser."""
        ...
