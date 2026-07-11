"""视频生成 Feature — 文生视频 Tab。"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, END, WORD

from agnes.runtime.app_context import AppContext
from agnes.runtime.theme import Theme


class VideoFeature:
    """视频生成功能页。"""

    def __init__(self):
        self._widgets: dict[str, tk.Widget] = {}
        self._ctx: AppContext | None = None

    def mount(self, parent: tk.Misc, ctx: AppContext) -> tk.Widget:
        self._ctx = ctx
        theme = ctx.theme or Theme()

        frame = tk.Frame(parent, bg=theme.bg)
        frame.pack(fill=tk.BOTH, expand=True)

        card = self._make_card(frame, theme)
        tk.Label(card, text="描述视频内容：", fg=theme.fg, bg=theme.card_bg).pack(anchor=tk.W)
        vid_input = tk.Text(card, height=3, bg=theme.input_bg, fg=theme.fg,
                            insertbackground="white", font=("微软雅黑", 10))
        vid_input.pack(fill=tk.X, pady=3)

        opt = tk.Frame(card, bg=theme.card_bg)
        opt.pack(fill=tk.X, pady=3)
        tk.Label(opt, text="时长(秒)：", fg=theme.fg, bg=theme.card_bg).pack(side=tk.LEFT)
        vid_duration = ttk.Combobox(opt, values=["2", "3", "4", "5", "6", "8", "10"],
                                    width=6, state="readonly")
        vid_duration.set("5")
        vid_duration.pack(side=tk.LEFT, padx=5)

        tk.Label(opt, text="尺寸：", fg=theme.fg, bg=theme.card_bg).pack(side=tk.LEFT)
        vid_size = ttk.Combobox(opt, values=["1152x768", "1280x720", "720x1280", "1024x1024"],
                                width=12, state="readonly")
        vid_size.set("1152x768")
        vid_size.pack(side=tk.LEFT, padx=5)

        self._progress_var = tk.StringVar(value="")

        # 参考图
        tk.Label(card, text="参考图（可选）：", fg=theme.fg, bg=theme.card_bg).pack(
            anchor=tk.W, pady=(8, 0))
        row = tk.Frame(card, bg=theme.card_bg)
        row.pack(fill=tk.X, pady=3)
        vid_img_path = tk.Entry(row, bg=theme.input_bg, fg=theme.fg,
                                insertbackground="white")
        vid_img_path.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def browse():
            path = filedialog.askopenfilename(
                filetypes=[("图片", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")]
            )
            if path:
                vid_img_path.delete(0, END)
                vid_img_path.insert(0, path)

        tk.Button(row, text="浏览", command=browse,
                  bg=theme.card_bg, fg="white", cursor="hand2").pack(side=tk.LEFT, padx=5)

        tk.Button(card, text="🎬 生成",
                  command=lambda: self._do_video(
                      vid_input, vid_duration, vid_size, vid_img_path, vid_out),
                  bg=theme.accent, fg="white", cursor="hand2").pack(anchor=tk.E, pady=3)

        tk.Label(frame, text="生成结果：", fg=theme.fg, bg=theme.bg).pack(anchor=tk.W, padx=5)
        vid_out = self._add_output_area(frame, theme)

        self._widgets = {
            "frame": frame,
            "vid_input": vid_input,
            "vid_duration": vid_duration,
            "vid_size": vid_size,
            "vid_img_path": vid_img_path,
            "vid_out": vid_out,
        }
        return frame

    def activate(self) -> None:
        pass

    def deactivate(self) -> None:
        pass

    def dispose(self) -> None:
        self._ctx = None
        self._widgets.clear()

    def _do_video(
        self,
        vid_input: tk.Text,
        vid_duration: ttk.Combobox,
        vid_size: ttk.Combobox,
        vid_img_path: tk.Entry,
        vid_out: scrolledtext.ScrolledText,
    ) -> None:
        prompt = vid_input.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("提示", "请输入视频描述")
            return

        vid_out.delete("1.0", END)
        vid_out.insert(END, "⏳ 正在生成视频...\n")
        vid_out.update()

        def task():
            try:
                client = self._ctx.client if self._ctx else None
                if client is None:
                    raise RuntimeError("上下文未初始化")
                image_ref = vid_img_path.get().strip() or None
                # Parse size "WxH" to width, height
                size_str = vid_size.get()  # e.g. "1152x768"
                w_str, h_str = size_str.split("x")
                result = client.generate_video(
                    prompt,
                    image_url=image_ref,
                    width=int(w_str),
                    height=int(h_str),
                )
                vid_out.delete("1.0", END)
                vid_out.insert(END, f"✅ 视频生成成功！\n{result}")
            except Exception as e:
                vid_out.delete("1.0", END)
                vid_out.insert(END, f"❌ 错误：{e}")

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
