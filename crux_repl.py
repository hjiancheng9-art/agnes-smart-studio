"""CRUX 纯文本 REPL — 无 TUI，无 prompt_toolkit，无鼠标追踪。

与 Claude Code 界面同级简约：读取输入 → 流式输出 → 工具调用 → 结果可见。
"""

import sys

from core.chat import ChatSession
from core.colors import ANSI
from core.provider import get_provider_manager


def main():
    mgr = get_provider_manager()
    client = mgr.create_client()
    model = mgr.get_model("light") or "deepseek-v4-flash"
    session = ChatSession(client, default_model=model)

    c = ANSI  # shorthand
    print(f"{c['bold']}{c['cyan']}CRUX {model}{c['reset']} {c['dim']}— 纯文本 REPL{c['reset']}")
    print(f"{c['dim']}输入消息，Ctrl+C 退出{c['reset']}\n")

    while True:
        try:
            user_input = input(f"{c['bold']}{c['green']}> {c['reset']}")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{c['dim']}再见{c['reset']}")
            break

        if not user_input.strip():
            continue

        # Start AI output with subtle color
        sys.stdout.write(c["ai"])
        for kind, payload in session.send_stream(user_input):
            if kind == "text":
                sys.stdout.write(_md_colorize(str(payload), c))
                sys.stdout.flush()
            elif kind == "info":
                sys.stdout.write(c["reset"])  # reset before info
                if not str(payload).startswith(("[1/", "[2/", "[3/", "[完成]")):
                    sys.stdout.write(f"\n  {c['info']}ℹ {payload}{c['reset']}")
                    sys.stdout.write(c["ai"])  # restore AI color
            elif kind == "error":
                sys.stdout.write(c["reset"])
                sys.stdout.write(f"\n  {c['error']}✗ {payload}{c['reset']}")
                sys.stdout.write(c["ai"])
            elif kind == "stream_start":
                pass
        sys.stdout.write(c["reset"])  # reset after stream
        print()


def _md_colorize(text: str, c: dict) -> str:
    """Apply markdown syntax highlighting with ANSI colors.

    Colorizes: **bold**, *italic*, `code`, [links](url).
    Base color c['ai'] is restored after each highlight.
    """
    import re

    # Inline code: `code`
    text = re.sub(
        r"`([^`]+)`",
        lambda m: f"{c['reset']}{c['yellow']}{m.group(1)}{c['reset']}{c['ai']}",
        text,
    )
    # Bold: **text**
    text = re.sub(
        r"\*\*([^*]+)\*\*",
        lambda m: f"{c['reset']}{c['bold']}{m.group(1)}{c['reset']}{c['ai']}",
        text,
    )
    # Italic: *text* (not **)
    text = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        lambda m: f"{c['reset']}{c['italic']}{m.group(1)}{c['reset']}{c['ai']}",
        text,
    )
    # Links: [text](url)
    text = re.sub(
        r"(?<!\x1b)\[([^\]]+)\]\([^)]+\)",
        lambda m: f"{c['reset']}{c['underline']}{c['blue']}{m.group(1)}{c['reset']}{c['ai']}",
        text,
    )
    return text


if __name__ == "__main__":
    main()
