"""Pure routing/model helpers for ChatSession (refactor P2).

Side-effect-free classification helpers extracted from core/chat.py so they
can be unit-tested independently. ChatSession keeps thin wrappers for
backward compatibility. Stateful routing (_auto_route, provider/model
switching) intentionally stays in ChatSession — it mutates session state.
"""

from __future__ import annotations

import re

# Vision-complexity keyword signatures (Chinese + English). A hit means the
# request likely needs a stronger vision model / larger token budget.
_COMPLEX_RE = re.compile(
        r"(数一数|多少个|计数|count|how many)|"
        r"(代码|code|函数|function|class |import |def )|"
        r"(图表|graph|chart|柱状|饼图|折线|scatter|bar chart)|"
        r"(对比|区别|差异|difference|compare|diff)|"
        r"(计算|算一算|calculate|compute|面积|周长|角度)|"
        r"(推理|推断|infer|deduce|逻辑|logical)|"
        r"(流程|flowchart|架构|architecture|拓扑|topology)|"
        r"(详细分析|深入|逐步|step.by.step|explain in detail)|"
        r"(公式|equation|math|数学)",
    re.IGNORECASE,
)

# Prefixes that mark a streamed buffer as a transport/API failure rather
# than assistant text.
_STREAM_ERROR_PREFIXES = ("[流中断", "[HTTP ")


def classify_vision_complexity(text: str) -> tuple[str, int]:
    """Classify a vision request as light vs complex.

    Returns (tier, max_tokens):
    - ("light", 2048)   OCR / description / simple Q&A
    - ("complex", 4096) code / reasoning / charts / compare / multi-step
    """
    if _COMPLEX_RE.search(text):
        return ("complex", 4096)
    return ("light", 2048)


def is_stream_error(buffer: str) -> bool:
    """Whether a streamed buffer looks like a transport/API error.

    Uses strict prefix matching so ordinary user text that merely contains
    these substrings does not false-trigger.
    """
    if not buffer:
        return False
    return buffer.startswith(_STREAM_ERROR_PREFIXES)
