"""
CRUX TUI v2 — Markdown Renderer with Pygments Caching
=======================================================
Per 3-platform debate conclusions (R6):
- Only support AI programming's most-used 20% Markdown
- Code block caching via Pygments with LRU
- Language auto-detection from code block annotation
- Flow output: render by block, not char-by-char
- CJK width aware
- No table/math/HTML/image support

Markdown subset:
    P0: Headers (# ## ###), Lists (- * 1.), Code blocks (```), Blockquotes (>)
    P1: Bold (**), Italic (*), Inline code (`), Links [text](url)
    P2: Tables (degrade to text)
    N/A: Math, HTML, Images
"""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

# ── Pygments Token → prompt_toolkit style mapping ─────────

_PYGMENTS_STYLE_MAP: dict[Any, str] = {}

def _init_style_map():
    """Lazy-init Pygments token style map to avoid import overhead."""
    if _PYGMENTS_STYLE_MAP:
        return
    try:
        from pygments.token import Token
        _PYGMENTS_STYLE_MAP.update({
            Token.Keyword: "bold fg:#cba6f7",
            Token.Keyword.Constant: "fg:#cba6f7",
            Token.Keyword.Declaration: "bold fg:#cba6f7",
            Token.Keyword.Namespace: "bold fg:#cba6f7",
            Token.Keyword.Type: "bold fg:#89b4fa",
            Token.Name.Function: "fg:#89b4fa",
            Token.Name.Class: "bold fg:#f2cdcd",
            Token.Name.Decorator: "fg:#f2cdcd",
            Token.Name.Builtin: "fg:#89b4fa",
            Token.Name.Constant: "fg:#fab387",
            Token.String: "fg:#a6e3a1",
            Token.String.Doc: "italic fg:#a6e3a1",
            Token.Number: "fg:#fab387",
            Token.Operator: "fg:#94e2d5",
            Token.Comment: "italic fg:#585b70",
            Token.Comment.Special: "bold fg:#585b70",
            Token.Punctuation: "fg:#cdd6f4",
            Token.Text: "",
        })
    except ImportError:
        pass


def _pygments_token_style(ttype: Any) -> str:
    """Look up prompt_toolkit style for a Pygments token type."""
    _init_style_map()
    style = _PYGMENTS_STYLE_MAP.get(ttype)
    if style is not None:
        return style
    if ttype.parent:
        return _PYGMENTS_STYLE_MAP.get(ttype.parent, "")
    return ""


# ── LRU Cache ──────────────────────────────────────────────

class PygmentsCache:
    """LRU cache for syntax-highlighted code blocks."""
    def __init__(self, maxsize: int = 64):
        self._cache: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> list[tuple[str, str]] | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value: list[tuple[str, str]]):
        self._cache[key] = value
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def highlight(self, code: str, lang: str = "") -> list[tuple[str, str]]:
        """
        Highlight code block via Pygments tokens → prompt_toolkit styles.
        Falls back to plain text if Pygments unavailable or lang unknown.
        """
        cache_key = f"{lang}:{hash(code)}"
        cached = self.get(cache_key)
        if cached:
            return cached

        try:
            from pygments.lexers import get_lexer_by_name, guess_lexer
            from pygments.util import ClassNotFound

            if lang:
                try:
                    lexer = get_lexer_by_name(lang, stripall=True)
                except ClassNotFound:
                    lexer = None
            else:
                lexer = None

            if lexer is None and len(code) > 20:
                try:
                    lexer = guess_lexer(code)
                except ClassNotFound:
                    lexer = None

            if lexer:
                result = []
                for ttype, value in lexer.get_tokens(code):
                    style = _pygments_token_style(ttype)
                    if value:
                        result.append((style, value))
            else:
                result = [("", code)]

        except ImportError:
            result = [("", code)]

        self.set(cache_key, result)
        return result


# ── Global cache instance ──────────────────────────────────

_cache = PygmentsCache(maxsize=64)


# ── Markdown block parsing ─────────────────────────────────

def _parse_code_blocks(text: str) -> list[tuple[str, str]]:
    """
    Split text into code blocks and non-code segments.
    Returns [(tag, content)] where tag is 'code' or 'text'.
    """
    segments: list[tuple[str, str]] = []
    pattern = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
    last_end = 0

    for match in pattern.finditer(text):
        lang = match.group(1).strip()
        code = match.group(2)

        # Text before this code block
        if match.start() > last_end:
            segments.append(("text", text[last_end:match.start()]))

        # The code block
        highlighted = _cache.highlight(code, lang)
        segments.append(("code_block", highlighted))
        last_end = match.end()

    # Remaining text after last code block
    if last_end < len(text):
        segments.append(("text", text[last_end:]))

    return segments


def _render_inline(text: str) -> list[tuple[str, str]]:
    """
    Render inline Markdown elements (bold, italic, code, links).
    Returns [(style_class, fragment), ...] for prompt_toolkit.

    Processing order:
        1. Inline code `...`
        2. Links [text](url)
        3. Bold **...**
        4. Italic *...*
    """
    result: list[tuple[str, str]] = []
    pos = 0

    # Combined pattern: code > link > bold > italic
    # Process in order of priority to avoid conflicts
    patterns = [
        (r'`([^`]+)`', 'class:msg-assistant'),           # inline code
        (r'\[([^\]]+)\]\(([^)]+)\)', 'class:msg-assistant underline'),  # link
        (r'\*\*([^*]+)\*\*', 'bold'),                     # bold
        (r'\*([^*]+)\*', 'italic'),                       # italic
    ]

    while pos < len(text):
        best_match = None
        best_start = len(text)

        for pat, style in patterns:
            match = re.search(pat, text[pos:])
            if match:
                abs_start = pos + match.start()
                if abs_start < best_start:
                    best_start = abs_start
                    best_match = (match, pat, style)

        if best_match is None:
            # Plain text
            remaining = text[pos:]
            if remaining.strip():
                result.append(("", remaining))
            break

        match, _, style = best_match
        abs_start = pos + match.start()

        # Text before this formatted element
        if abs_start > pos:
            before = text[pos:abs_start]
            if before.strip():
                result.append(("", before))

        # The formatted element itself
        if style.startswith('class:'):
            # Link style: show label, hide URL
            if '(' in match.group(0):
                label = match.group(1)
                result.append((style, label))
            else:
                result.append((style, match.group(1)))
        else:
            result.append((style, match.group(1)))

        pos = abs_start + match.end()

    return result


def _render_block(text: str, width: int = 80) -> list[tuple[str, str]]:
    """
    Render a single block of text (paragraph, header, list item, quote).
    Returns [(style, fragment), ...] for prompt_toolkit.
    """
    stripped = text.strip()
    if not stripped:
        return [("", "")]

    # Header
    if stripped.startswith('#'):
        level = len(stripped) - len(stripped.lstrip('#'))
        content = stripped.lstrip('#').strip()
        if level == 1:
            return [("class:msg-assistant bold underline", content)]
        elif level == 2:
            return [("class:msg-assistant bold", content)]
        else:
            return [("class:msg-assistant bold", content)]

    # Blockquote
    if stripped.startswith('>'):
        content = stripped.lstrip('>').strip()
        return _render_inline(content)

    # List item
    if re.match(r'^[\s]*[-*+]\s', stripped) or re.match(r'^[\s]*\d+[.)]\s', stripped):
        return _render_inline(stripped)

    # Code block indicator line (```) — skip silently
    if stripped.startswith('```'):
        return []

    # Regular paragraph
    return _render_inline(stripped)


# ── Public API ─────────────────────────────────────────────

def render_markdown(text: str, width: int = 80) -> list[tuple[str, str]]:
    """
    Render Markdown text to prompt_toolkit formatted text fragments.

    Args:
        text: Raw markdown string
        width: Terminal width for wrapping (unused currently)

    Returns:
        List of (style, fragment) tuples for FormattedText
    """
    # Split into code blocks and non-code
    segments = _parse_code_blocks(text)
    result: list[tuple[str, str]] = []

    for tag, content in segments:
        if tag == "code_block":
            # Pre-formatted highlighted code fragments
            if isinstance(content, list):
                result.extend(content)
            result.append(("", "\n"))
        else:
            # Text content — split into blocks and render each
            blocks = content.split('\n')
            for block in blocks:
                rendered = _render_block(block, width)
                result.extend(rendered)
                result.append(("", "\n"))

    return result


def clear_cache():
    """Clear the Pygments syntax cache."""
    _cache._cache.clear()
