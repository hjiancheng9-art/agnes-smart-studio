"""识图 Feature — 图片识别 Tab。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, END, WORD

from agnes.features.base import Feature
from agnes.runtime.app_context import AppContext
from agnes.runtime.theme import Theme


class VisionFeature:
    """图片识别功能页。"""

    def __init__(self):
        self._widgets: dict[str, tk.Widget] = {}
        self._ctx: AppContext | None = None

    def mount(self, parent: tk.Misc, ctx: AppContext) -> tk.Widget:
        self._ctx = ctx
        theme = ctx.theme or Theme()

        frame = tk.Frame(parent, bg=theme.bg)
        frame.pack(fill=tk.BOTH, expand=True)

        card = self._make_card(frame, theme)
        tk.Label(card, text="图片文件：", fg=theme.fg, bg=theme.card_bg).pack(anchor=tk.W)
        row = tk.Frame(card, bg=theme.card_bg)
        row.pack(fill=tk.X, pady=3)
        vision_path = tk.Entry(row, bg=theme.input_bg, fg=theme.fg,
                               insertbackground="white")
        vision_path.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def browse():
            path = filedialog.askopenfilename(
                filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")]
            )
            if path:
                vision_path.delete(0, END)
                vision_path.insert(0, path)

        tk.Button(row, text="浏览", command=browse,
                  bg=theme.card_bg, fg="white", cursor="hand2").pack(side=tk.LEFT, padx=5)

        tk.Label(card, text="问题：", fg=theme.fg, bg=theme.card_bg).pack(anchor=tk.W, pady=(8, 0))
        vision_input = tk.Entry(card, bg=theme.input_bg, fg=theme.fg,
                                insertbackground="white")
        vision_input.insert(0, "请描述这张图片")
        vision_input.pack(fill=tk.X, pady=3)

        tk.Button(card, text="🚀 识别",
                  command=lambda: self._do_vision(vision_path, vision_input, vision_out),
                  bg=theme.accent, fg="white", cursor="hand2").pack(anchor=tk.E)

        tk.Label(frame, text="识别结果：", fg=theme.fg, bg=theme.bg).pack(anchor=tk.W, padx=5)
        vision_out = self._add_output_area(frame, theme)

        self._widgets = {
            "frame": frame,
            "vision_path": vision_path,
            "vision_input": vision_input,
            "vision_out": vision_out,
        }
        return frame

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def dispose(self) -> None:
        self._ctx = None
        self._widgets.clear()

    def _do_chat(
        self,
        vision_path: tk.Entry,
        vision_input: tk.Entry,
        vision_out: scrolledtext.ScrolledText,
    ) -> None:
        img = vision_path.get().strip()
        prompt = vision_input.get().strip()
        if not img:
            messagebox.showwarning("提示", "请选择图片文件")
            return
        if not prompt:
            messagebox.showwarning("提示", "请输入问题")
            return

        vision_out.delete("1.0", END)
        vision_out.insert(END, "⏳ 正在识别...\n")
        vision_out.update()

        def task():
            try:
                client = self._ctx.client if self._ctx else None
                if client is None:
                    raise RuntimeError("上下文未初始化")
                reply = client.chat_with_image(prompt, img, model="agnes-2.0-flash")
                vision_out.delete("1.0", END)
                vision_out.insert(END, reply)
            except Exception as e:
                vision_out.delete("1.0", END)
                vision_out.insert(END, f"❌ 错误：{e}")

        threading.Thread(target=task, daemon=True).start()

    _do_vision = _do_chat  # alias for backward compat naming

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
