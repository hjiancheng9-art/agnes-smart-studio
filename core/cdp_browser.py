"""Compatibility shim — redirects to core.browser_runtime.

This module name is kept for backward compatibility.
New code should import from core.browser_runtime directly.
"""

from core.browser_runtime import *  # noqa: F403
