"""CRUX 配色烟雾测试 — 独立进程，避开 event loop 冲突"""

from prompt_toolkit import Application
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.output.color_depth import ColorDepth
from prompt_toolkit.styles import Style

style = Style.from_dict(
    {
        "": "fg:#E2E8F0 bg:#0B0E14",
        "app": "fg:#E2E8F0 bg:#0B0E14",
    }
)

root = HSplit(
    [
        Window(
            content=FormattedTextControl([("class:app", "  CRUX 刀阵 Blade Formation")]), style="class:app", height=1
        ),
        Window(
            content=FormattedTextControl([("class:app", "  bg:#0B0E14 — 深色=Style正常，白色=输出问题")]),
            style="class:app",
            height=1,
        ),
        Window(content=FormattedTextControl([("class:app", "  Ctrl+C 退出")]), style="class:app", height=1),
    ],
    style="class:app",
)

app = Application(
    layout=Layout(root),
    style=style,
    full_screen=True,
    mouse_support=False,
    color_depth=ColorDepth.TRUE_COLOR,
)

app.run()
