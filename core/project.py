"""项目管理 — 每项目独立会话、智能体团队、文件历史、部署集成

用法:
    from core.project import Project, run_team

    # 项目管理
    p = Project("my-app")                  # 创建/打开项目
    p.save_session("s1", messages)         # 保存对话历史
    msgs = p.load_session("s1")            # 恢复对话历史
    p.record_file_change("main.py", "modified")  # 记录文件变更
    stats = p.analyze_codebase()           # 统计文件/语言/行数

    # 智能体团队（3人并行审查/调试/开发）
    result = run_team(client, "review", code_context)

    # 一键部署
    deploy_to_vercel("./project")
"""

import json
import os
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# 项目数据存储根目录
PROJECTS_DIR = Path(__file__).parent.parent / "output" / "projects"


# ════════════════════════════════════════════════
#  项目管理
# ════════════════════════════════════════════════

class Project:
    """一个工作项目 — 管理独立的会话历史、文件变更记录和代码分析

    目录结构:
        output/projects/<name>/
            project.json          # 项目配置（摘要、依赖、最后访问时间）
            sessions/              # 对话历史（每个会话一个 JSON 文件）
            history/               # 文件变更记录（每次变更一个 JSON 文件）
    """

    def __init__(self, name: str, root_path: str = ""):
        self.name = name                                        # 项目名称
        self.root = Path(root_path) if root_path else PROJECTS_DIR / name  # 项目根目录
        self.root.mkdir(parents=True, exist_ok=True)            # 确保目录存在
        self.config_path = self.root / "project.json"           # 项目配置文件
        self.sessions_path = self.root / "sessions"             # 会话保存目录
        self.history_path = self.root / "history"               # 文件历史目录
        self.sessions_path.mkdir(exist_ok=True)                 # 创建会话目录
        self.history_path.mkdir(exist_ok=True)                  # 创建历史目录

    # ── 项目配置 ──────────────────────────────────

    def load_config(self) -> dict:
        """加载项目配置，如果不存在则返回默认配置"""
        if self.config_path.exists():
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        return {"name": self.name, "created": datetime.now().isoformat(),
                "summary": "", "files": [], "dependencies": [], "last_access": ""}

    def save_config(self, cfg: dict):
        """保存项目配置，自动更新最后访问时间"""
        cfg["last_access"] = datetime.now().isoformat()
        self.config_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    def set_summary(self, text: str):
        """更新项目摘要（AI 可自动生成）"""
        cfg = self.load_config()
        cfg["summary"] = text
        self.save_config(cfg)

    # ── 会话持久化 ────────────────────────────────

    def save_session(self, session_id: str, messages: list[dict]):
        """保存完整对话历史到 JSON 文件

        Args:
            session_id: 会话 ID（如 "20260617_143000"）
            messages: 对话消息列表 [{role, content}, ...]
        """
        path = self.sessions_path / f"{session_id}.json"
        path.write_text(json.dumps({
            "id": session_id,
            "saved_at": datetime.now().isoformat(),
            "messages": messages,           # 完整消息列表，恢复时不丢失上下文
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_session(self, session_id: str) -> Optional[list[dict]]:
        """从文件恢复对话历史

        Returns:
            消息列表或 None（会话不存在）
        """
        path = self.sessions_path / f"{session_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("messages", [])

    def list_sessions(self) -> list[dict]:
        """列出最近 10 个会话（按保存时间倒序）"""
        sessions = []
        for f in sorted(self.sessions_path.glob("*.json"), reverse=True):
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "id": data.get("id", f.stem),       # 会话 ID
                "saved_at": data.get("saved_at", ""),  # 保存时间
                "messages": len(data.get("messages", [])),  # 消息数
            })
        return sessions[:10]

    # ── 文件变更历史 ──────────────────────────────

    def record_file_change(self, filepath: str, kind: str, content_preview: str = ""):
        """记录一次文件变更（创建/修改/删除）

        每次变更存为一个独立 JSON 文件，按时间戳命名，
        方便回溯和 diff。

        Args:
            filepath: 文件路径
            kind: 变更类型 — "created" / "modified" / "deleted"
            content_preview: 变更内容预览（最多 200 字符）
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")        # 时间戳作为文件名
        entry = {
            "file": filepath,
            "kind": kind,
            "time": datetime.now().isoformat(),
            "preview": content_preview[:200],                 # 截断避免文件过大
        }
        path = self.history_path / f"{ts}.json"
        path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_file_history(self, limit: int = 20) -> list[dict]:
        """获取最近 N 条文件变更记录（倒序，最新在前）"""
        entries = []
        for f in sorted(self.history_path.glob("*.json"), reverse=True):
            entries.append(json.loads(f.read_text(encoding="utf-8")))
            if len(entries) >= limit:
                break
        return entries

    # ── 代码库分析 ────────────────────────────────

    def analyze_codebase(self) -> dict:
        """统计项目文件数量、语言分布、总行数

        跳过 .git / __pycache__ / node_modules / venv

        Returns:
            {"files": N, "languages": {".py": M, ...}, "total_lines": L}
        """
        stats = {"files": 0, "languages": {}, "total_lines": 0}
        if not self.root.exists():
            return stats

        for f in self.root.rglob("*"):
            # 跳过隐藏文件和常见忽略目录
            if f.is_file() and f.suffix and not any(
                p in f.parts for p in (".git", "__pycache__", "node_modules", "venv")
            ):
                stats["files"] += 1
                ext = f.suffix.lower()                         # 按扩展名统计语言
                stats["languages"][ext] = stats["languages"].get(ext, 0) + 1
                try:
                    stats["total_lines"] += sum(1 for _ in open(f, encoding="utf-8", errors="replace"))
                except Exception:
                    pass  # 二进制文件跳过
        return stats


# ════════════════════════════════════════════════
#  智能体团队 — 多人并行审查/调试/开发
# ════════════════════════════════════════════════

# 三种预置团队配置，每种 3 名成员，各司其职
TEAM_CONFIGS = {
    "review": {
        "name": "代码审查团队",
        "agents": [
            {"role": "安全审查", "prompt": "检查代码安全漏洞、注入风险、权限问题"},
            {"role": "性能审查", "prompt": "检查性能瓶颈、内存泄漏、N+1 查询"},
            {"role": "风格审查", "prompt": "检查代码规范、命名、注释、类型注解"},
        ],
    },
    "debug": {
        "name": "调试团队",
        "agents": [
            {"role": "根因分析", "prompt": "分析错误根因，不看表象"},
            {"role": "日志追踪", "prompt": "根据日志上下文追踪调用链"},
            {"role": "修复方案", "prompt": "给出 3 种修复方案，比较优劣"},
        ],
    },
    "feature": {
        "name": "功能开发团队",
        "agents": [
            {"role": "架构设计", "prompt": "设计功能架构、接口、数据流"},
            {"role": "实现编码", "prompt": "编写完整代码，带类型和测试"},
            {"role": "质量审查", "prompt": "审查代码质量、边界情况、错误处理"},
        ],
    },
}


def run_team(client, team_type: str, context: str, model: str = "agnes-2.0-flash") -> dict:
    """启动智能体团队并行分析

    每个成员收到相同的上下文但不同的角色提示词，并行调用 LLM。
    注意：当前为顺序调用（非真正并行的子进程），未来可升级为 asyncio。

    Args:
        client: AgnesClient 实例
        team_type: "review" / "debug" / "feature"
        context: 分析上下文（代码、日志、需求描述等，最多 3000 字符）
        model: LLM 模型

    Returns:
        {
            "team": "代码审查团队",
            "agents": [{"role": "安全审查", "output": "..."}, ...],
            "summary": "汇总文本"
        }
    """
    team = TEAM_CONFIGS.get(team_type)
    if not team:
        return {"error": f"未知团队类型: {team_type}，可选: {list(TEAM_CONFIGS.keys())}"}

    results = []
    for agent_cfg in team["agents"]:
        # 构造角色特定的 prompt
        prompt = f"{agent_cfg['prompt']}\n\n上下文:\n{context[:3000]}"
        messages = [
            {"role": "system", "content": f"你是 {agent_cfg['role']}。简洁、精准、给具体建议。"},
            {"role": "user", "content": prompt},
        ]
        try:
            r = client.chat(model=model, messages=messages, max_tokens=1024)
            output = r["choices"][0]["message"]["content"] or ""
        except Exception as e:
            output = f"[失败] {e}"  # 单个成员失败不阻断团队
        results.append({"role": agent_cfg["role"], "output": output})

    # 汇总所有成员输出
    summary = f"**{team['name']}** ({len(results)} 名成员)\n\n"
    for r in results:
        summary += f"### {r['role']}\n{r['output'][:500]}\n\n"

    return {"team": team["name"], "agents": results, "summary": summary}


# ════════════════════════════════════════════════
#  部署集成 — Vercel / Netlify / GitHub Pages
# ════════════════════════════════════════════════

def deploy_to_vercel(project_path: str, token: str = "") -> str:
    """部署到 Vercel（需安装 vercel CLI: npm i -g vercel）

    Args:
        project_path: 项目目录路径
        token: Vercel API token（可选，不传则用已登录的 CLI）
    """
    cmd = f"cd {project_path} && vercel --prod --yes"
    if token:
        cmd = f"cd {project_path} && vercel --prod --yes --token {token}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return r.stdout.strip() or r.stderr.strip() or "[部署完成]"
    except Exception as e:
        return f"[部署失败] {e}"


def deploy_to_netlify(project_path: str, token: str = "") -> str:
    """部署到 Netlify（需安装 netlify CLI: npm i -g netlify-cli）

    Args:
        project_path: 项目目录路径
        token: Netlify auth token（可选）
    """
    cmd = f"cd {project_path} && netlify deploy --prod"
    if token:
        cmd += f" --auth {token}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return r.stdout.strip() or r.stderr.strip() or "[部署完成]"
    except Exception as e:
        return f"[部署失败] {e}"


def deploy_to_github_pages(project_path: str) -> str:
    """部署到 GitHub Pages（需 gh-pages: npm i -g gh-pages）

    流程: 构建 → 推送到 gh-pages 分支
    """
    cmds = [
        f"cd {project_path}",
        "npm run build 2>/dev/null || echo 'no build script'",           # 尝试构建
        "npx gh-pages -d build 2>/dev/null || npx gh-pages -d dist 2>/dev/null || echo 'need gh-pages: npm i -g gh-pages'",  # 部署 build 或 dist 目录
    ]
    try:
        result = subprocess.run(" && ".join(cmds), shell=True, capture_output=True, text=True, timeout=120)
        return result.stdout.strip() or "[部署完成]"
    except Exception as e:
        return f"[部署失败] {e}"
