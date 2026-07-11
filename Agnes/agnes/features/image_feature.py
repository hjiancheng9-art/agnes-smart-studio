"""图片生成 Feature — 文生图 Tab。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, END, WORD

from agnes.runtime.app_context import AppContext
from agnes.runtime.theme import Theme


class ImageFeature:
    """图片生成功能页。"""

    def __init__(self):
        self._widgets: dict[str, tk.Widget] = {}
        self._ctx: AppContext | None = None

    def mount(self, parent: tk.Misc, ctx: AppContext) -> tk.Widget:
        self._ctx = ctx
        theme = ctx.theme or Theme()

        frame = tk.Frame(parent, bg=theme.bg)
        frame.pack(fill=tk.BOTH, expand=True)

        card = self._make_card(frame, theme)
        tk.Label(card, text="描述图片内容：", fg=theme.fg, bg=theme.card_bg).pack(anchor=tk.W)
        img_input = tk.Text(card, height=3, bg=theme.input_bg, fg=theme.fg,
                            insertbackground="white", font=("微软雅黑", 10))
        img_input.pack(fill=tk.X, pady=3)

        opt = tk.Frame(card, bg=theme.card_bg)
        opt.pack(fill=tk.X, pady=3)
        tk.Label(opt, text="尺寸：", fg=theme.fg, bg=theme.card_bg).pack(side=tk.LEFT)
        img_size = ttk.Combobox(opt, values=["1024x1024", "1024x768", "768x1024",
                                             "576x1024", "1024x576"],
                                width=12, state="readonly")
        img_size.set("1024x1024")
        img_size.pack(side=tk.LEFT, padx=5)

        tk.Button(card, text="🎨 生成",
                  command=lambda: self._do_image(img_input, img_size, img_out),
                  bg=theme.accent, fg="white", cursor="hand2").pack(anchor=tk.E, pady=3)

        tk.Label(frame, text="生成结果：", fg=theme.fg, bg=theme.bg).pack(anchor=tk.W, padx=5)
        img_out = self._add_output_area(frame, theme)

        self._widgets = {
            "frame": frame,
            "img_input": img_input,
            "img_size": img_size,
            "img_out": img_out,
        }
        return frame

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def dispose(self) -> None:
        self._ctx = None
        self._widgets.clear()

    def _do_image(
        self,
        img_input: tk.Text,
        img_size: ttk.Combobox,
        img_out: scrolledtext.ScrolledText,
    ) -> None:
        prompt = img_input.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("提示", "请输入图片描述")
            return

        img_out.delete("1.0", END)
        img_out.insert(END, "⏳ 正在生成图片...\n")
        img_out.update()

        def task():
            try:
                client = self._ctx.client if self._ctx else None
                if client is None:
                    raise RuntimeError("上下文未初始化")
                result = client.generate_image(prompt, size=img_size.get())
                img_out.delete("1.0", END)
                if isinstance(result, list):
                    lines = ["✅ 图片生成成功！"]
                    for i, r in enumerate(result):
                        url = r.get("url", str(r))
                        lines.append(f"  [{i+1}] {url}")
                    img_out.insert(END, "\n".join(lines))
                else:
                    img_out.insert(END, f"✅ 图片生成成功！\n{result}")
            except Exception as e:
                img_out.delete("1.0", END)
                img_out.insert(END, f"❌ 错误：{e}")

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
