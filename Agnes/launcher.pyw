# -*- coding: utf-8 -*-
"""Agnes AI 启动器 — 图形界面版"""

import os
import sys
import subprocess
import json
import time
import threading
from pathlib import Path
from tkinter import *
from tkinter import ttk, messagebox, scrolledtext

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from agnes.config import load_env_into_os, has_api_key, show_setup_dialog


class AgnesLauncher:
    """Agnes AI 图形启动器"""

    def __init__(self):
        load_env_into_os()
        if not has_api_key():
            show_setup_dialog()
        self.root = Tk()
        self.root.title("Agnes AI — 本地工具箱")
        self.root.geometry("720x680")
        self.root.minsize(600, 550)
        
        # 图标
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass
        
        # 颜色方案
        self.bg = "#1a1a2e"
        self.fg = "#e0e0e0"
        self.accent = "#6c63ff"
        self.success = "#4caf50"
        self.warning = "#ff9800"
        self.error = "#f44336"
        self.card_bg = "#16213e"
        self.input_bg = "#0f3460"
        
        self.root.configure(bg=self.bg)
        
        # 检测 API 状态
        self.api_ok = False
        self.models = []
        self._check_api()
        
        self._build_ui()
        
    def _check_api(self):
        """检查 API 连通性"""
        try:
            from agnes import AgnesClient
            c = AgnesClient()
            self.models = c.list_models()
            self.api_ok = True
        except Exception as e:
            self.api_ok = False
            self._api_error = str(e)
    
    def _build_ui(self):
        root = self.root
        
        # ===== 标题栏 =====
        header = Frame(root, bg=self.bg, pady=15)
        header.pack(fill=X)
        Label(header, text="▎Agnes AI 工具箱", font=("微软雅黑", 20, "bold"),
              fg="white", bg=self.bg).pack()
        Label(header, text="多模态 AI — 对话 · 图片 · 视频", font=("微软雅黑", 10),
              fg="#aaa", bg=self.bg).pack()
        
        # API 状态
        status_frame = Frame(root, bg=self.bg, pady=5)
        status_frame.pack(fill=X)
        if self.api_ok:
            colors = {"chat": "#4fc3f7", "image": "#ff9800", "video": "#ab47bc"}
            for m in self.models:
                mid = m["id"]
                from agnes import AgnesClient
                tp = AgnesClient.get_model_type(mid)
                c = colors.get(tp, "#888")
                lbl = Label(status_frame, text=f"● {mid}", fg=c, bg=self.bg, 
                           font=("微软雅黑", 8))
                lbl.pack(side=LEFT, padx=8)
            Label(status_frame, text="✅ API 已连接", fg=self.success, 
                  bg=self.bg, font=("微软雅黑", 9)).pack(side=RIGHT, padx=10)
        else:
            Label(status_frame, text=f"❌ API 未连接：{getattr(self, '_api_error', '未知错误')}",
                  fg=self.error, bg=self.bg, wraplength=600).pack(pady=5)
            Button(status_frame, text="刷新", command=self._refresh_api,
                   bg=self.accent, fg="white", cursor="hand2").pack(pady=3)
        
        # ===== 主功能区（笔记本选项卡） =====
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=self.bg, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.card_bg, foreground="white",
                       padding=[12, 4], font=("微软雅黑", 10))
        style.map("TNotebook.Tab", background=[("selected", self.accent)])
        
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # 各标签页
        self._add_tab_chat()
        self._add_tab_vision()
        self._add_tab_image()
        self._add_tab_video()
        self._add_tab_query()
        
        # ===== 底部栏 =====
        footer = Frame(root, bg=self.bg, pady=8)
        footer.pack(fill=X)
        Button(footer, text="❌ 退出", command=root.destroy,
               bg="#333", fg="white", width=10, cursor="hand2").pack(side=RIGHT, padx=10)
        Button(footer, text="💻 命令行模式", command=self._launch_cli,
               bg=self.card_bg, fg="white", cursor="hand2").pack(side=RIGHT, padx=5)
        Label(footer, text="Agnes v1.0 | https://agnes-ai.com",
              fg="#666", bg=self.bg, font=("微软雅黑", 8)).pack(side=LEFT, padx=10)
    
    def _make_card(self, parent):
        card = Frame(parent, bg=self.card_bg, padx=12, pady=10)
        card.pack(fill=X, pady=5)
        return card
    
    def _add_output_area(self, parent):
        text = scrolledtext.ScrolledText(parent, height=8, bg=self.input_bg,
                                         fg=self.fg, insertbackground="white",
                                         font=("Consolas", 10), wrap=WORD)
        text.pack(fill=BOTH, expand=True, pady=5)
        return text
    
    # ── Chat 标签页 ──────────────────────────────────
    def _add_tab_chat(self):
        frame = Frame(self.notebook, bg=self.bg)
        self.notebook.add(frame, text="💬 对话")
        
        # 输入区
        card = self._make_card(frame)
        Label(card, text="输入内容：", fg=self.fg, bg=self.card_bg,
              font=("微软雅黑", 10)).pack(anchor=W)
        self.chat_input = Text(card, height=3, bg=self.input_bg, fg=self.fg,
                               insertbackground="white", font=("微软雅黑", 10))
        self.chat_input.pack(fill=X, pady=3)
        
        # 参数
        opt = Frame(card, bg=self.card_bg)
        opt.pack(fill=X, pady=3)
        Label(opt, text="模型：", fg=self.fg, bg=self.card_bg).pack(side=LEFT)
        self.chat_model = ttk.Combobox(opt, values=["agnes-2.0-flash", "agnes-1.5-flash"],
                                       width=18, state="readonly")
        self.chat_model.set("agnes-2.0-flash")
        self.chat_model.pack(side=LEFT, padx=5)
        
        self.chat_thinking = BooleanVar(value=False)
        ttk.Checkbutton(opt, text="深度思考", variable=self.chat_thinking).pack(side=LEFT, padx=10)
        
        Button(card, text="🚀 发送", command=self._do_chat,
               bg=self.accent, fg="white", cursor="hand2").pack(anchor=E, pady=3)
        
        # 输出区
        Label(frame, text="回复：", fg=self.fg, bg=self.bg,
              font=("微软雅黑", 10)).pack(anchor=W, padx=5)
        self.chat_out = self._add_output_area(frame)
        self.chat_out.insert(END, "🎨 欢迎使用 Agnes AI！\n在下方输入框中输入内容，开始对话吧 🚀\n\n")

    def _do_chat(self):
        prompt = self.chat_input.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("提示", "请输入对话内容")
            return
        self.chat_out.delete("1.0", END)
        self.chat_out.insert(END, "⏳ 正在生成回复...\n")
        self.chat_out.update()
        
        def task():
            try:
                from agnes import AgnesClient
                c = AgnesClient()
                reply = c.chat_text(prompt, model=self.chat_model.get(),
                                   thinking=self.chat_thinking.get())
                self.chat_out.delete("1.0", END)
                self.chat_out.insert(END, reply)
            except Exception as e:
                self.chat_out.delete("1.0", END)
                self.chat_out.insert(END, f"❌ 错误：{e}")
        
        threading.Thread(target=task, daemon=True).start()
    
    # ── Vision 标签页 ────────────────────────────────
    def _add_tab_vision(self):
        frame = Frame(self.notebook, bg=self.bg)
        self.notebook.add(frame, text="👁 识图")
        
        card = self._make_card(frame)
        Label(card, text="图片文件：", fg=self.fg, bg=self.card_bg).pack(anchor=W)
        row = Frame(card, bg=self.card_bg)
        row.pack(fill=X, pady=3)
        self.vision_path = Entry(row, bg=self.input_bg, fg=self.fg, 
                                 insertbackground="white")
        self.vision_path.pack(side=LEFT, fill=X, expand=True)
        Button(row, text="浏览", command=self._browse_vision,
               bg=self.card_bg, fg="white", cursor="hand2").pack(side=LEFT, padx=5)
        
        Label(card, text="问题：", fg=self.fg, bg=self.card_bg).pack(anchor=W, pady=(8,0))
        self.vision_input = Entry(card, bg=self.input_bg, fg=self.fg,
                                  insertbackground="white")
        self.vision_input.insert(0, "请描述这张图片")
        self.vision_input.pack(fill=X, pady=3)
        
        Button(card, text="🚀 识别", command=self._do_vision,
               bg=self.accent, fg="white", cursor="hand2").pack(anchor=E)
        
        Label(frame, text="识别结果：", fg=self.fg, bg=self.bg).pack(anchor=W, padx=5)
        self.vision_out = self._add_output_area(frame)
    
    def _browse_vision(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename()
        if path:
            self.vision_path.delete(0, END)
            self.vision_path.insert(0, path)
    
    def _do_vision(self):
        img = self.vision_path.get().strip()
        prompt = self.vision_input.get().strip()
        if not img:
            messagebox.showwarning("提示", "请选择图片文件")
            return
        if not prompt:
            prompt = "请描述这张图片"
        
        self.vision_out.delete("1.0", END)
        self.vision_out.insert(END, "⏳ 正在识别...\n")
        self.vision_out.update()
        
        def task():
            try:
                from agnes import AgnesClient, AgnesConfig
                c = AgnesClient()
                if img.startswith(("http://", "https://", "data:")):
                    img_url = img
                else:
                    img_url = c.image_to_base64(img)
                reply = c.chat_with_image(prompt, img_url)
                self.vision_out.delete("1.0", END)
                self.vision_out.insert(END, reply)
            except Exception as e:
                self.vision_out.delete("1.0", END)
                self.vision_out.insert(END, f"❌ 错误：{e}")
        
        threading.Thread(target=task, daemon=True).start()
    
    # ── Image 标签页 ─────────────────────────────────
    def _add_tab_image(self):
        frame = Frame(self.notebook, bg=self.bg)
        self.notebook.add(frame, text="🎨 生图")
        
        card = self._make_card(frame)
        Label(card, text="图片描述：", fg=self.fg, bg=self.card_bg).pack(anchor=W)
        self.img_input = Text(card, height=2, bg=self.input_bg, fg=self.fg,
                              insertbackground="white", font=("微软雅黑", 10))
        self.img_input.pack(fill=X, pady=3)
        
        opt = Frame(card, bg=self.card_bg)
        opt.pack(fill=X, pady=3)
        Label(opt, text="尺寸：", fg=self.fg, bg=self.card_bg).pack(side=LEFT)
        self.img_size = ttk.Combobox(opt, values=[
            "1024x768", "1024x1024", "768x1024",
            "2048x2048", "2048x1536", "1536x2048",
            "3072x3072", "4096x4096",
        ], width=12, state="readonly")
        self.img_size.set("1024x768")
        self.img_size.pack(side=LEFT, padx=5)
        
        self.img_save_var = BooleanVar(value=True)
        ttk.Checkbutton(opt, text="自动保存到本地", variable=self.img_save_var).pack(side=LEFT, padx=10)
        
        Button(card, text="🚀 生成", command=self._do_image,
               bg=self.accent, fg="white", cursor="hand2").pack(anchor=E)
        
        Label(frame, text="结果：", fg=self.fg, bg=self.bg).pack(anchor=W, padx=5)
        self.img_out = self._add_output_area(frame)
    
    def _do_image(self):
        prompt = self.img_input.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("提示", "请输入图片描述")
            return
        
        self.img_out.delete("1.0", END)
        self.img_out.insert(END, "⏳ 正在生成图片...\n")
        self.img_out.update()
        
        def task():
            try:
                from agnes import AgnesClient
                c = AgnesClient()
                # 自动保存到 outputs/images/
                path = c.generate_image_and_save(prompt, size=self.img_size.get())
                self.img_out.delete("1.0", END)
                self.img_out.insert(END, f"✅ 图片已生成\n\n📁 已保存至：{path}\n")
                # 添加打开文件夹按钮
                self.root.after(0, lambda p=path: self._add_open_btn(self.img_out, p))
            except Exception as e:
                self.img_out.delete("1.0", END)
                self.img_out.insert(END, f"❌ 错误：{e}")
        
        threading.Thread(target=task, daemon=True).start()
    
    # ── Video 标签页 ─────────────────────────────────
    def _add_tab_video(self):
        frame = Frame(self.notebook, bg=self.bg)
        self.notebook.add(frame, text="🎬 视频")
        
        card = self._make_card(frame)
        Label(card, text="视频描述：", fg=self.fg, bg=self.card_bg).pack(anchor=W)
        self.vid_input = Text(card, height=2, bg=self.input_bg, fg=self.fg,
                              insertbackground="white", font=("微软雅黑", 10))
        self.vid_input.pack(fill=X, pady=3)
        
        # 参考图
        row = Frame(card, bg=self.card_bg)
        row.pack(fill=X, pady=3)
        Label(row, text="参考图（可选）：", fg=self.fg, bg=self.card_bg).pack(side=LEFT)
        self.vid_img = Entry(row, bg=self.input_bg, fg=self.fg)
        self.vid_img.pack(side=LEFT, fill=X, expand=True, padx=5)
        Button(row, text="浏览", command=self._browse_video_img,
               bg=self.card_bg, fg="white", cursor="hand2").pack(side=LEFT)
        
        self.vid_wait = BooleanVar(value=True)
        ttk.Checkbutton(card, text="等待生成完成", variable=self.vid_wait).pack(anchor=W)
        
        Button(card, text="🚀 生成", command=self._do_video,
               bg=self.accent, fg="white", cursor="hand2").pack(anchor=E)
        
        Label(frame, text="生成结果：", fg=self.fg, bg=self.bg).pack(anchor=W, padx=5)
        self.vid_out = self._add_output_area(frame)
    
    def _browse_video_img(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename()
        if path:
            self.vid_img.delete(0, END)
            self.vid_img.insert(0, path)
    
    def _do_video(self):
        prompt = self.vid_input.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("提示", "请输入视频描述")
            return
        
        self.vid_out.delete("1.0", END)
        self.vid_out.insert(END, "⏳ 正在创建视频任务...\n")
        self.vid_out.update()
        
        def task():
            try:
                from agnes import AgnesClient
                c = AgnesClient()
                img = self.vid_img.get().strip()
                if img and not img.startswith(("http://", "https://", "data:")):
                    img = c.image_to_base64(img)
                
                # 进度回调 → GUI 更新
                def on_progress(state, progress):
                    self.root.after(0, lambda: (
                        self.vid_out.delete("1.0", END),
                        self.vid_out.insert(END,
                            f"⏳ 视频生成中...\n\n[{'█' * (progress // 5)}{'░' * (20 - progress // 5)}] {progress}%\n{state}")
                    ))
                
                # 自动等待 + 下载到 outputs/videos/
                self.root.after(0, lambda: (
                    self.vid_out.delete("1.0", END),
                    self.vid_out.insert(END, "⏳ 正在提交视频任务...\n")
                ))
                
                path = c.generate_video_and_save(
                    prompt, image_url=img or None,
                    poll_interval=3,
                    on_progress=on_progress)
                
                self.vid_out.delete("1.0", END)
                self.vid_out.insert(END, f"✅ 视频已生成\n\n📁 已保存至：{path}\n")
                self.root.after(0, lambda p=path: self._add_open_btn(self.vid_out, p))
            except Exception as e:
                self.vid_out.delete("1.0", END)
                self.vid_out.insert(END, f"❌ 错误：{e}")
        
        threading.Thread(target=task, daemon=True).start()
    
    # ── 查询标签页 ──────────────────────────────────
    def _add_tab_query(self):
        frame = Frame(self.notebook, bg=self.bg)
        self.notebook.add(frame, text="🔍 查询")
        
        card = self._make_card(frame)
        Label(card, text="查询类型：", fg=self.fg, bg=self.card_bg).pack(anchor=W)
        
        self.query_type = ttk.Combobox(card, values=["视频状态查询", "模型列表"], 
                                       state="readonly", width=20)
        self.query_type.set("视频状态查询")
        self.query_type.pack(anchor=W, pady=3)
        
        Label(card, text="video_id（视频状态查询时填写）：", fg=self.fg, 
              bg=self.card_bg).pack(anchor=W, pady=(8,0))
        self.query_input = Entry(card, bg=self.input_bg, fg=self.fg,
                                 insertbackground="white")
        self.query_input.pack(fill=X, pady=3)
        
        Button(card, text="🔍 查询", command=self._do_query,
               bg=self.accent, fg="white", cursor="hand2").pack(anchor=E)
        
        Label(frame, text="查询结果：", fg=self.fg, bg=self.bg).pack(anchor=W, padx=5)
        self.query_out = self._add_output_area(frame)
    
    def _do_query(self):
        self.query_out.delete("1.0", END)
        self.query_out.insert(END, "⏳ 查询中...\n")
        self.query_out.update()
        
        def task():
            try:
                from agnes import AgnesClient
                c = AgnesClient()
                qtype = self.query_type.get()
                
                if qtype == "视频状态查询":
                    vid = self.query_input.get().strip()
                    if not vid:
                        self.query_out.delete("1.0", END)
                        self.query_out.insert(END, "⚠️ 请输入 video_id")
                        return
                    result = c.get_video(vid)
                    import json
                    self.query_out.delete("1.0", END)
                    self.query_out.insert(END, json.dumps(result, indent=2, ensure_ascii=False))
                    
                elif qtype == "模型列表":
                    models = c.list_models()
                    self.query_out.delete("1.0", END)
                    for m in models:
                        mid = m["id"]
                        from agnes import AgnesClient
                        tp = AgnesClient.get_model_type(mid)
                        info = AgnesClient.get_model_info(mid)
                        self.query_out.insert(END, f"● {mid}\n")
                        self.query_out.insert(END, f"  类型：{tp}\n")
                        if tp == "chat" and info:
                            self.query_out.insert(END, f"  上下文：{info.get('context',0)//1000}K\n")
                            if info.get("vision"): self.query_out.insert(END, "  支持：多模态\n")
                            if info.get("thinking"): self.query_out.insert(END, "  支持：深度思考\n")
                            if info.get("tools"): self.query_out.insert(END, "  支持：工具调用\n")
                        elif tp == "image" and info:
                            self.query_out.insert(END, f"  最大尺寸：{info.get('max_size','?')}\n")
                        self.query_out.insert(END, "\n")
            except Exception as e:
                self.query_out.delete("1.0", END)
                self.query_out.insert(END, f"❌ 错误：{e}")
        
        threading.Thread(target=task, daemon=True).start()
    
    # ── 辅助方法 ─────────────────────────────────────
    def _open_folder(self, path: str = ""):
        """在文件管理器中打开输出目录。"""
        import subprocess
        folder = path or str(Path(__file__).parent / "outputs")
        if os.path.exists(folder):
            subprocess.Popen(["explorer", folder])
        else:
            messagebox.showinfo("提示", f"目录不存在：\n{folder}")

    def _refresh_api(self):
        self._check_api()
        self.root.destroy()
        self.__init__()
        
    def _launch_cli(self):
        import subprocess
        subprocess.Popen(
            ["start", "cmd", "/k", "python", "-m", "agnes.cli", "interactive"],
            shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE
        )
    
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = AgnesLauncher()
    app.run()
