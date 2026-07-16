"""Rules 系统 — 持久化编码规范，按文件模式/场景/手动引用激活。

TRAE-inspired 四种激活模式：
    always:  始终生效（alwaysApply: true）
    globs:   仅在涉及匹配文件时生效
    smart:   根据 description AI 自行判断相关性
    manual:  仅当用户 #Rule 引用时生效
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

__all__ = ["RULES_DIR", "Rule", "RulesManager", "get_rules"]
RULES_DIR = Path(__file__).parent.parent / "rules"


# Valid activation modes
MODE_ALWAYS = "always"
MODE_GLOBS = "globs"
MODE_SMART = "smart"
MODE_MANUAL = "manual"
_VALID_MODES = (MODE_ALWAYS, MODE_GLOBS, MODE_SMART, MODE_MANUAL)


class Rule:
    """一条编码规则，支持按文件模式/场景激活。

    Attributes:
        name: 规则唯一名称
        content: Markdown 格式的规则正文
        description: 简短描述，用于 Smart 模式的匹配
        enabled: 是否启用
        category: 分类目录名
        mode: 激活模式 (always/globs/smart/manual)
        globs: 文件匹配模式列表（mode=globs 时生效，如 ["*.py", "src/**/*.ts"]）
        default_active: 是否首次发现时自动激活
        scene: 可选场景标记（如 "git_message"）
    """

    def __init__(
        self,
        name: str,
        content: str,
        description: str = "",
        enabled: bool = True,
        category: str = "general",
        default_active: bool = False,
        mode: str = MODE_ALWAYS,
        globs: list[str] | None = None,
        scene: str = "",
    ) -> None:
        self.name = name
        self.content = content
        self.description = description
        self.enabled = enabled
        self.category = category
        self.default_active = default_active
        self.mode = mode if mode in _VALID_MODES else MODE_ALWAYS
        self.globs = globs or []
        self.scene = scene

    @staticmethod
    def from_file(path: Path) -> Rule:
        """从 .rules.md 文件加载规则。

        支持 YAML frontmatter（可选）::

            ---
            mode: globs
            globs: ["*.py", "src/**/*.ts"]
            scene: git_message
            ---
            # 规则标题
            规则正文...

        无 frontmatter 时默认 mode=always（向后兼容）。
        """
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        description = ""
        content = text
        default_active = False
        mode = MODE_ALWAYS
        globs: list[str] = []
        scene = ""

        # YAML frontmatter
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                front = parts[1]
                body = parts[2].strip()
                for line in front.strip().splitlines():
                    stripped = line.strip()
                    if stripped.lower().startswith("default-active:"):
                        default_active = stripped.split(":", 1)[1].strip().lower() in ("true", "yes", "1")
                    elif stripped.lower().startswith("mode:"):
                        m = stripped.split(":", 1)[1].strip().strip("\"'")
                        mode = m if m in _VALID_MODES else MODE_ALWAYS
                    elif stripped.lower().startswith("globs:"):
                        val = stripped.split(":", 1)[1].strip()
                        if val.startswith("[") and val.endswith("]"):
                            import json

                            try:
                                globs = json.loads(val)
                            except json.JSONDecodeError:
                                globs = [v.strip().strip("\"'") for v in val[1:-1].split(",") if v.strip()]
                    elif stripped.lower().startswith("scene:"):
                        scene = stripped.split(":", 1)[1].strip()
                content = body

        # 提取第一行作为描述
        first_line = content.strip().split("\n")[0]
        if first_line.startswith("# "):
            description = first_line[2:].strip()
            content = "\n".join(content.strip().split("\n")[1:]).strip()

        # 提取纯规则名
        raw_stem = path.stem
        name = raw_stem.removesuffix(".rules") if raw_stem.endswith(".rules") else raw_stem

        return Rule(
            name=name,
            content=content,
            description=description,
            category=path.parent.name if path.parent != RULES_DIR else "general",
            default_active=default_active,
            mode=mode,
            globs=globs,
            scene=scene,
        )

    def matches_files(self, files: list[str]) -> bool:
        """Check if this rule matches any of the given file paths via globs.

        Only relevant when mode=globs.
        """
        if not self.globs or self.mode != MODE_GLOBS:
            return False
        for file_path in files:
            for pattern in self.globs:
                if fnmatch.fnmatch(file_path, pattern):
                    return True
        return False


class RulesManager:
    """规则管理器：加载、懒激活、注入"""

    def __init__(self, rules_dir: Path | None = None) -> None:
        self._dir = rules_dir or RULES_DIR
        self._rules: dict[str, Rule] = {}
        self._active: list[str] = []
        self._mentioned: set[str] = set()  # Manual-mode rules explicitly #Rule'd
        self._context_files: list[str] = []  # Current conversation file context

    def discover(self) -> dict[str, Rule]:
        """扫描 rules/ 目录发现规则。支持子目录（最多 3 层）。

        default_active 的规则首次发现时自动激活。
        """
        self._rules.clear()
        if not self._dir.exists():
            self._dir.mkdir(parents=True, exist_ok=True)
            return self._rules

        # 支持子目录嵌套（最多 3 层，对标 TRAE）
        for depth in range(4):
            pattern = "*.rules.md" if depth == 0 else "/".join(["*"] * depth) + "/*.rules.md"
            for f in self._dir.glob(pattern):
                try:
                    rule = Rule.from_file(f)
                    self._rules[rule.name] = rule
                except (AttributeError, TypeError):
                    pass

        # 首次自动激活 default_active 规则
        for name, rule in self._rules.items():
            if rule.default_active and name not in self._active:
                self._active.append(name)
        return self._rules

    def set_context_files(self, files: list[str]) -> None:
        """Set the current conversation's file context for globs matching."""
        self._context_files = list(files)

    def load(self, name: str) -> Rule | None:
        """加载指定规则"""
        self.discover()
        return self._rules.get(name)

    def enable(self, name: str) -> bool:
        """启用规则"""
        rule = self._rules.get(name) or self.load(name)
        if rule:
            rule.enabled = True
            if name not in self._active:
                self._active.append(name)
            return True
        return False

    def disable(self, name: str):
        """禁用规则"""
        if name in self._active:
            self._active.remove(name)

    def mention(self, name: str) -> None:
        """Temporarily activate a manual-mode rule via #Rule reference."""
        if name in self._rules:
            self._mentioned.add(name)
            if name not in self._active:
                self._active.append(name)

    def get_active_for_context(self, task_text: str = "", files: list[str] | None = None) -> list[Rule]:
        """Get rules active for the current context, respecting activation mode.

        - always:    always included
        - globs:     included if any context file matches
        - smart:     included if description keywords match task_text
        - manual:    NOT auto-included (only via #Rule mention)
        """
        context_files = files or self._context_files
        active_rules: list[Rule] = []

        for name in self._active:
            rule = self._rules.get(name)
            if not rule or not rule.enabled:
                continue

            if rule.mode == MODE_ALWAYS:
                active_rules.append(rule)
            elif rule.mode == MODE_GLOBS and context_files:
                if rule.matches_files(context_files):
                    active_rules.append(rule)
            elif rule.mode == MODE_SMART and task_text:
                desc = rule.description.lower()
                task_lower = task_text.lower()
                keywords = [w for w in desc.split() if len(w) >= 2]
                if any(kw in task_lower for kw in keywords):
                    active_rules.append(rule)
            elif rule.mode == MODE_MANUAL:
                # Only included if explicitly mentioned via #Rule this turn
                if rule.name in self._mentioned:
                    active_rules.append(rule)

        return active_rules

    @property
    def active_rules(self) -> list[Rule]:
        """All enabled active rules (legacy API, ignores mode)."""
        return [self._rules[n] for n in self._active if n in self._rules]

    @property
    def available_names(self) -> list[str]:
        return list(self._rules.keys())

    def inject_prompt(self, task_text: str = "", files: list[str] | None = None) -> str:
        """将活跃规则注入为 LLM 指令（尊重激活模式）。

        Args:
            task_text: 当前任务描述，用于 Smart 模式匹配
            files: 当前涉及的文件列表，用于 Globs 模式匹配
        Returns:
            Markdown 格式的规则注入文本，无活跃规则时返回空字符串。
        """
        rules = self.get_active_for_context(task_text, files)
        if not rules:
            return ""

        lines = ["\n[激活规则]"]
        for r in rules:
            mode_tag = f" [{r.mode}]" if r.mode != MODE_ALWAYS else ""
            lines.append(f"### {r.description or r.name}{mode_tag}")
            lines.append(r.content[:500])
            lines.append("")
        return "\n".join(lines)

    def create_rule(
        self,
        name: str,
        content: str,
        description: str = "",
        category: str = "general",
        mode: str = MODE_ALWAYS,
        globs: list[str] | None = None,
    ) -> Path:
        """创建新规则文件（支持激活模式）。"""
        self._dir.mkdir(parents=True, exist_ok=True)
        cat_dir = self._dir / category
        cat_dir.mkdir(exist_ok=True)
        path = cat_dir / f"{name}.rules.md"

        # Build frontmatter
        frontmatter_lines = []
        if mode != MODE_ALWAYS:
            frontmatter_lines.append(f"mode: {mode}")
        if globs:
            import json

            frontmatter_lines.append(f"globs: {json.dumps(globs)}")
        frontmatter = "\n".join(frontmatter_lines)

        if frontmatter:
            text = f"---\n{frontmatter}\n---\n\n# {description or name}\n\n{content}"
        else:
            text = f"# {description or name}\n\n{content}"
        path.write_text(text, encoding="utf-8")
        return path

    def create_examples(self):
        """创建示例规则"""
        examples = {
            "encoding-i18n": {
                "name": "encoding-i18n",
                "desc": "编码与国际化规范",
                "content": (
                    "1. 源码只写 ASCII/英文，中文放语言包\n"
                    "2. 所有文件 UTF-8\n"
                    "3. 代码中不直接写中文\n"
                    "4. 提交前扫描乱码字符"
                ),
            },
            "python-style": {
                "name": "python-style",
                "desc": "Python 代码风格",
                "content": (
                    "1. 使用类型注解 (typing)\n"
                    "2. 函数写 docstring\n"
                    "3. 用 pathlib 处理路径\n"
                    "4. 异常精确捕获，不用裸 except\n"
                    "5. 遵循 PEP 8"
                ),
                "mode": MODE_GLOBS,
                "globs": ["*.py"],
            },
            "secret-security": {
                "name": "secret-security",
                "desc": "密钥安全规范",
                "content": (
                    "1. 绝对不提交 API Key/密码到代码\n"
                    "2. 用环境变量或 .env 管理密钥\n"
                    "3. .env 加入 .gitignore\n"
                    "4. 代码中不硬编码 token/password\n"
                    "5. 发现泄露立即轮换"
                ),
            },
        }

        for name, data in examples.items():
            path = self._dir / f"{name}.rules.md"
            if not path.exists():
                mode = data.get("mode", MODE_ALWAYS)
                globs = data.get("globs")
                self.create_rule(
                    name=name,
                    content=data["content"],
                    description=data["desc"],
                    mode=mode,
                    globs=globs,
                )


# 全局单例
_manager: RulesManager | None = None


def get_rules() -> RulesManager:
    global _manager
    if _manager is None:
        _manager = RulesManager()
        _manager.create_examples()
        _manager.discover()
    return _manager


def reset_rules() -> None:
    """Reset the rules singleton (test isolation / hot reload)."""
    global _manager
    _manager = None
