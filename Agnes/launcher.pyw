# -*- coding: utf-8 -*-
"""Agnes AI 启动器 — 图形界面版（重构后，薄壳架构）

改动：Tab 功能页改为 Feature 延迟加载，启动时不再一次性导入全部模块。
"""

from __future__ import annotations

import os
import subprocess
import sys
from tkinter import *
from tkinter import ttk, messagebox

import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agnes.config import load_env_into_os, has_api_key, show_setup_dialog
from agnes.gui.feature_manager import FeatureManager, FeatureInfo
from agnes.runtime.app_context import AppContext
from agnes.runtime.theme import Theme


class AgnesLauncher:
    """Agnes AI 图形启动器（薄壳版）。"""

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

        # 主题
        self.theme = Theme()
        self.root.configure(bg=self.theme.bg)

        # 初始化上下文（单一长生命周期 API Client）
        self.api_ok = False
        self.models: list[dict] = []
        self._api_error = ""
        self._ctx: AppContext | None = None

        self._init_api()
        self._build_ui()

    # ── API 初始化 ──────────────────────────────────────

    def _init_api(self) -> None:
        """尝试创建 API 客户端。"""
        try:
            self._ctx = AppContext.create_default()
            self.models = self._ctx.client.list_models()
            self.api_ok = True
        except Exception as e:
            self.api_ok = False
            self._api_error = str(e)
            try:
                self._ctx = AppContext.create_default()
            except Exception:
                pass

    def _refresh_api(self) -> None:
        self._init_api()
        self._build_ui()

    # ── UI 构建 ─────────────────────────────────────────

    def _build_ui(self) -> None:
        """重建整个界面（刷新 API 状态时调用）。"""
        for child in self.root.winfo_children():
            child.destroy()

        # 标题栏
        header = Frame(self.root, bg=self.theme.bg, pady=15)
        header.pack(fill=X)
        Label(header, text="▎Agnes AI 工具箱", font=("微软雅黑", 20, "bold"),
              fg="white", bg=self.theme.bg).pack()
        Label(header, text="多模态 AI — 对话 · 图片 · 视频", font=("微软雅黑", 10),
              fg="#aaa", bg=self.theme.bg).pack()

        # API 状态栏
        status_frame = Frame(self.root, bg=self.theme.bg, pady=5)
        status_frame.pack(fill=X)

        if self.api_ok:
            colors = {"chat": "#4fc3f7", "image": "#ff9800", "video": "#ab47bc"}
            for m in self.models:
                if self._ctx is not None:
                    tp = self._ctx.client.get_model_type(m["id"])
                else:
                    tp = "unknown"
                c = colors.get(tp, "#888")
                Label(status_frame, text=f"● {m['id']}", fg=c, bg=self.theme.bg,
                      font=("微软雅黑", 8)).pack(side=LEFT, padx=8)
            Label(status_frame, text="✅ API 已连接", fg=self.theme.success,
                  bg=self.theme.bg, font=("微软雅黑", 9)).pack(side=RIGHT, padx=10)
        else:
            Label(status_frame,
                  text=f"❌ API 未连接：{self._api_error or '未知错误'}",
                  fg=self.theme.error, bg=self.theme.bg,
                  wraplength=600).pack(pady=5)
            Button(status_frame, text="刷新", command=self._refresh_api,
                   bg=self.theme.accent, fg="white", cursor="hand2").pack(pady=3)

        # Notebook 选项卡
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=self.theme.bg, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.theme.card_bg,
                        foreground="white", padding=[12, 4],
                        font=("微软雅黑", 10))
        style.map("TNotebook.Tab", background=[("selected", self.theme.accent)])

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=True, padx=10, pady=5)

        # Feature 管理器（延迟加载核心）
        if self.api_ok and self._ctx is not None:
            self.feature_mgr = FeatureManager(self.notebook, self._ctx)
            self.feature_mgr.register(FeatureInfo(
                name="chat",
                module_path="agnes.features.chat_feature",
                class_name="ChatFeature",
                title="💬 对话",
            ))
            self.feature_mgr.register(FeatureInfo(
                name="vision",
                module_path="agnes.features.vision_feature",
                class_name="VisionFeature",
                title="👁 识图",
            ))
            self.feature_mgr.register(FeatureInfo(
                name="image",
                module_path="agnes.features.image_feature",
                class_name="ImageFeature",
                title="🎨 绘图",
            ))
            self.feature_mgr.register(FeatureInfo(
                name="video",
                module_path="agnes.features.video_feature",
                class_name="VideoFeature",
                title="🎬 视频",
            ))
            self.feature_mgr.register(FeatureInfo(
                name="query",
                module_path="agnes.features.query_feature",
                class_name="QueryFeature",
                title="🔍 查询",
            ))

        # 底部按钮
        bottom = Frame(self.root, bg=self.theme.bg, pady=8)
        bottom.pack(fill=X, side=BOTTOM)
        Button(bottom, text="📟 打开命令行", command=self._launch_cli,
               bg=self.theme.card_bg, fg="white", cursor="hand2",
               font=("微软雅黑", 9)).pack(side=LEFT, padx=10)

    # ── 辅助方法 ────────────────────────────────────────

    def _launch_cli(self) -> None:
        subprocess.Popen(
            ["start", "cmd", "/k", "python", "-m", "agnes", "interactive"],
            shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    app = AgnesLauncher()
    app.run()
