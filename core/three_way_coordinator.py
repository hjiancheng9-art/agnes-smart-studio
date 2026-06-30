"""三向协同器 — CRUX × Kimi × Copilot 任务委派。

Three-way coordination utility:
    CRUX (主脑)  → 规划/决策/验证
    Kimi (DeepSeek)  → 深度推理 + 中文代码理解
    Copilot (GPT-5-mini)  → 快速实现 + GitHub 集成

使用方式:
    from core.three_way_coordinator import ThreeWayCoordinator
    coord = ThreeWayCoordinator()
    result = coord.dispatch("探索用户认证模块的 bug", to="kimi")
    # or
    results = coord.parallel({
        "kimi": "分析认证流程的安全性",
        "copilot": "审查认证代码质量",
    })

状态检查:
    coord.status() → {"kimi": {...}, "copilot": {...}, "crux": {...}}
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from core.mcp_servers._mcp_utils import run_subprocess

__all__ = ["ThreeWayCoordinator", "SystemStatus", "get_coordinator"]

WORK_DIR = str(Path(__file__).resolve().parent.parent)


@dataclass
class SystemStatus:
    name: str
    available: bool
    version: str = ""
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "version": self.version,
            "model": self.model,
            "error": self.error,
        }


class ThreeWayCoordinator:
    """三向协同器：信息枢纽 + 任务路由。"""

    def __init__(self, work_dir: str = ""):
        self.work_dir = work_dir or WORK_DIR

    # ── 状态检查 ──

    def check_kimi(self) -> SystemStatus:
        try:
            import shutil
            kimi = (
                shutil.which("kimi")
                or os.path.expanduser("~/.kimi-code/bin/kimi.EXE")
                or os.path.expanduser("~/.kimi-code/bin/kimi")
            )
            if not kimi or not os.path.isfile(kimi):
                return SystemStatus(name="kimi", available=False, error="kimi CLI 未安装")

            r = run_subprocess([kimi, "--version"], timeout=10)
            version = r.stdout.strip() if r.returncode == 0 else "unknown"

            # 检查登录
            logged_in = False
            try:
                r2 = run_subprocess([kimi, "-p", "ok", "--output-format", "text"], timeout=20)
                logged_in = r2.returncode == 0 and "error" not in r2.stderr.lower()
            except Exception:
                pass

            return SystemStatus(
                name="kimi",
                available=logged_in,
                version=version,
                model="deepseek-v4 (via Kimi)",
                error="" if logged_in else "未登录: kimi login",
            )
        except Exception as e:
            return SystemStatus(name="kimi", available=False, error=str(e))

    def check_copilot(self) -> SystemStatus:
        try:
            import shutil
            copilot = (
                shutil.which("copilot")
                or os.path.expanduser("~/AppData/Roaming/npm/copilot.CMD")
            )
            if not copilot or not os.path.isfile(copilot):
                return SystemStatus(name="copilot", available=False, error="Copilot CLI 未安装")

            r = run_subprocess([copilot, "--version"], timeout=10)
            version = r.stdout.strip() if r.returncode == 0 else "unknown"

            # 检查 gh 登录
            logged_in = False
            try:
                r2 = run_subprocess(["gh", "auth", "status"], timeout=10)
                logged_in = r2.returncode == 0
            except Exception:
                pass

            return SystemStatus(
                name="copilot",
                available=logged_in,
                version=version,
                model="gpt-5-mini (via Copilot)",
                error="" if logged_in else "未登录: gh auth login",
            )
        except Exception as e:
            return SystemStatus(name="copilot", available=False, error=str(e))

    def check_crux(self) -> SystemStatus:
        return SystemStatus(
            name="crux",
            available=True,
            version="v5.0",
            model="deepseek-v4-pro",
            error="",
        )

    def status(self) -> dict:
        """获取三系统状态。"""
        return {
            "crux": self.check_crux().to_dict(),
            "kimi": self.check_kimi().to_dict(),
            "copilot": self.check_copilot().to_dict(),
        }

    # ── 智能路由 ──

    def route(self, task: str) -> str:
        """根据任务特征自动选择最佳系统。

        启发式:
        - 中文代码/深度推理 → kimi (DeepSeek 中文最强)
        - 快速PR/代码审查/安全审查 → copilot (GPT-5-mini + GitHub集成)
        - 规划/生成/创意/复杂编排 → crux (主脑)
        """
        task_lower = task.lower()
        keywords = {
            "kimi": ["中文", "chinese", "深度推理", "架构分析", "方案设计", "review design", "architecture"],
            "copilot": ["pr", "pull request", "代码审查", "code review", "安全审查", "security", "/review", "快速", "quick"],
            "crux": ["生成", "generate", "视频", "video", "图片", "image", "规划", "plan", "编排", "orchestrate", "协调", "coordinate"],
        }
        scores = {"kimi": 0, "copilot": 0, "crux": 1}  # crux 默认
        for system, kws in keywords.items():
            for kw in kws:
                if kw in task_lower:
                    scores[system] += 1
        return max(scores, key=scores.get)

    # ── 能力矩阵 ──

    CAPABILITY_MATRIX = {
        "kimi": {
            "explore": True, "code": True, "review": True, "think": True,
            "chinese_expert": True, "github_pr": False, "security_review": False,
            "model": "deepseek-v4",
        },
        "copilot": {
            "explore": True, "code": True, "review": True, "think": True,
            "chinese_expert": False, "github_pr": True, "security_review": True,
            "model": "gpt-5-mini",
        },
        "crux": {
            "explore": True, "code": True, "review": True, "think": True,
            "chinese_expert": True, "github_pr": True, "security_review": True,
            "generate_image": True, "generate_video": True, "comfyui": True,
            "model": "deepseek-v4-pro",
        },
    }

    def can_do(self, system: str, capability: str) -> bool:
        return self.CAPABILITY_MATRIX.get(system, {}).get(capability, False)

    def best_for(self, capability: str) -> list[str]:
        """返回支持该能力的所有系统（按推荐度排序）。"""
        return [
            s for s in ["crux", "kimi", "copilot"]
            if self.can_do(s, capability)
        ]

    # ── 诊断报告 ──

    def diagnose(self) -> str:
        """生成三系统诊断报告。"""
        st = self.status()
        lines = ["# Three-Way System Diagnostic", ""]

        for name, info in st.items():
            icon = "[OK]" if info["available"] else "[OFFLINE]"
            lines.append(f"## {icon} {name.upper()}")
            lines.append(f"- Model: {info['model']}")
            lines.append(f"- Version: {info['version']}")
            if info["error"]:
                lines.append(f"- Error: {info['error']}")
            lines.append("")

        lines.append("## Capability Matrix")
        lines.append("| Capability | CRUX | Kimi | Copilot |")
        lines.append("|-----------|------|------|---------|")
        for cap in ["explore", "code", "review", "think", "chinese_expert", "github_pr", "security_review", "generate_image", "generate_video"]:
            c = "Y" if self.can_do("crux", cap) else "-"
            k = "Y" if self.can_do("kimi", cap) else "-"
            p = "Y" if self.can_do("copilot", cap) else "-"
            lines.append(f"| {cap} | {c} | {k} | {p} |")

        lines.append("")
        lines.append("## Routing Suggestions")
        lines.append("- 中文代码 + 深度推理 → Kimi (DeepSeek V4)")
        lines.append("- 快速PR + 代码/安全审查 → Copilot (GPT-5-mini)")
        lines.append("- 创意生成 + 复杂编排 → CRUX (主脑)")

        return "\n".join(lines)


# ── 全局实例 ──

_coordinator: ThreeWayCoordinator | None = None


def get_coordinator() -> ThreeWayCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = ThreeWayCoordinator()
    return _coordinator


# ── CLI 入口 ──

if __name__ == "__main__":
    import sys
    coord = ThreeWayCoordinator()

    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps(coord.status(), ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "diagnose":
        print(coord.diagnose())
    elif len(sys.argv) > 1 and sys.argv[1] == "route":
        task = " ".join(sys.argv[2:])
        best = coord.route(task)
        print(f"Route: {best} (task: {task})")
    else:
        print(coord.diagnose())
