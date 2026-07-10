"""Agnes 配置管理 — 安全存储 API Key 到用户目录"""

import os
import sys
import json
from pathlib import Path

APP_NAME = "Agnes"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def get_app_dir() -> Path:
    """获取应用根目录（兼容 PyInstaller 打包）"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_resource_dir() -> Path:
    """获取资源目录（打包后指向 sys._MEIPASS）"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return get_app_dir()


def load_config() -> dict:
    """加载配置：用户目录 config.json > 环境变量 > .env"""
    config = {}

    # 1. 用户目录 config.json
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # 2. 环境变量覆盖
    env_map = {"AGNES_API_KEY": "agnes_api_key", "AGNES_API_BASE": "agnes_api_base",
               "AGNES_TIMEOUT": "agnes_timeout"}
    for env_key, cfg_key in env_map.items():
        if env_key in os.environ:
            config[cfg_key] = os.environ[env_key]

    # 3. .env fallback（开发环境）
    if not config.get("agnes_api_key") and ENV_FILE.exists():
        _load_env_file(ENV_FILE, config)

    return config


def save_config(config: dict) -> None:
    """保存配置到 %APPDATA%/Agnes/config.json"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_env_file(env_path: Path, config: dict) -> None:
    """解析 .env 文件到 config dict"""
    for line in env_path.read_text(encoding="utf-8").split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip("\"'")
        if k == "AGNES_API_KEY" and not config.get("agnes_api_key"):
            config["agnes_api_key"] = v
        elif k == "AGNES_API_BASE" and not config.get("agnes_api_base"):
            config["agnes_api_base"] = v
        elif k == "AGNES_TIMEOUT" and not config.get("agnes_timeout"):
            config["agnes_timeout"] = v


def load_env_into_os() -> None:
    """加载配置到 os.environ（供 client.py 的 os.getenv 读取）"""
    config = load_config()
    mappings = {"agnes_api_key": "AGNES_API_KEY", "agnes_api_base": "AGNES_API_BASE",
                "agnes_timeout": "AGNES_TIMEOUT"}
    for cfg_key, env_key in mappings.items():
        if config.get(cfg_key):
            os.environ.setdefault(env_key, str(config[cfg_key]))


def has_api_key() -> bool:
    """检查是否已配置 API Key"""
    config = load_config()
    return bool(config.get("agnes_api_key") or os.environ.get("AGNES_API_KEY"))


def show_setup_dialog() -> bool:
    """首次运行引导对话框 — 让用户输入 API Key"""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("Agnes — 首次设置")
    root.geometry("520x300")
    root.resizable(False, False)
    root.configure(bg="#1a1a2e")

    root.update_idletasks()
    x = (root.winfo_screenwidth() - 520) // 2
    y = (root.winfo_screenheight() - 300) // 2
    root.geometry(f"+{x}+{y}")

    result = [False]

    def on_ok():
        key = entry_key.get().strip()
        base = entry_base.get().strip()
        if not key:
            messagebox.showwarning("提示", "请输入 API Key")
            return
        config = {"agnes_api_key": key}
        if base:
            config["agnes_api_base"] = base
        save_config(config)
        load_env_into_os()
        result[0] = True
        root.destroy()

    def on_skip():
        root.destroy()

    tk.Label(root, text="🔑 Agnes 首次使用设置", font=("微软雅黑", 16, "bold"),
             fg="#e0e0e0", bg="#1a1a2e").pack(pady=(20, 5))
    tk.Label(root, text="请填入你的 API Key 来开始使用", font=("微软雅黑", 10),
             fg="#aaa", bg="#1a1a2e").pack(pady=(0, 15))

    frame = tk.Frame(root, bg="#1a1a2e")
    frame.pack(padx=40, fill="x")

    tk.Label(frame, text="API Key *", font=("微软雅黑", 10),
             fg="#e0e0e0", bg="#1a1a2e", anchor="w").pack(fill="x")
    entry_key = tk.Entry(frame, font=("Consolas", 10), bd=2, relief="solid", show="*",
                         bg="#0f3460", fg="#e0e0e0", insertbackground="#e0e0e0")
    entry_key.pack(fill="x", pady=(2, 10))

    tk.Label(frame, text="API Base（可选）", font=("微软雅黑", 10),
             fg="#e0e0e0", bg="#1a1a2e", anchor="w").pack(fill="x")
    entry_base = tk.Entry(frame, font=("Consolas", 10), bd=2, relief="solid",
                          bg="#0f3460", fg="#e0e0e0", insertbackground="#e0e0e0")
    entry_base.insert(0, "https://apihub.agnes-ai.com/v1")
    entry_base.pack(fill="x", pady=(2, 15))

    btn_frame = tk.Frame(root, bg="#1a1a2e")
    btn_frame.pack(pady=5)

    tk.Button(btn_frame, text="✅ 确认", font=("微软雅黑", 10), bg="#6c63ff", fg="white",
              command=on_ok, bd=0, padx=30, pady=5, cursor="hand2").pack(side="left", padx=5)
    tk.Button(btn_frame, text="跳过", font=("微软雅黑", 10), bg="#333", fg="#aaa",
              command=on_skip, bd=0, padx=20, pady=5, cursor="hand2").pack(side="left", padx=5)

    root.mainloop()
    return result[0]
