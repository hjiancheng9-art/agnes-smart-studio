"""披风 · 隐私隐身 — request sanitization & privacy guard.
Strips API keys from logs. Masks email/phone/ip in output.
Session traces anonymized before persistence.
Usage: from core.intimate_slots.cloak import cloak
cloak.sanitize(text)
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


class PrivacyCloak:
    def __init__(self):
        self._patterns = {
            "api_key": (r"(sk-|Bearer\s+)[A-Za-z0-9_-]{20,}", r"\1***REDACTED***"),
            "email": (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "***@***.***"),
            "phone_cn": (r"1[3-9]\d{9}", "1**********"),
            "ip": (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "***.***.***.***"),
            "jwt": (r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "***JWT***"),
        }

    def sanitize(self, text: str) -> str:
        """Strip all sensitive patterns from text."""
        for name, (pattern, replacement) in self._patterns.items():
            if re.search(pattern, text):
                text = re.sub(pattern, replacement, text)
                logger.debug("[披风] redacted %s", name)
        return text

    def sanitize_dict(self, data: dict) -> dict:
        """Recursively sanitize all string values in a dict."""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                result[k] = self.sanitize(v)
            elif isinstance(v, dict):
                result[k] = self.sanitize_dict(v)
            elif isinstance(v, list):
                result[k] = [self.sanitize(x) if isinstance(x, str) else x for x in v]
            else:
                result[k] = v
        return result

    def wrap(self, text: str) -> str:
        """Full privacy wrap: sanitize + add metadata marker."""
        return f"[PRIVACY_WRAPPED] {self.sanitize(text)}"

    def summary(self) -> str:
        patterns = list(self._patterns.keys())
        return f"[披风] guarding: {', '.join(patterns)}"


cloak = PrivacyCloak()
