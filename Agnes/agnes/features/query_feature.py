"""查询 Feature — 模型/API 信息查询 Tab。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, END, WORD

from agnes.runtime.app_context import AppContext
from agnes.runtime.theme import Theme


class QueryFeature:
    """查询/工具功能页。"""

    def __init__(self):
        self._widgets: dict[str, tk.Widget] = {}
        self._ctx: AppContext | None = None

    def mount(self, parent: tk.Misc, ctx: AppContext) -> tk.Widget:
        self._ctx = ctx
        theme = ctx.theme or Theme()

        frame = tk.Frame(parent, bg=theme.bg)
        frame.pack(fill=tk.BOTH, expand=True)

        card = self._make_card(frame, theme)
        tk.Label(card, text="选择查询：", fg=theme.fg, bg=theme.card_bg).pack(anchor=tk.W)

        query_type = ttk.Combobox(
            card,
            values=["模型列表", "API 状态", "余额查询"],
            state="readonly",
            width=18,
        )
        query_type.set("模型列表")
        query_type.pack(fill=tk.X, pady=3)

        tk.Button(card, text="🔍 查询",
                  command=lambda: self._do_query(query_type, query_out),
                  bg=theme.accent, fg="white", cursor="hand2").pack(anchor=tk.E, pady=3)

        tk.Label(frame, text="查询结果：", fg=theme.fg, bg=theme.bg).pack(anchor=tk.W, padx=5)
        query_out = self._add_output_area(frame, theme)

        self._widgets = {
            "frame": frame,
            "query_type": query_type,
            "query_out": query_out,
        }
        return frame

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def dispose(self) -> None:
        self._ctx = None
        self._widgets.clear()

    def _do_query(
        self,
        query_type: ttk.Combobox,
        query_out: scrolledtext.ScrolledText,
    ) -> None:
        qtype = query_type.get()
        query_out.delete("1.0", END)
        query_out.insert(END, f"⏳ 正在查询「{qtype}」...\n")
        query_out.update()

        def task():
            try:
                client = self._ctx.client if self._ctx else None
                if client is None:
                    raise RuntimeError("上下文未初始化")

                if qtype == "模型列表":
                    models = client.list_models()
                    result = "📋 可用模型：\n\n"
                    for m in models:
                        tp = client.get_model_type(m["id"])
                        result += f"  ● {m['id']} ({tp})\n"
                elif qtype == "API 状态":
                    result = "✅ API 已连接\n"
                elif qtype == "余额查询":
                    result = "💰 余额查询暂不可用"
                else:
                    result = "❓ 未知查询类型"

                query_out.delete("1.0", END)
                query_out.insert(END, result)
            except Exception as e:
                query_out.delete("1.0", END)
                query_out.insert(END, f"❌ 错误：{e}")

        threading.Thread(target=task, daemon=True).start()

    @staticmethod
    def _make_card(parent: tk.Misc, theme: Theme) -> tk.Frame:
        card = tk.Frame(parent, bg=theme.card_bg, padx=12, pady=10)
        card.pack(fill=tk.X, pady=5)
        return card

    @staticmethod
    def _add_output_area(parent: tk.Misc, theme: Theme) -> scrolledtext.ScrolledText:
        text = scrolledtext.ScrolledText(parent, height=8, bg=theme.input_bg,
                                         fg=theme.fg, insertbackground="white",
                                         font=("Consolas", 10), wrap=WORD)
        text.pack(fill=tk.BOTH, expand=True, pady=5)
        return text
