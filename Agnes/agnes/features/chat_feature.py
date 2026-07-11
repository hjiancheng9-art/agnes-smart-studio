"""对话 Feature — 文本对话 Tab。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, END, WORD

from agnes.features.base import Feature
from agnes.runtime.app_context import AppContext
from agnes.runtime.theme import Theme


class ChatFeature:
    """文本对话功能页。"""

    def __init__(self):
        self._widgets: dict[str, tk.Widget] = {}
        self._ctx: AppContext | None = None

    # ---- Feature protocol ----

    def mount(self, parent: tk.Misc, ctx: AppContext) -> tk.Widget:
        self._ctx = ctx
        theme = ctx.theme or Theme()

        frame = tk.Frame(parent, bg=theme.bg)
        frame.pack(fill=tk.BOTH, expand=True)

        # 输入区
        card = self._make_card(frame, theme)
        tk.Label(card, text="输入内容：", fg=theme.fg, bg=theme.card_bg,
                 font=("微软雅黑", 10)).pack(anchor=tk.W)
        chat_input = tk.Text(card, height=3, bg=theme.input_bg, fg=theme.fg,
                             insertbackground="white", font=("微软雅黑", 10))
        chat_input.pack(fill=tk.X, pady=3)

        # 参数
        opt = tk.Frame(card, bg=theme.card_bg)
        opt.pack(fill=tk.X, pady=3)
        tk.Label(opt, text="模型：", fg=theme.fg, bg=theme.card_bg).pack(side=tk.LEFT)
        chat_model = ttk.Combobox(opt, values=["agnes-2.0-flash", "agnes-1.5-flash"],
                                  width=18, state="readonly")
        chat_model.set("agnes-2.0-flash")
        chat_model.pack(side=tk.LEFT, padx=5)

        chat_thinking = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="深度思考", variable=chat_thinking).pack(side=tk.LEFT, padx=10)

        tk.Button(card, text="🚀 发送",
                  command=lambda: self._do_chat(chat_input, chat_model, chat_thinking, chat_out),
                  bg=theme.accent, fg="white", cursor="hand2").pack(anchor=tk.E, pady=3)

        # 输出区
        tk.Label(frame, text="回复：", fg=theme.fg, bg=theme.bg,
                 font=("微软雅黑", 10)).pack(anchor=tk.W, padx=5)
        chat_out = self._add_output_area(frame, theme)
        chat_out.insert(tk.END, "🎨 欢迎使用 Agnes AI！\n在下方输入框中输入内容，开始对话吧 🚀\n\n")

        self._widgets = {
            "frame": frame,
            "chat_input": chat_input,
            "chat_model": chat_model,
            "chat_thinking": chat_thinking,
            "chat_out": chat_out,
        }
        return frame

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def dispose(self) -> None:
        self._ctx = None
        self._widgets.clear()

    # ---- 内部方法 ----

    def _do_chat(
        self,
        chat_input: tk.Text,
        chat_model: ttk.Combobox,
        chat_thinking: tk.BooleanVar,
        chat_out: scrolledtext.ScrolledText,
    ) -> None:
        prompt = chat_input.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("提示", "请输入对话内容")
            return
        chat_out.delete("1.0", END)
        chat_out.insert(END, "⏳ 正在生成回复...\n")
        chat_out.update()

        def task():
            try:
                client = self._ctx.client if self._ctx else None
                if client is None:
                    raise RuntimeError("上下文未初始化")
                reply = client.chat_text(
                    prompt,
                    model=chat_model.get(),
                    thinking=chat_thinking.get(),
                )
                chat_out.delete("1.0", END)
                chat_out.insert(END, reply)
            except Exception as e:
                chat_out.delete("1.0", END)
                chat_out.insert(END, f"❌ 错误：{e}")

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
