# -*- coding: utf-8 -*-
"""Agnes AI 查询启动器 — 视频状态 + 模型查询"""

import os
import sys
import json
import threading
from pathlib import Path
from tkinter import *
from tkinter import ttk, messagebox, scrolledtext

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from agnes.config import load_env_into_os


class QueryTool:
    """Agnes AI 查询启动器"""

    def __init__(self):
        load_env_into_os()
        self.root = Tk()
        self.root.title("Agnes AI — 查询工具")
        self.root.geometry("650x520")
        self.root.minsize(500, 400)
        
        self.bg = "#1a1a2e"
        self.fg = "#e0e0e0"
        self.accent = "#6c63ff"
        self.card_bg = "#16213e"
        self.input_bg = "#0f3460"
        self.root.configure(bg=self.bg)
        
        self._check_api()
        self._build_ui()
    
    def _check_api(self):
        try:
            from agnes import AgnesClient
            self.client = AgnesClient()
            self.api_ok = True
        except Exception as e:
            self.api_ok = False
            self.api_err = str(e)
    
    def _build_ui(self):
        root = self.root
        
        # 标题
        header = Frame(root, bg=self.bg, pady=12)
        header.pack(fill=X)
        Label(header, text="🔍 Agnes AI 查询工具", font=("微软雅黑", 18, "bold"),
              fg="white", bg=self.bg).pack()
        Label(header, text="查询视频生成状态 · 查看模型列表", font=("微软雅黑", 9),
              fg="#aaa", bg=self.bg).pack()
        
        if self.api_ok:
            Label(header, text="✅ API 已连接", fg="#4caf50", bg=self.bg).pack()
        else:
            Label(header, text=f"❌ {getattr(self, 'api_err', '连接失败')}",
                  fg="#f44336", bg=self.bg, wraplength=500).pack()
            Button(header, text="刷新连接", command=self._refresh,
                   bg=self.accent, fg="white", cursor="hand2").pack(pady=3)
        
        # 选项卡
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=self.bg, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.card_bg, foreground="white",
                       padding=[12, 4], font=("微软雅黑", 10))
        style.map("TNotebook.Tab", background=[("selected", self.accent)])
        
        nb = ttk.Notebook(root)
        nb.pack(fill=BOTH, expand=True, padx=10, pady=5)
        
        # ── Tab 1: 视频查询 ────────────────────────
        tab1 = Frame(nb, bg=self.bg)
        nb.add(tab1, text="🎬 视频状态")
        
        card = Frame(tab1, bg=self.card_bg, padx=10, pady=8)
        card.pack(fill=X, pady=5)
        
        Label(card, text="video_id：", fg=self.fg, bg=self.card_bg,
              font=("微软雅黑", 10)).pack(anchor=W)
        
        row = Frame(card, bg=self.card_bg)
        row.pack(fill=X, pady=5)
        self.vid_id_entry = Entry(row, bg=self.input_bg, fg=self.fg,
                                  insertbackground="white", font=("Consolas", 10))
        self.vid_id_entry.pack(side=LEFT, fill=X, expand=True)
        
        Button(row, text="📋 粘贴", command=lambda: self._paste(self.vid_id_entry),
               bg=self.card_bg, fg="white", cursor="hand2").pack(side=LEFT, padx=5)
        
        btn_row = Frame(card, bg=self.card_bg)
        btn_row.pack(fill=X, pady=3)
        Button(btn_row, text="🔍 查询状态", command=self._query_video,
               bg=self.accent, fg="white", width=12, cursor="hand2").pack(side=LEFT, padx=2)
        Button(btn_row, text="🔄 轮询刷新", command=self._poll_video,
               bg="#ff9800", fg="white", width=12, cursor="hand2").pack(side=LEFT, padx=2)
        
        Label(tab1, text="查询结果：", fg=self.fg, bg=self.bg,
              font=("微软雅黑", 9)).pack(anchor=W, padx=5)
        
        self.vid_out = scrolledtext.ScrolledText(tab1, height=10, bg=self.input_bg,
                                                 fg=self.fg, insertbackground="white",
                                                 font=("Consolas", 10), wrap=WORD)
        self.vid_out.pack(fill=BOTH, expand=True, pady=5)
        
        # ── Tab 2: 模型列表 ─────────────────────────
        tab2 = Frame(nb, bg=self.bg)
        nb.add(tab2, text="📋 模型列表")
        
        Button(tab2, text="🔄 刷新模型列表", command=self._query_models,
               bg=self.accent, fg="white", cursor="hand2").pack(pady=8)
        
        self.model_out = scrolledtext.ScrolledText(tab2, height=15, bg=self.input_bg,
                                                   fg=self.fg, insertbackground="white",
                                                   font=("Consolas", 10), wrap=WORD)
        self.model_out.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # 底部
        footer = Frame(root, bg=self.bg, pady=6)
        footer.pack(fill=X)
        Button(footer, text="❌ 退出", command=root.destroy,
               bg="#333", fg="white", cursor="hand2").pack(side=RIGHT, padx=10)
        Label(footer, text="查询工具 v1.0", fg="#555", bg=self.bg,
              font=("微软雅黑", 8)).pack(side=LEFT, padx=10)
    
    def _paste(self, entry):
        try:
            entry.delete(0, END)
            entry.insert(0, root.clipboard_get())
        except Exception:
            pass
    
    def _query_video(self):
        vid = self.vid_id_entry.get().strip()
        if not vid:
            messagebox.showwarning("提示", "请输入 video_id")
            return
        
        self.vid_out.delete("1.0", END)
        self.vid_out.insert(END, "⏳ 查询中...\n")
        
        def task():
            try:
                if not self.api_ok:
                    self.vid_out.delete("1.0", END)
                    self.vid_out.insert(END, "❌ API 未连接，请刷新")
                    return
                result = self.client.get_video(vid)
                self.vid_out.delete("1.0", END)
                self.vid_out.insert(END, json.dumps(result, indent=2, ensure_ascii=False))
                
                # 额外提示
                status = result.get("internal_status", result.get("status", ""))
                if status == "completed":
                    self.vid_out.insert(END, "\n\n✅ 视频已生成完成！")
                    url = result.get("url", result.get("data", {}).get("url", ""))
                    if url:
                        self.vid_out.insert(END, f"\n📎 视频链接：{url}")
                elif status in ("failed", "error"):
                    self.vid_out.insert(END, "\n\n❌ 视频生成失败")
                elif status:
                    self.vid_out.insert(END, f"\n⏳ 当前状态：{status}")
            except Exception as e:
                self.vid_out.delete("1.0", END)
                self.vid_out.insert(END, f"❌ 查询失败：{e}")
        
        threading.Thread(target=task, daemon=True).start()
    
    def _poll_video(self):
        vid = self.vid_id_entry.get().strip()
        if not vid:
            messagebox.showwarning("提示", "请输入 video_id")
            return
        
        self.vid_out.delete("1.0", END)
        self.vid_out.insert(END, "🔄 开始轮询（每5秒刷新一次）\n\n")
        
        def task():
            try:
                if not self.api_ok:
                    self.vid_out.insert(END, "❌ API 未连接")
                    return
                import time
                for i in range(60):  # 最多轮询 5 分钟
                    result = self.client.get_video(vid)
                    status = result.get("internal_status", result.get("status", ""))
                    progress = result.get("progress", 0)
                    
                    # 只更新最后一行
                    self.vid_out.delete("1.0", END)
                    bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
                    self.vid_out.insert(END, f"[{bar}] {progress}% 状态：{status}\n")
                    
                    if status in ("completed", "done", "succeeded"):
                        url = result.get("url", result.get("data", {}).get("url", ""))
                        self.vid_out.insert(END, f"\n✅ 视频生成完成！")
                        if url:
                            self.vid_out.insert(END, f"\n📎 {url}")
                        break
                    elif status in ("failed", "error"):
                        self.vid_out.insert(END, f"\n❌ 生成失败")
                        break
                    
                    time.sleep(5)
                else:
                    self.vid_out.insert(END, "\n⏰ 轮询超时，请手动查询")
            except Exception as e:
                self.vid_out.insert(END, f"\n❌ 错误：{e}")
        
        threading.Thread(target=task, daemon=True).start()
    
    def _query_models(self):
        self.model_out.delete("1.0", END)
        self.model_out.insert(END, "⏳ 加载中...\n")
        
        def task():
            try:
                if not self.api_ok:
                    self.model_out.delete("1.0", END)
                    self.model_out.insert(END, "❌ API 未连接")
                    return
                models = self.client.list_models()
                from agnes import AgnesClient
                self.model_out.delete("1.0", END)
                self.model_out.insert(END, f"共 {len(models)} 个模型\n\n")
                for m in models:
                    mid = m["id"]
                    tp = AgnesClient.get_model_type(mid)
                    info = AgnesClient.get_model_info(mid)
                    
                    self.model_out.insert(END, f"● {mid}\n")
                    self.model_out.insert(END, f"  类型：{tp}\n")
                    
                    if tp == "chat":
                        self.model_out.insert(END, f"  上下文：{info.get('context',0)//1000}K\n")
                        self.model_out.insert(END, f"  最大输出：{info.get('max_output',0)//1000}K\n")
                        caps = []
                        if info.get("vision"): caps.append("多模态")
                        if info.get("tools"): caps.append("工具调用")
                        if info.get("thinking"): caps.append("深度思考")
                        if info.get("stream"): caps.append("流式输出")
                        if caps:
                            self.model_out.insert(END, f"  能力：{'、'.join(caps)}\n")
                    elif tp == "image":
                        self.model_out.insert(END, f"  最大尺寸：{info.get('max_size','?')}\n")
                        if info.get("img2img"):
                            self.model_out.insert(END, f"  支持：图生图\n")
                    elif tp == "video":
                        self.model_out.insert(END, f"  默认尺寸：{info.get('default_size','?')}\n")
                        if info.get("img2video"):
                            self.model_out.insert(END, f"  支持：图生视频\n")
                    self.model_out.insert(END, "\n")
            except Exception as e:
                self.model_out.delete("1.0", END)
                self.model_out.insert(END, f"❌ 加载失败：{e}")
        
        threading.Thread(target=task, daemon=True).start()
    
    def _refresh(self):
        self._check_api()
        self.root.destroy()
        self.__init__()
    
    def run(self):
        if self.api_ok:
            self._query_models()  # 自动加载模型列表
        self.root.mainloop()


if __name__ == "__main__":
    app = QueryTool()
    app.run()
