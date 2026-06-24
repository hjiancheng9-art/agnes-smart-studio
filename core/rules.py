"""Rules 系统 — 持久化编码规范，自动注入会话上下文"""

from pathlib import Path

__all__ = ["RULES_DIR", "Rule", "RulesManager", "get_rules"]
RULES_DIR = Path(__file__).parent.parent / "rules"


class Rule:
    """一条编码规则"""

    def __init__(
        self,
        name: str,
        content: str,
        description: str = "",
        enabled: bool = True,
        category: str = "general",
        default_active: bool = False,
    ) -> None:
        self.name = name
        self.content = content
        self.description = description
        self.enabled = enabled
        self.category = category
        # 是否在首次 discover 时自动加入 _active（opt-in，默认 False）
        # 用途：rendering 这类系统级契约规则默认就该生效，不必等用户手动 enable
        self.default_active = default_active

    @staticmethod
    def from_file(path: Path) -> "Rule":
        """从 .rules.md 文件加载规则

        支持 YAML frontmatter（可选）::

            ---
            default-active: true
            ---
            # 规则标题
            规则正文...

        无 frontmatter 时向后兼容（仅取第一行 # 当描述）。default-active 默认 False，
        故 3 个示例规则（encoding-i18n / python-style / secret-security）行为不变。
        """
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        description = ""
        content = text
        default_active = False

        # YAML frontmatter（可选）：---  ...  ---
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                front = parts[1]
                body = parts[2].strip()
                # 极简解析（避免引入 yaml 依赖）：只认 default-active: true
                for line in front.strip().splitlines():
                    if line.strip().lower().startswith("default-active:"):
                        default_active = line.split(":", 1)[1].strip().lower() in ("true", "yes", "1")
                content = body

        # 提取第一行作为描述
        first_line = content.strip().split("\n")[0]
        if first_line.startswith("# "):
            description = first_line[2:].strip()
            content = "\n".join(content.strip().split("\n")[1:]).strip()

        # 提取纯规则名：rendering.rules.md → rendering（剥 .rules.md 两层后缀）
        raw_stem = path.stem  # rendering.rules（只剥 .md）
        name = raw_stem.removesuffix(".rules") if raw_stem.endswith(".rules") else raw_stem

        return Rule(
            name=name,
            content=content,
            description=description,
            category=path.parent.name if path.parent != RULES_DIR else "general",
            default_active=default_active,
        )


class RulesManager:
    """规则管理器：加载、注入、创建"""

    def __init__(self, rules_dir: Path | None = None) -> None:
        self._dir = rules_dir or RULES_DIR
        self._rules: dict[str, Rule] = {}
        self._active: list[str] = []

    def discover(self) -> dict[str, Rule]:
        """扫描 rules/ 目录发现规则

        带 frontmatter ``default-active: true`` 的规则会在首次发现时自动加入 _active
        （系统级契约规则，如 rendering，默认就该生效）。已在 _active 的不重复加入；
        用户用 /rules disable 移除后，本方法不会重新加回（保持用户意图）。
        """
        self._rules.clear()
        if not self._dir.exists():
            self._dir.mkdir(parents=True, exist_ok=True)
            return self._rules

        for f in self._dir.rglob("*.rules.md"):
            try:
                rule = Rule.from_file(f)
                self._rules[rule.name] = rule
            except (AttributeError, TypeError):
                pass
        # 首次自动激活标记为 default_active 的规则
        for name, rule in self._rules.items():
            if getattr(rule, "default_active", False) and name not in self._active:
                self._active.append(name)
        return self._rules

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

    @property
    def active_rules(self) -> list[Rule]:
        return [self._rules[n] for n in self._active if n in self._rules]

    @property
    def available_names(self) -> list[str]:
        return list(self._rules.keys())

    def inject_prompt(self) -> str:
        """将已启用的规则注入为 LLM 指令"""
        rules = self.active_rules
        if not rules:
            return ""

        lines = ["\n[激活规则]"]
        for r in rules:
            lines.append(f"### {r.description or r.name}")
            lines.append(r.content[:500])
            lines.append("")
        return "\n".join(lines)

    def create_rule(self, name: str, content: str, description: str = "", category: str = "general") -> Path:
        """创建新规则文件"""
        self._dir.mkdir(parents=True, exist_ok=True)
        cat_dir = self._dir / category
        cat_dir.mkdir(exist_ok=True)
        path = cat_dir / f"{name}.rules.md"
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
                path.write_text(f"# {data['desc']}\n\n{data['content']}", encoding="utf-8")


# 全局单例
_manager: RulesManager | None = None


def get_rules() -> RulesManager:
    global _manager
    if _manager is None:
        _manager = RulesManager()
        _manager.create_examples()
        _manager.discover()
    return _manager
