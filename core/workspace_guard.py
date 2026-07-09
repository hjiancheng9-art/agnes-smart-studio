"""
CRUX Workspace Guard — 防止工具把自身仓库当项目 workspace

用法:
  guard = WorkspaceGuard(cwd)
  guard.check()  # 如果 cwd 是 CRUX 自身仓库，打印警告

环境变量:
  CRUX_WORKSPACE  — 显式指定目标项目路径
  --workspace     — CLI 参数（优先级高于环境变量）
"""

import os
from pathlib import Path


def get_crux_root() -> Path:
    """返回 CRUX 工具自身的根目录"""
    return Path(__file__).resolve().parent.parent


def is_crux_self(path: Path) -> bool:
    """检查 path 是否是 CRUX 自身仓库"""
    crux_root = get_crux_root()
    try:
        return path.resolve() == crux_root.resolve()
    except Exception:
        return False


def resolve_workspace(cli_workspace: str | None = None) -> Path:
    """
    按优先级返回 workspace：
    1. CLI --workspace 参数
    2. CRUX_WORKSPACE 环境变量
    3. 当前工作目录（如果非 CRUX 自身）
    """
    # 1. CLI 参数
    if cli_workspace:
        wp = Path(cli_workspace).resolve()
        if wp.exists():
            return wp
        print(f"⚠️  --workspace 路径不存在: {wp}，回退")

    # 2. 环境变量
    env_ws = os.environ.get("CRUX_WORKSPACE")
    if env_ws:
        wp = Path(env_ws).resolve()
        if wp.exists():
            return wp
        print(f"⚠️  CRUX_WORKSPACE 路径不存在: {wp}，回退")

    # 3. 当前工作目录
    cwd = Path.cwd().resolve()

    # 检查是否在使用 CRUX 自身
    if is_crux_self(cwd):
        crux_root = get_crux_root()
        print("=" * 60)
        print("⚠️  WARNING: 当前工作目录是 CRUX 自身源码仓库!")
        print(f"    CRUX ROOT: {crux_root}")
        print(f"    CWD:       {cwd}")
        print()
        print("    在此目录下运行 CRUX 会把输出文件写入工具自身源码。")
        print("    建议: 用 --workspace 指定目标项目路径")
        print()
        print("    例如: crux --workspace C:\\path\\to\\your\\project")
        print("    或者: set CRUX_WORKSPACE=C:\\path\\to\\your\\project && crux")
        print("=" * 60)
        print()

    return cwd


class WorkspaceGuard:
    """文件写入路径守卫 — 阻止写入 CRUX 自身目录"""

    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace).resolve()

    def resolve(self, relative_path: str) -> Path:
        target = (self.workspace / relative_path).resolve()
        crux_root = get_crux_root()

        # 拒绝写入 CRUX 自身目录
        if str(target).startswith(str(crux_root)):
            raise RuntimeError(
                f"❌ 拒绝写入 CRUX 自身目录: {target}\n"
                f"   请使用 --workspace 指定目标项目路径"
            )

        return target

    def write_text(self, relative_path: str, content: str) -> None:
        target = self.resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
