# -*- coding: utf-8 -*-
"""✨ 小画家 AI — 小学生专用版 ✨ 秒切版"""

import os, sys, time, threading, json, subprocess, ctypes, ctypes.wintypes
from pathlib import Path
from tkinter import *
from tkinter import ttk, filedialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agnes.config import load_env_into_os
load_env_into_os()

from agnes.client import AgnesClient


# ── Windows 拖拽支持 ─────────────────────────────
WM_DROPFILES = 0x0233
GWL_WNDPROC = -4
WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int, ctypes.wintypes.HWND,
    ctypes.c_uint, ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM
)


class DropTarget:
    """为 tkinter 控件注册 Windows 文件拖拽功能（64 位兼容）。"""

    _procs = {}

    @classmethod
    def register(cls, widget, on_drop, hover_feedback=None):
        hwnd = int(widget.winfo_id())
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        # 修正 argtypes（64 位 Python 需要 c_longlong）
        user32.SetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.c_longlong]
        user32.GetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_longlong
        user32.CallWindowProcW.argtypes = [ctypes.c_longlong, ctypes.wintypes.HWND,
                                            ctypes.c_uint, ctypes.wintypes.WPARAM,
                                            ctypes.wintypes.LPARAM]
        user32.CallWindowProcW.restype = ctypes.c_longlong

        shell32.DragAcceptFiles(hwnd, True)
        old_proc = user32.GetWindowLongPtrW(hwnd, GWL_WNDPROC)
        old_cb = WNDPROC(old_proc) if old_proc else None
        hovering = False

        def new_proc(h, msg, wp, lp):
            nonlocal hovering
            if msg == WM_DROPFILES:
                count = shell32.DragQueryFileW(wp, -1, None, 0)
                files = []
                for i in range(count):
                    buf = ctypes.create_unicode_buffer(260)
                    shell32.DragQueryFileW(wp, i, buf, 260)
                    p = buf.value
                    if os.path.splitext(p)[1].lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
                        files.append(p)
                shell32.DragFinish(wp)
                if files:
                    widget.after(0, lambda f=list(files): on_drop(f))
                if hover_feedback:
                    hover_feedback(False)
                return 1
            if hover_feedback and msg in (0x0234, 0x0235) and not hovering:
                hovering = True
                widget.after(0, lambda: hover_feedback(True))
            if hover_feedback and msg == 0x0236:
                hovering = False
                widget.after(0, lambda: hover_feedback(False))
            if old_cb:
                return user32.CallWindowProcW(old_cb, h, msg, wp, lp)
            return 0

        cb = WNDPROC(new_proc)
        cls._procs[hwnd] = cb
        # 用 ctypes.addressof 获取函数指针的整数地址，安全传给 SetWindowLongPtrW
        # Python 3.8+ 支持 ctypes.WINFUNCTYPE 实例的 .value 属性
        # 兼容方式：转 c_void_p 取 value 整数再传
        ptr = ctypes.cast(cb, ctypes.c_void_p).value
        user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC, ptr)
        return cb


# ── 配色 ──
C = {
    "bg": "#FFF8E7",
    "card": "#FFFFFF",
    "shadow": "#E8DCC8",
    "orange": "#FF8C42",
    "pink": "#FF6B9D",
    "blue": "#4ECDC4",
    "purple": "#A78BFA",
    "green": "#68D391",
    "text": "#2D3436",
    "subtext": "#636E72",
    "success": "#00B894",
    "error": "#FF6B6B",
}

class KidsApp:
    def __init__(self):
        self.root = Tk()
        self.root.title("✨ 小画家 AI")
        self.root.configure(bg=C["bg"])
        self.root.geometry("900x700")
        self.root.minsize(700, 550)

        self._client = None
        self.api_ok = False

        # ── 一个容器 Frame，所有页面往里放 ──
        self.container = Frame(self.root, bg=C["bg"])
        self.container.pack(fill=BOTH, expand=True)

        # 预创建所有页面
        self.pages = {}
        for name in ["home", "draw", "video", "chat"]:
            self.pages[name] = Frame(self.container, bg=C["bg"])

        self._build_home()
        self._build_draw()
        self._build_video()
        self._build_chat()

        self.current_page = None
        self.show_page("home")

        # 后台检查 API（不阻塞界面显示）
        threading.Thread(target=self._check_api, daemon=True).start()

    def _rebuild_home_status(self):
        """仅重建主页的 API 状态行，不动其他控件"""
        if not hasattr(self, 'api_status_label'):
            return
        if self.api_ok:
            self.api_status_label.config(text="✅ 已连接", fg=C["success"])
        else:
            self.api_status_label.config(
                text=f"⚠️ 连接失败：{getattr(self, '_api_error', '未知')}",
                fg=C["error"])

    def _check_api(self):
        """后台检查 API 连通性，不阻塞界面"""
        try:
            c = AgnesClient()
            self._client = c
            self.api_ok = True
        except Exception as e:
            self.api_ok = False
            self._api_error = str(e)
            # 写日志
            Path(__file__).parent.joinpath("kids_error.log").write_text(
                f"API 检查失败: {e}", encoding="utf-8")
        # 刷新主页（如果当前在主页）
        if self.current_page == "home":
            self.root.after(0, lambda: self._rebuild_home_status())

    def show_page(self, name):
        """切页面：隐藏当前 → 显示目标（瞬间完成，不重建控件）"""
        if self.current_page:
            self.pages[self.current_page].pack_forget()
        self.pages[name].pack(fill=BOTH, expand=True)
        self.current_page = name

    # ── 通用组件 ──
    def _topbar(self, parent, emoji, title, color):
        bar = Frame(parent, bg=C["bg"])
        bar.pack(fill=X, padx=20, pady=(15, 5))

        Button(bar, text="🏠", font=("Segoe UI Emoji", 24),
               bg=C["card"], fg=C["text"], cursor="hand2",
               relief=FLAT, bd=0, padx=15, pady=5,
               command=lambda: self.show_page("home")).pack(side=LEFT)

        Label(bar, text=f"{emoji} {title}", font=("Microsoft YaHei", 24, "bold"),
              fg=color, bg=C["bg"]).pack(side=LEFT, expand=True)

        Button(bar, text="📂", font=("Segoe UI Emoji", 24),
               bg=C["card"], fg=C["text"], cursor="hand2",
               relief=FLAT, bd=0, padx=10,
               command=self._open_outputs).pack(side=RIGHT)

        sep = Frame(parent, bg=color, height=3)
        sep.pack(fill=X, padx=30, pady=(0, 5))

    def _open_outputs(self, sub=None):
        path = Path(__file__).parent / "outputs"
        if sub:
            path = path / sub
        if path.exists():
            subprocess.Popen(["explorer", str(path)])

    def _insert_open_btn(self, widget, filepath, color):
        """在 Text 控件里插入打开文件夹按钮"""
        btn = Button(widget, text="📂 打开文件夹", font=("Microsoft YaHei", 16, "bold"),
                     bg=color, fg="white", cursor="hand2",
                     relief=FLAT, bd=0, padx=20, pady=8,
                     command=lambda: self._open_outputs(os.path.dirname(filepath)))
        widget.window_create(END, window=btn)

    # ═══════════════ 主页 ═══════════════
    def _build_home(self):
        p = self.pages["home"]

        Label(p, text="✨ 小画家 AI ✨", fg=C["orange"], bg=C["bg"],
              font=("Microsoft YaHei", 32, "bold")).pack(pady=(40, 5))
        Label(p, text="你想做什么呀？", fg=C["subtext"], bg=C["bg"],
              font=("Microsoft YaHei", 18)).pack(pady=(0, 20))

        self.api_status_label = Label(p, text="⏳ 正在连接...", fg=C["subtext"],
                                       bg=C["bg"], font=("Microsoft YaHei", 14))
        self.api_status_label.pack(pady=(5, 10))

        cards = Frame(p, bg=C["bg"])
        cards.pack(expand=True, fill=BOTH, padx=40, pady=10)
        for i in range(3):
            cards.grid_columnconfigure(i, weight=1)
        cards.grid_rowconfigure(0, weight=1)

        features = [
            ("🎨", "画一张画", "告诉 AI 你想画什么\n它马上帮你画出来！", C["orange"], "draw"),
            ("🎬", "做小动画", "写一个小故事\nAI 帮你变成视频！", C["blue"], "video"),
            ("💬", "聊聊天", "和 AI 说说话\n什么问题都能问！", C["purple"], "chat"),
        ]

        for i, (emoji, title, desc, color, page) in enumerate(features):
            card = Frame(cards, bg=C["card"], highlightbackground=C["shadow"],
                         highlightthickness=2, bd=0)
            card.grid(row=0, column=i, padx=10, pady=10, sticky="nsew")

            inner = Frame(card, bg=C["card"])
            inner.pack(expand=True, fill=BOTH, padx=15, pady=15)

            Label(inner, text=emoji, font=("Segoe UI Emoji", 48), bg=C["card"]).pack(pady=5)
            Label(inner, text=title, font=("Microsoft YaHei", 20, "bold"),
                  fg=color, bg=C["card"]).pack()
            Label(inner, text=desc, font=("Microsoft YaHei", 13),
                  fg=C["subtext"], bg=C["card"], justify=CENTER).pack(pady=5)

            # 点击整张卡跳转
            for w in [card, inner] + inner.winfo_children():
                w.bind("<Button-1>", lambda e, n=page: self.show_page(n), add="+")

        foot = Frame(p, bg=C["bg"])
        foot.pack(pady=(5, 20))
        Label(foot, text="作品自动保存在 outputs 文件夹 📁",
              fg=C["subtext"], bg=C["bg"], font=("Microsoft YaHei", 13)).pack()
        Button(foot, text="📂 打开 outputs", font=("Microsoft YaHei", 13),
               bg=C["green"], fg="white", cursor="hand2",
               relief=FLAT, bd=0, padx=20, pady=6,
               command=self._open_outputs).pack(pady=5)

    # ═══════════════ 画画 ═══════════════
    def _build_draw(self):
        p = self.pages["draw"]
        self._topbar(p, "🎨", "画一张画", C["orange"])

        body = Frame(p, bg=C["bg"])
        body.pack(fill=BOTH, expand=True, padx=30, pady=10)

        Label(body, text="你想画什么？一句话就行 👇",
              font=("Microsoft YaHei", 16), fg=C["text"], bg=C["bg"]).pack(anchor=W)

        # 模式切换
        mode_row = Frame(body, bg=C["bg"])
        mode_row.pack(fill=X, pady=(5, 0))
        Label(mode_row, text="模式：", font=("Microsoft YaHei", 12),
              fg=C["subtext"], bg=C["bg"]).pack(side=LEFT)
        self.draw_mode = ttk.Combobox(mode_row, font=("Microsoft YaHei", 13),
                                      state="readonly", width=16)
        self.draw_mode["values"] = ["🖊 纯文字生成", "🖼 参考图片生成"]
        self.draw_mode.current(0)
        self.draw_mode.pack(side=LEFT, padx=8)
        self.draw_mode.bind("<<ComboboxSelected>>", self._toggle_draw_mode)

        # 图片上传（默认隐藏）
        self.draw_images = []
        self.draw_img_btn = Button(body, text="📷 选择参考图片（可多选，最多 4 张）",
                                   font=("Microsoft YaHei", 13),
                                   bg=C["pink"], fg="white", cursor="hand2",
                                   relief=FLAT, bd=0, padx=12, pady=5,
                                   command=self._pick_draw_images)
        self.draw_thumbs = Frame(body, bg=C["bg"])

        ef = Frame(body, bg=C["card"], highlightbackground=C["shadow"],
                   highlightthickness=2, bd=0)
        ef.pack(fill=X, pady=8)
        self.draw_input = Text(ef, height=2, font=("Microsoft YaHei", 18),
                               bg=C["card"], fg=C["text"], relief=FLAT, bd=0, padx=10, pady=8)
        self.draw_input.pack(fill=X)
        self.draw_input.focus()

        # 尺寸选择
        size_row = Frame(body, bg=C["bg"])
        size_row.pack(fill=X, pady=(8, 0))
        Label(size_row, text="尺寸：", font=("Microsoft YaHei", 14),
              fg=C["text"], bg=C["bg"]).pack(side=LEFT)
        self.draw_size = ttk.Combobox(size_row, font=("Microsoft YaHei", 14),
                                      state="readonly", width=20)
        self.draw_size["values"] = [
            "1024x768  (横版)",
            "1024x1024 (方形)",
            "768x1024  (竖版)",
            "2048x2048 (高清)",
        ]
        self.draw_size.current(0)
        self.draw_size.pack(side=LEFT, padx=10)

        self.draw_btn = Button(body, text="🎨 画出来！", font=("Microsoft YaHei", 20, "bold"),
                                bg=C["orange"], fg="white", cursor="hand2",
                                relief=FLAT, bd=0, padx=30, pady=12,
                                command=self._do_draw)
        self.draw_btn.pack(pady=8)

        Label(body, text="💡 试试：一只戴帽子的猫  在太空飞行的火箭 🚀",
              font=("Microsoft YaHei", 12), fg=C["subtext"], bg=C["bg"]).pack()

        of = Frame(body, bg=C["card"], highlightbackground=C["shadow"],
                   highlightthickness=2, bd=0)
        of.pack(fill=BOTH, expand=True, pady=(10, 0))
        self.draw_output = Text(of, font=("Consolas", 12), bg=C["card"], fg=C["text"],
                                 relief=FLAT, bd=0, wrap=WORD, padx=15, pady=10)
        self.draw_output.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.draw_output.insert(END, "在上面写你想画的，然后点「画出来！」🎨\n")

        # 注册拖拽目标
        self._setup_draw_drop()

    def _setup_draw_drop(self):
        """为画图页注册拖拽图片功能。"""
        def on_drop(files):
            for f in files:
                if f not in self.draw_images and len(self.draw_images) < 4:
                    self.draw_images.append(f)
            self.draw_mode.current(1)
            self._toggle_draw_mode()
            self._show_draw_thumbs()

        def hover(on):
            self.draw_input.configure(bg="#FFF3E0" if on else C["card"])

        DropTarget.register(self.draw_input, on_drop, hover)

    def _toggle_draw_mode(self, e=None):
        if "参考" in self.draw_mode.get():
            self.draw_img_btn.pack(before=self.draw_size.master, fill=X, pady=(6, 2))
        else:
            self.draw_img_btn.pack_forget()
            self.draw_thumbs.pack_forget()
            self.draw_images = []

    def _pick_draw_images(self):
        files = filedialog.askopenfilenames(
            title="选择参考图片（可多选）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")]
        )
        for f in files:
            if f not in self.draw_images and len(self.draw_images) < 4:
                self.draw_images.append(f)
        self._show_draw_thumbs()

    def _show_draw_thumbs(self):
        for w in self.draw_thumbs.winfo_children():
            w.destroy()
        if not self.draw_images:
            self.draw_thumbs.pack_forget()
            self.draw_img_btn.config(text="📷 选择参考图片（可多选，最多 4 张）")
            return
        self.draw_thumbs.pack(fill=X, pady=(4, 0))
        chip_row = Frame(self.draw_thumbs, bg=C["bg"])
        chip_row.pack(anchor=W)
        for f in self.draw_images:
            name = os.path.basename(f)
            if len(name) > 12: name = name[:10] + ".."
            chip = Frame(chip_row, bg=C["pink"], highlightthickness=0, bd=0)
            chip.pack(side=LEFT, padx=2, pady=2)
            lbl = Label(chip, text=f"🖼 {name}", font=("Microsoft YaHei", 9),
                        fg="white", bg=C["pink"], padx=6, pady=2)
            lbl.pack(side=LEFT)
            lbl.bind("<Button-1>", lambda e, fp=f: (self.draw_images.remove(fp), self._show_draw_thumbs()))
        btn_clr = Button(chip_row, text="✕ 全部清空", font=("Microsoft YaHei", 9),
                          bg=C["error"], fg="white", cursor="hand2", relief=FLAT, bd=0, padx=6, pady=2,
                          command=lambda: (self.draw_images.clear(), self._show_draw_thumbs()))
        btn_clr.pack(side=LEFT, padx=5)
        self.draw_img_btn.config(text=f"📷 再加图片（{len(self.draw_images)}/4）")

    def _do_draw(self):
        prompt = self.draw_input.get("1.0", END).strip()
        if not prompt:
            return
        self.draw_btn.config(state=DISABLED, text="⏳ 正在画...")
        self.draw_output.delete("1.0", END)
        mode = self.draw_mode.get()
        use_images = "参考" in mode and self.draw_images
        if use_images:
            self.draw_output.insert(END, f"🎨 参考 {len(self.draw_images)} 张图片在创作...\n⏳ AI 正在画...\n\n")
        else:
            self.draw_output.insert(END, f"🎨 正在画：{prompt}\n⏳ AI 正在创作...\n\n")

        draw_images = list(self.draw_images)
        size = self.draw_size.get().split()[0]

        def task():
            try:
                c = self._client or AgnesClient()
                urls = None
                if "参考" in mode and draw_images:
                    urls = [c.image_to_base64(p) for p in draw_images]
                path = c.generate_image_and_save(prompt, size=size, image_urls=urls)
                self.root.after(0, lambda: self._draw_done(path))
            except Exception as e:
                import traceback
                errlog = Path(__file__).parent / "kids_error.log"
                errlog.write_text(f"画图失败: {e}\n{traceback.format_exc()}", encoding="utf-8")
                self.root.after(0, lambda e=e: self._draw_error(str(e)))
        threading.Thread(target=task, daemon=True).start()

    def _draw_done(self, path):
        self.draw_output.delete("1.0", END)
        self.draw_output.insert(END, "✅ 画好啦！\n\n")
        self.draw_output.insert(END, f"📁 图片已经保存到：\n{path}\n\n")
        self._insert_open_btn(self.draw_output, path, C["orange"])
        self.draw_btn.config(state=NORMAL, text="🎨 再画一张！")

    def _draw_error(self, msg):
        self.draw_output.delete("1.0", END)
        self.draw_output.insert(END, f"❌ 出错了...\n\n{msg}\n\n")
        self.draw_output.insert(END, "💡 等一下再试，或者换一个描述试试？")
        self.draw_btn.config(state=NORMAL, text="🎨 画出来！")

    # ═══════════════ 做动画 ═══════════════
    def _build_video(self):
        p = self.pages["video"]
        self._topbar(p, "🎬", "做小动画", C["blue"])

        body = Frame(p, bg=C["bg"])
        body.pack(fill=BOTH, expand=True, padx=30, pady=(10, 0))

        Label(body, text="写一个小故事，AI 帮你变成视频 👇",
              font=("Microsoft YaHei", 16), fg=C["text"], bg=C["bg"]).pack(anchor=W)

        ef = Frame(body, bg=C["card"], highlightbackground=C["shadow"],
                   highlightthickness=2, bd=0)
        ef.pack(fill=X, pady=8)
        self.video_input = Text(ef, height=3, font=("Microsoft YaHei", 18),
                                bg=C["card"], fg=C["text"], relief=FLAT, bd=0, padx=10, pady=8)
        self.video_input.pack(fill=X)
        self.video_input.focus()

        # 图片上传（图生视频）
        self.video_img_frame = Frame(body, bg=C["bg"])
        self.video_img_path = None
        self.video_img_btn = Button(body, text="🖼 选一张起始图片（可选）",
                                    font=("Microsoft YaHei", 13),
                                    bg=C["shadow"], fg=C["text"], cursor="hand2",
                                    relief=FLAT, bd=0, padx=12, pady=5,
                                    command=self._pick_video_image)
        self.video_img_btn.pack(pady=(8, 0))
        self.video_img_thumb = Label(body, text="", bg=C["bg"])

        # 分辨率 + 时长
        opt_row = Frame(body, bg=C["bg"])
        opt_row.pack(fill=X, pady=(8, 0))

        Label(opt_row, text="分辨率：", font=("Microsoft YaHei", 14),
              fg=C["text"], bg=C["bg"]).pack(side=LEFT)
        self.video_size = ttk.Combobox(opt_row, font=("Microsoft YaHei", 14),
                                       state="readonly", width=16)
        self.video_size["values"] = [
            "1152x768  (默认)",
            "1024x1024 (方形)",
            "768x1024  (竖版)",
        ]
        self.video_size.current(0)
        self.video_size.pack(side=LEFT, padx=(5, 20))

        Label(opt_row, text="时长：", font=("Microsoft YaHei", 14),
              fg=C["text"], bg=C["bg"]).pack(side=LEFT)
        self.video_duration = ttk.Combobox(opt_row, font=("Microsoft YaHei", 14),
                                           state="readonly", width=12)
        self.video_duration["values"] = ["3秒", "5秒", "7秒", "10秒"]
        self.video_duration.current(1)  # 默认 5s
        self.video_duration.pack(side=LEFT, padx=5)

        self.video_btn = Button(body, text="🎬 开始做动画！", font=("Microsoft YaHei", 20, "bold"),
                                 bg=C["blue"], fg="white", cursor="hand2",
                                 relief=FLAT, bd=0, padx=30, pady=12,
                                 command=self._do_video)
        self.video_btn.pack(pady=8)

        Label(body, text="💡 视频需要等 1-3 分钟，先去喝口水吧 🧃",
              font=("Microsoft YaHei", 12), fg=C["subtext"], bg=C["bg"]).pack()

        of = Frame(body, bg=C["card"], highlightbackground=C["shadow"],
                   highlightthickness=2, bd=0)
        of.pack(fill=BOTH, expand=True, pady=(10, 0))
        self.video_output = Text(of, font=("Consolas", 12), bg=C["card"], fg=C["text"],
                                  relief=FLAT, bd=0, wrap=WORD, padx=15, pady=10)
        self.video_output.pack(fill=BOTH, expand=True, padx=5, pady=5)
        self.video_output.insert(END, "写一个故事，然后点「开始做动画」！🎬\n")

        # 注册拖拽目标（输入框区域）
        self._setup_video_drop()

    def _setup_video_drop(self):
        """为视频页注册拖拽图片功能。"""
        def on_drop(files):
            if files:
                f = files[0]
                self.video_img_path = f
                name = os.path.basename(f)
                if len(name) > 20: name = name[:18] + ".."
                self.video_img_btn.config(text=f"🖼 {name}  ✕ 点此移除",
                                          bg=C["pink"], fg="white")

        def hover(on):
            if on:
                self.video_input.configure(bg="#E3F5F3")
            else:
                self.video_input.configure(bg=C["card"])

        DropTarget.register(self.video_input, on_drop, hover)

    def _pick_video_image(self):
        f = filedialog.askopenfilename(
            title="选一张图片作为视频开头",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")]
        )
        if f:
            self.video_img_path = f
            name = os.path.basename(f)
            if len(name) > 20: name = name[:18] + ".."
            self.video_img_btn.config(text=f"🖼 {name}  ✕ 点此移除",
                                      bg=C["pink"], fg="white")
        else:
            self.video_img_path = None
            self.video_img_btn.config(text="🖼 选一张起始图片（可选）",
                                      bg=C["shadow"], fg=C["text"])

    def _do_video(self):
        prompt = self.video_input.get("1.0", END).strip()
        if not prompt:
            return
        self.video_btn.config(state=DISABLED, text="⏳ 正在做动画...")
        self._video_start_time = time.time()
        self._show_video_progress()
        self._video_progress("queued", 0)
        self.video_output.delete("1.0", END)
        if self.video_img_path:
            self.video_output.insert(END, f"🎬 小故事：{prompt}\n🖼 起始图：{os.path.basename(self.video_img_path)}\n\n")
        else:
            self.video_output.insert(END, f"🎬 小故事：{prompt}\n\n")

        img_path = self.video_img_path
        def task():
            try:
                c = self._client or AgnesClient()
                def on_progress(state, progress):
                    self.root.after(0, lambda s=state, p=progress: self._video_progress(s, p))
                img_b64 = c.image_to_base64(img_path) if img_path else None
                duration_map = {"3秒": 81, "5秒": 121, "7秒": 169, "10秒": 241}
                dur = self.video_duration.get()
                frames = duration_map.get(dur, 121)
                size = self.video_size.get().split()[0].split("x")
                w, h = int(size[0]), int(size[1])
                path = c.generate_video_and_save(
                    prompt, width=w, height=h, num_frames=frames,
                    image_url=img_b64,
                    poll_interval=8, on_progress=on_progress)
                self.root.after(0, lambda: self._video_done(path))
            except Exception as e:
                import traceback
                errlog = Path(__file__).parent / "kids_error.log"
                errlog.write_text(f"视频失败: {e}\n{traceback.format_exc()}", encoding="utf-8")
                self.root.after(0, lambda e=e: self._video_error(str(e)))
        threading.Thread(target=task, daemon=True).start()

    def _show_video_progress(self):
        self.video_progress_frame.pack(fill=X, pady=(10, 5))
        self.video_progress.pack(fill=X, pady=(0, 5))
        self.video_pct_label.pack()

    def _hide_video_progress(self):
        self.video_progress_frame.pack_forget()
        self.video_progress.pack_forget()
        self.video_pct_label.pack_forget()

    def _video_progress(self, state, progress):
        # 确保显示
        if not self.video_progress.winfo_ismapped():
            self._show_video_progress()

        w = self.video_progress.winfo_width() or 600
        h = 40

        self.video_progress.delete("all")

        # 底色
        self.video_progress.create_rectangle(0, 0, w, h, fill=C["card"], outline="", width=0)

        # 进度条
        fill_w = int(w * max(0, min(100, progress)) / 100)
        if progress >= 100:
            color = C["success"]
        elif progress >= 50:
            color = C["blue"]
        else:
            color = C["blue"]

        # 渐变效果：多段矩形
        for x in range(0, fill_w, 3):
            self.video_progress.create_rectangle(x, 2, min(x+3, fill_w), h-2,
                                                  fill=color, outline="", width=0)
        # 边框
        self.video_progress.create_rectangle(0, 0, w, h, outline=C["shadow"], width=2)

        # 百分比文字在进度条中间
        self.video_pct_label.config(text=f"{progress}%")

        # 状态文字映射
        state_map = {
            "queued": "📋 排队中，马上开始...",
            "in_progress": "🎨 AI 正在创作中...",
            "running": "🎨 AI 正在创作中...",
            "processing": "🎨 AI 正在创作中...",
            "rendering": "🎬 正在渲染画面...",
            "completed": "✅ 生成完成！正在下载...",
            "done": "✅ 生成完成！",
            "succeeded": "✅ 生成完成！",
            "ready": "✅ 生成完成！",
            "downloading": "📥 正在下载到本地...",
        }
        friendly = state_map.get(state, f"⏳ {state}")

        # 计算已过时间
        elapsed = int(time.time() - self._video_start_time)
        mins, secs = divmod(elapsed, 60)
        time_str = f"⏱ {mins}分{secs}秒" if mins > 0 else f"⏱ {secs}秒"

        self.video_status_label.config(text=friendly)
        self.video_time_label.config(text=time_str)

    def _video_done(self, path):
        self._video_progress("done", 100)
        self.video_output.delete("1.0", END)
        self.video_output.insert(END, "✅ 动画做好啦！🎉\n\n")
        self.video_output.insert(END, f"📁 视频已经保存到：\n{path}\n\n")
        self._insert_open_btn(self.video_output, path, C["blue"])
        self.video_output.insert(END, "\n💡 用播放器打开哦 🎬")
        self.video_btn.config(state=NORMAL, text="🎬 再做一个！")

    def _video_error(self, msg):
        self.video_output.delete("1.0", END)
        self.video_output.insert(END, f"❌ 出错了...\n\n{msg}\n\n")
        self.video_output.insert(END, "💡 等一下再试，或者换一个更简单的描述\n")
        self.video_output.insert(END, "   比如：「一只小猫在花园里玩耍」🐱")
        self.video_btn.config(state=NORMAL, text="🎬 开始做动画！")

    # ═══════════════ 聊天 ═══════════════
    def _build_chat(self):
        p = self.pages["chat"]
        self._topbar(p, "💬", "聊聊天", C["purple"])

        # 聊天记录 + 滚动条
        body = Frame(p, bg=C["bg"])
        body.pack(fill=BOTH, expand=True, padx=30, pady=10)

        cf = Frame(body, bg=C["card"], highlightbackground=C["shadow"],
                   highlightthickness=2, bd=0)
        cf.pack(fill=BOTH, expand=True)

        # 用 Canvas + 内嵌 Frame 实现气泡聊天
        self.chat_canvas = Canvas(cf, bg=C["card"], highlightthickness=0)
        self.chat_scroll = Scrollbar(cf, orient=VERTICAL, command=self.chat_canvas.yview)
        self.chat_bubbles = Frame(self.chat_canvas, bg=C["card"])

        self.chat_bubbles.bind("<Configure>",
            lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")))
        self.chat_canvas.create_window((0, 0), window=self.chat_bubbles, anchor="nw", tags="bubbles")
        self.chat_canvas.configure(yscrollcommand=self.chat_scroll.set)

        self.chat_canvas.pack(side=LEFT, fill=BOTH, expand=True, padx=(5, 0), pady=5)
        self.chat_scroll.pack(side=RIGHT, fill=Y, pady=5)
        self.chat_canvas.bind("<Configure>", self._resize_chat_canvas)

        # 输入行
        row = Frame(p, bg=C["bg"])
        row.pack(fill=X, padx=30, pady=(5, 20))

        # 图片附件按钮
        self.chat_img_btn = Button(row, text="📎", font=("Segoe UI Emoji", 22),
                                    bg=C["card"], fg=C["subtext"], cursor="hand2",
                                    relief=FLAT, bd=0, padx=8, pady=8,
                                    command=self._pick_chat_images)
        self.chat_img_btn.pack(side=LEFT, padx=(0, 8))

        ef = Frame(row, bg=C["card"], highlightbackground=C["shadow"],
                   highlightthickness=2, bd=0)
        ef.pack(side=LEFT, fill=X, expand=True)
        self.chat_input = Entry(ef, font=("Microsoft YaHei", 18), bg=C["card"], fg=C["text"],
                                 relief=FLAT, bd=0)
        # 拖拽支持
        self.chat_images = []
        self.chat_input.pack(fill=X)
        self.chat_input.bind("<Return>", lambda e: self._do_chat())
        self.chat_input.bind("<Shift-Return>", lambda e: self.chat_input.insert(INSERT, "\n"))

        self.chat_btn = Button(row, text="💬 发送", font=("Microsoft YaHei", 18, "bold"),
                                bg=C["purple"], fg="white", cursor="hand2",
                                relief=FLAT, bd=0, padx=20, pady=8,
                                command=self._do_chat)
        self.chat_btn.pack(side=RIGHT, padx=(10, 0))

        # 注册拖拽 + 初始化附件
        self.chat_images = []
        self._setup_chat_drop()

        # 对话记忆
        self.chat_history = []
        self._chat_typing_id = None

        # 欢迎语
        self._add_bubble("🤖", "AI 小助手",
            "你好呀！我是 AI 小助手 🤗\n有什么想问的都可以告诉我！\n\n比如：\n  🌍 地球为什么是圆的？\n  🦕 恐龙是怎么灭绝的？\n  🍰 怎么做巧克力蛋糕？",
            C["purple"], is_bot=True)

    def _resize_chat_canvas(self, event):
        w = event.width
        self.chat_canvas.itemconfig("bubbles", width=w)

    def _add_bubble(self, emoji, name, text, color, is_bot=False):
        """添加一条聊天气泡"""
        bubble = Frame(self.chat_bubbles, bg=C["card"])
        bubble.pack(fill=X, padx=10, pady=6)

        if is_bot:
            # AI 消息靠左
            row = Frame(bubble, bg=C["card"])
            row.pack(anchor=W, fill=X)

            ava = Frame(row, bg=C["card"])
            ava.pack(side=LEFT, anchor=N, padx=(0, 10))
            Label(ava, text=emoji, font=("Segoe UI Emoji", 28), bg=C["card"]).pack()

            content = Frame(row, bg="#F3E8FF", highlightbackground=color,
                            highlightthickness=1, bd=0)
            content.pack(side=LEFT, fill=X, expand=True)
            Label(content, text=name, font=("Microsoft YaHei", 11, "bold"),
                  fg=color, bg="#F3E8FF").pack(anchor=W, padx=10, pady=(6, 0))
            msg = Label(content, text=text, font=("Microsoft YaHei", 14),
                        fg=C["text"], bg="#F3E8FF", justify=LEFT, wraplength=450)
            msg.pack(anchor=W, padx=10, pady=(2, 8))
        else:
            # 用户消息靠右
            row = Frame(bubble, bg=C["card"])
            row.pack(anchor=E)

            content = Frame(row, bg="#E8F0FE", highlightbackground=C["blue"],
                            highlightthickness=1, bd=0)
            content.pack(side=RIGHT)
            Label(content, text=name, font=("Microsoft YaHei", 11, "bold"),
                  fg=C["blue"], bg="#E8F0FE").pack(anchor=E, padx=10, pady=(6, 0))
            msg = Label(content, text=text, font=("Microsoft YaHei", 14),
                        fg=C["text"], bg="#E8F0FE", justify=LEFT, wraplength=450)
            msg.pack(anchor=W, padx=10, pady=(2, 8))

            ava = Frame(row, bg=C["card"])
            ava.pack(side=RIGHT, anchor=N, padx=(10, 0))
            Label(ava, text=emoji, font=("Segoe UI Emoji", 28), bg=C["card"]).pack()

        # 滚动到底
        self.root.after(50, self._chat_scroll_bottom)

    def _chat_scroll_bottom(self):
        self.chat_canvas.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)

    def _remove_typing(self):
        """移除正在输入..."""
        if self._chat_typing_id:
            try:
                self._chat_typing_id.destroy()
            except Exception:
                pass
            self._chat_typing_id = None

    def _show_typing(self):
        """显示正在输入..."""
        self._remove_typing()
        bubble = Frame(self.chat_bubbles, bg=C["card"])
        bubble.pack(fill=X, padx=10, pady=6)
        row = Frame(bubble, bg=C["card"])
        row.pack(anchor=W, fill=X)
        ava = Frame(row, bg=C["card"])
        ava.pack(side=LEFT, anchor=N, padx=(0, 10))
        Label(ava, text="🤖", font=("Segoe UI Emoji", 28), bg=C["card"]).pack()
        content = Frame(row, bg="#F3E8FF", highlightbackground=C["purple"],
                        highlightthickness=1, bd=0)
        content.pack(side=LEFT)
        lbl = Label(content, text="正在输入...", font=("Microsoft YaHei", 14, "italic"),
                     fg=C["subtext"], bg="#F3E8FF")
        lbl.pack(padx=15, pady=10)
        self._chat_typing_id = bubble
        self._chat_scroll_bottom()

    def _pick_chat_images(self):
        files = filedialog.askopenfilenames(
            title="选择参考图片（可多选，最多 4 张）",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp"), ("所有文件", "*.*")]
        )
        for f in files:
            if f not in self.chat_images and len(self.chat_images) < 4:
                self.chat_images.append(f)
        self._show_chat_thumbs()

    def _show_chat_thumbs(self):
        """在输入框上方显示 / 清除缩略图条"""
        # 移除旧条（用实例属性引用）
        old = getattr(self, '_chat_thumb_bar', None)
        if old and old.winfo_exists():
            old.destroy()
        self._chat_thumb_bar = None

        if not self.chat_images:
            self.chat_img_btn.config(text="📎", fg=C["subtext"])
            return

        p = self.pages["chat"]
        bar = Frame(p, bg=C["bg"])
        bar.pack(fill=X, padx=30, pady=(0, 5), before=self.chat_img_btn)  # 插入到输入行前面
        self._chat_thumb_bar = bar

        for f in self.chat_images:
            name = os.path.basename(f)
            if len(name) > 12: name = name[:10] + ".."
            chip = Frame(bar, bg=C["pink"], bd=0)
            chip.pack(side=LEFT, padx=2)
            lbl = Label(chip, text=f"🖼 {name}", font=("Microsoft YaHei", 9),
                        fg="white", bg=C["pink"], padx=6, pady=2)
            lbl.pack(side=LEFT)
            lbl.bind("<Button-1>", lambda e, fp=f: (self.chat_images.remove(fp), self._show_chat_thumbs()))
        btn = Button(bar, text="✕", font=("Microsoft YaHei", 9, "bold"),
                     bg=C["error"], fg="white", cursor="hand2", relief=FLAT, bd=0, padx=4,
                     command=lambda: (self.chat_images.clear(), self._show_chat_thumbs()))
        btn.pack(side=LEFT, padx=5)
        self.chat_img_btn.config(text="📎", fg=C["pink"])

    def _setup_chat_drop(self):
        """聊天输入框拖拽图片。"""
        def on_drop(files):
            for f in files:
                if f not in self.chat_images and len(self.chat_images) < 4:
                    self.chat_images.append(f)
            self._show_chat_thumbs()
        def hover(on):
            self.chat_input.configure(bg="#F3E8FF" if on else C["card"])
        DropTarget.register(self.chat_input, on_drop, hover)

    def _do_chat(self):
        msg = self.chat_input.get().strip()
        if not msg:
            return

        # 附带的图片
        attach = list(self.chat_images)
        attach_label = f"  +{len(attach)}张图" if attach else ""
        self._add_bubble("🧒", "你", msg + attach_label, C["blue"], is_bot=False)
        self.chat_images.clear()
        self._show_chat_thumbs()
        self.chat_input.delete(0, END)
        self.chat_btn.config(state=DISABLED, text="⏳")
        self._show_typing()
        self.chat_history.append({"role": "user", "content": msg})

        def task():
            try:
                c = self._client or AgnesClient()
                tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": "generate_image",
                            "description": "根据描述生成一张图片。用户说'画''生成图''做一张图'等时调用。",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "prompt": {"type": "string", "description": "图片描述（中文）"},
                                    "size": {"type": "string", "enum": ["1024x768", "1024x1024", "768x1024", "2048x2048"], "default": "1024x768"},
                                },  # 参考图由系统自动附加，无需 AI 填写
                                "required": ["prompt"]
                            }
                        }
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "generate_video",
                            "description": "根据描述生成一段视频。用户说'做视频''生成动画''拍一段'等时调用。",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "prompt": {"type": "string", "description": "视频描述（中文）"},
                                    "duration": {"type": "string", "enum": ["3秒", "5秒", "7秒", "10秒"], "default": "5秒"}
                                },
                                "required": ["prompt"]
                            }
                        }
                    }
                ]

                msgs = [{"role": "system", "content": "你是小画家AI助手。用户发图片时先看看图再回答。让你画画或做视频时必须调用 generate_image 或 generate_video 工具。如果用户给了参考图，把图片描述和参考图一起传给工具。用中文，简短友好。"}]
                msgs += self.chat_history[-8:]

                # 有图片附件时构造多模态消息
                if attach:
                    b64_images = [c.image_to_base64(p) for p in attach]
                    content = [{"type": "text", "text": msg}]
                    for b in b64_images:
                        content.append({"type": "image_url", "image_url": {"url": b}})
                    msgs = [{"role": "system", "content": "你是小画家AI助手。用户发了图片给你看。如果用户让你根据图片画图或做视频，调用 generate_image/generate_video 工具。参考图系统会自动附上，你不用管。用中文简短回答。"}]
                    msgs += self.chat_history[-6:]
                    msgs.append({"role": "user", "content": content})
                    reply = c.chat(msgs, tools=tools)
                    # 保留 chat_images 供后续 tool call 使用
                else:
                    reply = c.chat(msgs, tools=tools)
                msg_obj = reply["choices"][0]["message"]

                # 检查是否有工具调用
                if msg_obj.get("tool_calls"):
                    for tc in msg_obj["tool_calls"]:
                        func = tc["function"]
                        name = func["name"]
                        args = json.loads(func["arguments"])

                        if name == "generate_image":
                            self.root.after(0, lambda a=args: self._chat_gen_image(a))
                        elif name == "generate_video":
                            self.root.after(0, lambda a=args: self._chat_gen_video(a))
                else:
                    text = msg_obj.get("content", "")
                    self.chat_history.append({"role": "assistant", "content": text})
                    self.root.after(0, lambda t=text: self._chat_reply(t))
            except Exception as e:
                import traceback
                log = Path(__file__).parent / "kids_error.log"
                log.write_text(f"聊天失败: {e}\n{traceback.format_exc()}", encoding="utf-8")
                self.root.after(0, lambda: self._chat_reply(
                    "😅 哎呀我卡住了...\n\n能不能再说一次？"))

        threading.Thread(target=task, daemon=True).start()

    def _chat_gen_image(self, args):
        """聊天中触发画图"""
        self._remove_typing()
        prompt = args.get("prompt", "")
        size = args.get("size", "1024x768")
        # 从聊天附件自动获取参考图（而非靠 AI 猜测）
        ref_b64 = []
        if self.chat_images:
            c = self._client or AgnesClient()
            ref_b64 = [c.image_to_base64(p) for p in self.chat_images]
            self.chat_images.clear()
            self._show_chat_thumbs()
        attach_hint = f"（+ {len(ref_b64)} 张参考图）" if ref_b64 else ""
        self._add_bubble("🤖", "AI 小助手", f"好的！我这就画「{prompt}」{attach_hint}\n⏳ 正在生成中...", C["purple"], is_bot=True)

        def task():
            try:
                c = self._client or AgnesClient()
                path = c.generate_image_and_save(prompt, size=size, image_urls=ref_b64 if ref_b64 else None)
                self.root.after(0, lambda: self._chat_reply(
                    f"✅ 画好啦！\n\n📁 已保存到：\n{path}\n\n你可以点顶部 📂 打开文件夹查看～"))
            except Exception as e:
                self.root.after(0, lambda e=e: self._chat_reply(f"❌ 画画失败了...\n{e}"))
        threading.Thread(target=task, daemon=True).start()

    def _chat_gen_video(self, args):
        """聊天中触发做视频"""
        self._remove_typing()
        prompt = args.get("prompt", "")
        dur_str = args.get("duration", "5秒")
        # 自动注入附件图
        img_b64 = None
        if self.chat_images:
            c = self._client or AgnesClient()
            img_b64 = c.image_to_base64(self.chat_images[0])
            self.chat_images.clear()
            self._show_chat_thumbs()
        attach_hint = "（+ 参考图）" if img_b64 else ""
        self._add_bubble("🤖", "AI 小助手", f"好的！我做「{prompt}」的动画{attach_hint} 🎬\n⏳ 大概需要 5-10 分钟，先去玩一会儿吧～", C["purple"], is_bot=True)

        def task():
            try:
                c = self._client or AgnesClient()
                duration_map = {"3秒": 81, "5秒": 121, "7秒": 169, "10秒": 241}
                frames = duration_map.get(dur_str, 121)
                path = c.generate_video_and_save(prompt, num_frames=frames, image_url=img_b64, poll_interval=8)
                self.root.after(0, lambda: self._chat_reply(
                    f"✅ 动画做好啦！\n\n📁 已保存到：\n{path}\n\n你可以点顶部 📂 打开文件夹查看～"))
            except Exception as e:
                self.root.after(0, lambda e=e: self._chat_reply(f"❌ 做动画失败了...\n{e}"))
        threading.Thread(target=task, daemon=True).start()

    def _chat_reply(self, reply):
        self._remove_typing()
        self._add_bubble("🤖", "AI 小助手", reply, C["purple"], is_bot=True)
        self.chat_btn.config(state=NORMAL, text="💬 发送")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        app = KidsApp()
        app.run()
    except Exception as e:
        import traceback
        # 写入错误日志方便排查
        err_path = Path(__file__).parent / "kids_error.log"
        err_path.write_text(f"启动失败: {e}\n\n{traceback.format_exc()}", encoding="utf-8")
        # 尝试弹窗报错
        try:
            from tkinter import messagebox
            messagebox.showerror("启动失败", f"小画家启动失败：\n{e}\n\n错误详情已写入 kids_error.log")
        except Exception:
            pass
