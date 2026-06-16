"""Skill 系统 — 领域知识包，按需加载到 Agent 系统提示词

目录结构:
    skills/
        python.skill.json
        react.skill.json
        debug.skill.json
        ...

Skill 文件格式 (JSON):
{
    "name": "python-expert",
    "description": "Python 专家",
    "version": "1.0",
    "prompt": "你是 Python 专家。规则：...",
    "tools": [  // 可选，加载时自动注入的额外工具
        {"name": "run_python", "type": "shell", ...}
    ],
    "icon": "🐍"  // 可选
}

用法:
    /skill load python-expert   → 加载 Python 技能
    /skill list                 → 列出可用技能
    /skill unload               → 卸载当前技能
"""

import json
from pathlib import Path
from typing import Optional


SKILLS_DIR = Path(__file__).parent.parent / "skills"


class Skill:
    """单个技能"""

    def __init__(self, data: dict, file_path: Path):
        self.name = data.get("name", file_path.stem)
        self.description = data.get("description", "")
        self.version = data.get("version", "1.0")
        self.prompt = data.get("prompt", "")
        self.icon = data.get("icon", "")
        self.tools = data.get("tools", [])
        self.file = file_path

    def __repr__(self):
        return f"Skill({self.name})"


class SkillManager:
    """技能管理器：发现、加载、卸载"""

    def __init__(self, skills_dir: Optional[Path] = None):
        self._dir = skills_dir or SKILLS_DIR
        self._loaded: Optional[Skill] = None
        self._available: dict[str, Skill] = {}

    def discover(self) -> dict[str, Skill]:
        """扫描 skills/ 目录，发现所有可用技能"""
        self._available.clear()
        if not self._dir.exists():
            self._dir.mkdir(parents=True, exist_ok=True)
            return self._available

        for f in sorted(self._dir.glob("*.skill.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                skill = Skill(data, f)
                self._available[skill.name] = skill
            except (json.JSONDecodeError, KeyError):
                pass
        return self._available

    @property
    def loaded(self) -> Optional[Skill]:
        return self._loaded

    @property
    def available_names(self) -> list[str]:
        return list(self._available.keys())

    def load(self, name: str) -> Optional[Skill]:
        """加载指定技能，返回技能对象"""
        self.discover()
        skill = self._available.get(name)
        if skill:
            self._loaded = skill
        return skill

    def unload(self):
        self._loaded = None

    def get_system_prompt(self, base_prompt: str) -> str:
        """拼接 base_prompt + 已加载 skill 的 prompt"""
        if not self._loaded:
            return base_prompt
        skill_prompt = self._loaded.prompt.strip()
        if not skill_prompt:
            return base_prompt
        return f"{base_prompt}\n\n[Skill 激活: {self._loaded.name}]\n{skill_prompt}"

    def get_extra_tools(self) -> list[dict]:
        """获取当前技能注入的额外工具定义"""
        if not self._loaded:
            return []
        return self._loaded.tools or []

    # ── 创建示例技能 ──
    # ── 品质门禁 (参考 harness-engineering) ──

    def validate(self) -> dict:
        """验证所有技能文件的结构合法性

        Returns:
            {"passed": [...], "failed": [{"file": ..., "error": ...}]}
        """
        self.discover()
        result = {"passed": [], "failed": [], "warnings": []}

        for f in sorted(self._dir.glob("*.skill.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                result["failed"].append({"file": f.name, "error": f"Invalid JSON: {e}"})
                continue

            errors = []
            if not data.get("name"):
                errors.append("缺少 name")
            if not data.get("description"):
                errors.append("缺少 description")
            if not data.get("prompt") or len(data.get("prompt", "")) < 20:
                errors.append("prompt 过短 (需 ≥20 字符)")
            if len(data.get("prompt", "")) > 8000:
                result["warnings"].append(f"{f.name}: prompt 过长 ({len(data['prompt'])} 字符)，建议 ≤8KB")

            if errors:
                result["failed"].append({"file": f.name, "errors": errors})
            else:
                result["passed"].append(f.name)

        return result

    # ── 导入外部技能市场 ──

    def import_from_marketplace(self, market_path: str) -> dict:
        """从外部技能市场导入技能（适配 claude-agents 格式）

        扫描 plugins/*/skills/*/SKILL.md（YAML frontmatter + Markdown），
        转换为本项目的 .skill.json 格式。

        Returns: {"imported": [name, ...], "skipped": [file, ...], "errors": [...]}
        """
        import yaml
        mp = Path(market_path)
        if not mp.exists():
            return {"imported": [], "skipped": [], "errors": [f"路径不存在: {market_path}"]}

        # 查找技能文件
        skill_files = list(mp.rglob("SKILL.md"))  # claude-agents 格式
        skill_files += list(mp.rglob("*.skill.md"))  # 其他可能的格式

        result = {"imported": [], "skipped": [], "errors": []}
        self._dir.mkdir(parents=True, exist_ok=True)

        for sf in skill_files:
            try:
                text = sf.read_text(encoding="utf-8")
                # 解析 YAML frontmatter (--- ... ---)
                parts = text.split("---", 2)
                if len(parts) < 3:
                    result["skipped"].append(str(sf))
                    continue

                meta = yaml.safe_load(parts[1]) or {}
                body = parts[2].strip()

                name = meta.get("name", sf.parent.name)
                if not name:
                    name = sf.parent.name

                # 目标文件（避免覆盖已有）
                dest = self._dir / f"{name}.skill.json"
                if dest.exists():
                    result["skipped"].append(f"{name} (已存在)")
                    continue

                skill_data = {
                    "name": name,
                    "description": meta.get("description", f"从 {sf.parent.name} 导入"),
                    "version": meta.get("version", "1.0"),
                    "icon": meta.get("icon", "📦"),
                    "prompt": body[:7000],  # 截断到 7KB
                    "_source": str(sf),
                }
                dest.write_text(json.dumps(skill_data, indent=2, ensure_ascii=False), encoding="utf-8")
                result["imported"].append(name)

            except Exception as e:
                result["errors"].append(f"{sf.name}: {e}")

        return result

    def create_examples(self):
        """首次使用时创建示例技能文件"""
        self._dir.mkdir(parents=True, exist_ok=True)

        examples = {
            "python-expert": {
                "name": "python-expert",
                "description": "Python 全栈开发专家，擅长类型安全、异步编程、测试",
                "version": "1.0",
                "icon": "🐍",
                "prompt": (
                    "激活 Python 专家模式。你必须：\n"
                    "- 使用类型注解 (typing)\n"
                    "- 优先 asyncio 处理 I/O\n"
                    "- 代码自带 docstring\n"
                    "- 关键逻辑写单元测试示例\n"
                    "- 推荐使用 pathlib、dataclasses、functools 等标准库"
                ),
            },
            "debug-master": {
                "name": "debug-master",
                "description": "调试大师，分析错误堆栈、性能瓶颈、内存泄漏",
                "version": "1.0",
                "icon": "🔍",
                "prompt": (
                    "激活调试大师模式。策略：\n"
                    "1. 先看完整错误信息和堆栈\n"
                    "2. 定位根因，不要修表面症状\n"
                    "3. 给 3 个可能原因，按概率排序\n"
                    "4. 每个原因给具体修复代码\n"
                    "5. 建议如何预防类似问题"
                ),
            },
            "shell-master": {
                "name": "shell-master",
                "description": "Shell 脚本大师，bash/zsh/powershell 全能",
                "version": "1.0",
                "icon": "💻",
                "prompt": (
                    "激活 Shell 大师模式。规则：\n"
                    "- 脚本加 shebang 和注释\n"
                    "- 用 set -euo pipefail (bash)\n"
                    "- 跨平台时标注 Windows/Linux 差异\n"
                    "- 危险命令加确认提示\n"
                    "- 管道操作解释数据流"
                ),
            },
            "api-designer": {
                "name": "api-designer",
                "description": "API 设计专家，RESTful/GraphQL/gRPC",
                "version": "1.0",
                "icon": "🔌",
                "prompt": (
                    "激活 API 设计专家模式。规范：\n"
                    "- RESTful: 资源命名、状态码、分页、版本控制\n"
                    "- 请求/响应示例 (JSON)\n"
                    "- 认证方案 (JWT/OAuth2/API Key)\n"
                    "- 错误处理格式\n"
                    "- OpenAPI/Swagger schema"
                ),
            },
        }

        for name, data in examples.items():
            path = self._dir / f"{name}.skill.json"
            if not path.exists():
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# 全局单例
_manager: Optional[SkillManager] = None


def get_manager() -> SkillManager:
    global _manager
    if _manager is None:
        _manager = SkillManager()
        _manager.create_examples()
        _manager.discover()
    return _manager
