"""Skill Marketplace — 接入 CodeBuddy 及任意技能生态市场

架构:
  MarketplaceClient  ─→  LocalRegistry (内置，skills/ 目录)
                      ├→  CodeBuddyAdapter (CodeBuddy 插件市场)
                      └→  CustomAdapter (任意第三方市场)

用法:
  mp = MarketplaceClient()
  mp.search("video")          # 跨所有市场搜索
  mp.install("showrunner")    # 安装技能包
  mp.list_installed()         # 已安装列表
  mp.check_updates()          # 检查更新
"""

import contextlib
import json
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "CodeBuddyAdapter",
    "LocalRegistry",
    "MarketplaceAdapter",
    "MarketplaceClient",
    "ROOT",
    "RemoteMarketplaceAdapter",
    "SKILLS_DIR",
    "SkillPackage",
    "get_marketplace",
]

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════


@dataclass
class SkillPackage:
    """一个技能包"""

    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    icon: str = ""  # emoji or URL
    category: str = ""  # video/coding/creative/quality/tool
    tags: list[str] = field(default_factory=list)
    source: str = "local"  # local/codebuddy/custom
    installed: bool = False
    installable: bool = True
    size_kb: int = 0
    downloads: int = 0
    rating: float = 0.0  # 0-5
    homepage: str = ""
    requires: list[str] = field(default_factory=list)  # 依赖的其他技能

    def to_dict(self) -> dict:
        return dict(self.__dict__.items())

    @classmethod
    def from_dict(cls, d: dict) -> "SkillPackage":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════
# 市场适配器基类
# ═══════════════════════════════════════════════════════════════


class MarketplaceAdapter(ABC):
    """市场适配器 — 每个生态市场实现此接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """市场名称，如 'codebuddy', 'local'"""
        ...

    @abstractmethod
    def search(self, query: str, category: str = "") -> list[SkillPackage]:
        """搜索技能包"""
        ...

    @abstractmethod
    def fetch(self, name: str) -> SkillPackage | None:
        """获取技能包详情"""
        ...

    @abstractmethod
    def download(self, name: str, version: str = "") -> Path:
        """下载技能包文件，返回临时路径"""
        ...

    @abstractmethod
    def list_available(self) -> list[SkillPackage]:
        """列出市场上所有可用技能包"""
        ...

    def check_updates(self, installed: list[str]) -> dict[str, str]:
        """检查已安装技能包是否有更新"""
        return {}


# ═══════════════════════════════════════════════════════════════
# Local Registry — 基于 skills/ 目录
# ═══════════════════════════════════════════════════════════════


class LocalRegistry(MarketplaceAdapter):
    """本地技能注册表 — 从 skills/ 和 skills_md/ 双目录加载"""

    def __init__(self) -> None:
        self._md_dir = ROOT / "skills_md"

    @property
    def name(self) -> str:
        return "local"

    def _load_all(self) -> list[dict]:
        """加载所有本地技能定义（skills/*.skill.json + skills_md/*.skill.md）"""
        skills = []
        # 1) skills/ 目录 (.skill.json)
        if SKILLS_DIR.exists():
            for f in sorted(SKILLS_DIR.glob("*.skill.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    data.setdefault("installed", True)
                    data.setdefault("source", "local")
                    data["_file"] = str(f)
                    skills.append(data)
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
        # 2) skills_md/ 目录 (.skill.md)
        if self._md_dir.exists():
            for f in sorted(self._md_dir.glob("*.skill.md")):
                try:
                    raw = self._parse_skill_md(f)
                    if raw and raw.get("name"):
                        raw.setdefault("installed", False)
                        raw.setdefault("installable", True)
                        raw.setdefault("source", "local")
                        raw["_file"] = str(f)
                        skills.append(raw)
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
        return skills

    def _parse_skill_md(self, path: Path) -> dict | None:
        """解析 .skill.md 文件：以 # Title 为 name，其余为 description"""
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.strip().split("\n")
        name = ""
        desc_lines = []
        in_desc = False
        for line in lines:
            s = line.strip()
            if s.startswith("# ") and not name:
                name = s[2:].strip()
            elif s.startswith("## ") and "description" in s.lower():
                in_desc = True
                desc = s.split("## ")[-1].strip()
                if desc.lower() != "description":
                    desc_lines.append(desc)
            elif in_desc and s and not s.startswith("#"):
                desc_lines.append(s)
            elif in_desc and s.startswith("#"):
                break
        if not name:
            name = path.stem.replace("-", " ").title()
        description = " ".join(desc_lines)[:120] if desc_lines else name
        return {
            "name": name.lower().replace(" ", "-"),
            "display_name": name,
            "description": description,
            "version": "1.0.0",
        }

    def _to_package(self, raw: dict) -> SkillPackage:
        """将原始数据转为 SkillPackage"""
        cat = raw.get("category", "")
        if not cat:
            # 自动推断分类
            name = raw.get("name", "")
            desc = raw.get("description", "")
            text = (name + desc).lower()
            if any(w in text for w in ["video", "cinematic", "motion", "storyboard", "showrunner"]):
                cat = "video"
            elif any(w in text for w in ["creative", "writer", "novel", "comic", "world", "actor"]):
                cat = "creative"
            elif any(w in text for w in ["qc", "quality", "code-review", "debug", "master", "delivery"]):
                cat = "quality"
            elif any(w in text for w in ["python", "shell", "api", "comfyui", "model", "publishing"]):
                cat = "tool"
            else:
                cat = "other"

        return SkillPackage(
            name=raw.get("name", ""),
            description=raw.get("description", "")[:120],
            version=raw.get("version", "1.0.0"),
            author=raw.get("author", "CRUX Studio"),
            icon=raw.get("icon", ""),
            category=cat,
            tags=raw.get("tags", []),
            source="local",
            installed=True,
            installable=True,
        )

    def search(self, query: str, category: str = "") -> list[SkillPackage]:
        q = query.lower()
        results = []
        for raw in self._load_all():
            pkg = self._to_package(raw)
            if (q in pkg.name.lower() or q in pkg.description.lower() or q in pkg.category.lower()) and (
                not category or pkg.category == category
            ):
                results.append(pkg)
        return results

    def fetch(self, name: str) -> SkillPackage | None:
        for raw in self._load_all():
            if raw.get("name") == name:
                return self._to_package(raw)
        return None

    def download(self, name: str, version: str = "") -> Path:
        """下载技能包文件。skills/ 目录的 .skill.json 直接返回；skills_md/ 的 .skill.md 自动转换为 .skill.json"""
        # 已存在的 .skill.json
        f = SKILLS_DIR / f"{name}.skill.json"
        if f.exists():
            return f
        # skills_md/ 中的 .skill.md → 转换为 skill.json
        md = self._md_dir / f"{name}.skill.md"
        if md.exists():
            raw = self._parse_skill_md(md)
            if raw:
                # 读取完整正文作 prompt
                content = md.read_text(encoding="utf-8", errors="replace")
                skill_data = {
                    "name": raw.get("name", name),
                    "description": raw.get("description", ""),
                    "version": raw.get("version", "1.0.0"),
                    "author": "Local Market",
                    "prompt": content[:5000],
                    "source": "local",
                    "tags": [],
                }
                SKILLS_DIR.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(skill_data, indent=2, ensure_ascii=False), encoding="utf-8")
                return f
        raise FileNotFoundError(f"Skill {name} not found locally")

    def list_available(self) -> list[SkillPackage]:
        return [self._to_package(raw) for raw in self._load_all()]


# ═══════════════════════════════════════════════════════════════
# CodeBuddy 本地市场适配器 — 直接读 .codebuddy/skills-marketplace
# ═══════════════════════════════════════════════════════════════


class CodeBuddyAdapter(MarketplaceAdapter):
    """CodeBuddy 技能市场 — 从本地 .codebuddy/skills-marketplace/skills/ 读取。

    每个技能是一个目录，内含 SKILL.md（YAML frontmatter + Markdown 正文）。
    格式:
      ---
      name: skill-name
      description_zh: 中文描述
      category: Category
      version: 1.0.0
      author: Author
      ---
      # Skill Title
      ...
    """

    CATEGORY_MAP = {
        "Education": "creative",
        "Office": "tool",
        "Cloud": "tool",
        "Dev": "tool",
        "Content": "creative",
        "Life": "other",
        "AI": "tool",
        "Tencent": "tool",
    }

    def __init__(self, name: str = "codebuddy", market_dir: str = "") -> None:
        import os

        home = os.path.expanduser("~")
        if market_dir:
            self.market_dir = Path(market_dir)
        else:
            self.market_dir = Path(home) / ".codebuddy" / "skills-marketplace" / "skills"
        self._name = name
        self._enabled = self.market_dir.exists()
        self._cache: dict[str, dict] = {}
        self._cache_time: float = 0
        self._cache_ttl: float = 30.0

    @property
    def name(self) -> str:
        return self._name

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _load_all(self) -> dict[str, dict]:
        """加载所有技能元数据（递归搜索 SKILL.md，带缓存）"""
        import time

        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        skills = {}
        if not self.market_dir.exists():
            return skills

        # 递归搜索所有 SKILL.md 和 agent .md 文件（最多 3 层）
        def _scan_dir(d: Path, depth: int = 0):
            if depth > 3 or not d.is_dir():
                return
            try:
                for item in sorted(d.iterdir()):
                    if item.name.startswith("."):
                        continue
                    if item.is_dir():
                        # 检查 SKILL.md 或 agent 目录下的 .md 文件
                        found = False
                        for md_name in ("SKILL.md",):
                            md = item / md_name
                            if md.exists():
                                try:
                                    raw = self._parse_skill_md(md)
                                    if raw:
                                        raw["_dir"] = str(item)
                                        skills[raw["name"]] = raw
                                        found = True
                                except (AttributeError, TypeError):
                                    pass
                        if not found:
                            # Agent 目录: agents/*.md, commands/*.md
                            for sub in ("agents", "commands"):
                                sub_dir = item / sub
                                if sub_dir.exists():
                                    for agent_file in sub_dir.glob("*.md"):
                                        try:
                                            raw = self._parse_skill_md(agent_file)
                                            if raw:
                                                raw["_dir"] = str(item)
                                                raw.setdefault("category", "agent")
                                                skills[raw["name"]] = raw
                                        except (AttributeError, TypeError):
                                            pass
                            if not (item / "agents").exists() and not (item / "commands").exists():
                                _scan_dir(item, depth + 1)
            except PermissionError:
                pass

        _scan_dir(self.market_dir)

        self._cache = skills
        self._cache_time = now
        return skills

    def _parse_skill_md(self, path: Path) -> dict | None:
        """解析 SKILL.md 或 agent .md 的 YAML frontmatter。

        支持两种格式:
          - SKILL.md: name, description, version, category, author
          - agent .md: name, description, tools, model
        """
        content = path.read_text(encoding="utf-8", errors="replace")
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        fm_text = parts[1].strip()
        data = {}
        for line in fm_text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                data[key] = val

        if "name" not in data:
            return None

        # Agent 格式转换: tools → category tag
        if "tools" in data and "category" not in data:
            data["category"] = "agent"
        return data

    def _to_package(self, raw: dict) -> SkillPackage:
        """转换原始数据为 SkillPackage"""
        name = raw.get("name", "")
        desc = raw.get("description_zh") or raw.get("description", "")
        category_raw = raw.get("category", "Other")
        category = self.CATEGORY_MAP.get(category_raw, "other")

        return SkillPackage(
            name=name,
            description=desc[:120],
            version=raw.get("version", "1.0.0"),
            author=raw.get("author", ""),
            icon=raw.get("icon", ""),
            category=category,
            source="codebuddy",
            installed=(ROOT / "skills" / f"{name}.skill.json").exists(),
            installable=True,
        )

    def search(self, query: str, category: str = "") -> list[SkillPackage]:
        q = query.lower()
        results = []
        for raw in self._load_all().values():
            pkg = self._to_package(raw)
            match = q in pkg.name.lower() or q in pkg.description.lower() or q in pkg.category
            if match and (not category or pkg.category == category):
                results.append(pkg)
        return sorted(results, key=lambda p: p.name)

    def fetch(self, name: str) -> SkillPackage | None:
        all_skills = self._load_all()
        raw = all_skills.get(name)
        return self._to_package(raw) if raw else None

    def download(self, name: str, version: str = "") -> Path:
        """从本地市场复制技能到 skills/ 目录，转换为 CRUX 格式。

        把 SKILL.md 转为 .skill.json：
          name, description, version, author, prompt → 合并到 skill.json
        """
        all_skills = self._load_all()
        raw = all_skills.get(name)
        if not raw:
            raise FileNotFoundError(f"Skill '{name}' not in CodeBuddy marketplace")

        skill_dir = Path(raw["_dir"])
        md_path = skill_dir / "SKILL.md"
        content = md_path.read_text(encoding="utf-8", errors="replace")

        # 提取正文（frontmatter 之后的部分）
        parts = content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else content

        # 构建 CRUX 格式的 skill.json
        skill_data = {
            "name": raw.get("name", name),
            "description": raw.get("description_zh") or raw.get("description", ""),
            "version": raw.get("version", "1.0.0"),
            "author": raw.get("author", "CodeBuddy"),
            "icon": raw.get("icon", ""),
            "category": raw.get("category", ""),
            "prompt": body[:5000],  # 取前 5000 字符作为提示词
            "source": "codebuddy",
            "tags": [],
        }

        # 写入 CRUX skills/ 目录
        dest = SKILLS_DIR / f"{name}.skill.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(skill_data, indent=2, ensure_ascii=False), encoding="utf-8")
        return dest

    def list_available(self) -> list[SkillPackage]:
        return [self._to_package(raw) for raw in self._load_all().values()]

    def check_updates(self, installed: list[str]) -> dict[str, str]:
        """对比本地市场版本和已安装版本"""
        updates = {}
        all_skills = self._load_all()
        for name in installed:
            market = all_skills.get(name)
            if not market:
                continue
            market_ver = market.get("version", "")
            # 检查已安装版本
            local_file = SKILLS_DIR / f"{name}.skill.json"
            if local_file.exists():
                try:
                    local = json.loads(local_file.read_text(encoding="utf-8"))
                    local_ver = local.get("version", "")
                    if market_ver and market_ver != local_ver:
                        updates[name] = market_ver
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
        return updates


# ═══════════════════════════════════════════════════════════════
# 远程市场适配器 — 从 GitHub/URL 注册表下载技能
# ═══════════════════════════════════════════════════════════════


class RemoteMarketplaceAdapter(MarketplaceAdapter):
    """远程市场适配器 — 从可配置 URL 拉取技能注册表并下载。

    支持的注册表格式：
      - JSON 注册表: {"plugins": [{"name":..., "description":..., ...}, ...]}
      - 原始目录索引: 尝试 {url}/skills/index.json 或 {url}/plugins.json
    """

    # 已知的 CodeBuddy 市场源
    _KNOWN_REGISTRIES = [
        "https://api.codebuddy.tencent.com/v1/skills",
        "https://copilot.tencent.com/api/plugins",
        "https://raw.githubusercontent.com/codebuddy-ai/marketplace/main/registry.json",
    ]

    def __init__(self, name: str = "remote", registry_url: str = "", api_key: str = "") -> None:
        import os

        self._name = name
        self._registry_url = registry_url
        # 自动从环境变量获取 CodeBuddy/DeepSeek API key
        self._api_key = api_key or os.getenv("CODEBUDDY_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
        self._cache: list[dict] = []
        self._cache_time: float = 0
        self._cache_ttl: float = 120.0
        self._available: bool | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def enabled(self) -> bool:
        if self._available is None:
            self._probe()
        return self._available or False

    def _probe(self) -> bool:
        """探活：至少一个注册表 URL 可达"""
        import httpx

        urls = [self._registry_url] if self._registry_url else self._KNOWN_REGISTRIES
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        for url in urls:
            try:
                r = httpx.head(
                    url, timeout=httpx.Timeout(8, connect=5), trust_env=False, follow_redirects=True, headers=headers
                )
                if r.status_code < 500:
                    self._available = True
                    self._registry_url = url
                    return True
            except (httpx.HTTPError, OSError):
                continue
        self._available = False
        return False

    def _fetch_registry(self) -> list[dict]:
        """拉取远程注册表，带缓存"""
        import time

        import httpx

        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        urls = [self._registry_url] if self._registry_url else self._KNOWN_REGISTRIES
        for url in urls:
            try:
                r = httpx.get(
                    url, timeout=httpx.Timeout(15, connect=8), trust_env=False, follow_redirects=True, headers=headers
                )
                if r.status_code == 200:
                    data = r.json()
                    plugins = data.get("plugins") or data.get("skills") or data.get("data") or data
                    if isinstance(plugins, list):
                        self._cache = plugins
                        self._cache_time = now
                        self._registry_url = url
                        self._available = True
                        return plugins
                    if isinstance(plugins, dict):
                        # 有些 API 返回 {"data": {"items": [...]}}
                        items = plugins.get("items") or plugins.get("list") or []
                        if isinstance(items, list) and items:
                            self._cache = items
                            self._cache_time = now
                            self._registry_url = url
                            self._available = True
                            return items
            except (httpx.HTTPError, OSError):
                continue
        return []

    def search(self, query: str, category: str = "") -> list[SkillPackage]:
        q = query.lower()
        results = []
        for raw in self._fetch_registry():
            name = raw.get("name", "")
            desc = raw.get("description", "") or raw.get("description_zh", "")
            if q in name.lower() or q in desc.lower():
                pkg = SkillPackage(
                    name=name,
                    description=desc[:120],
                    version=raw.get("version", "1.0.0"),
                    author=raw.get("author", ""),
                    source=self.name,
                    installed=(SKILLS_DIR / f"{name}.skill.json").exists(),
                    installable=True,
                )
                if not category or pkg.category == category:
                    results.append(pkg)
        return results

    def fetch(self, name: str) -> SkillPackage | None:
        for raw in self._fetch_registry():
            if raw.get("name") == name:
                return SkillPackage(
                    name=name,
                    description=(raw.get("description") or raw.get("description_zh", ""))[:120],
                    version=raw.get("version", "1.0.0"),
                    author=raw.get("author", ""),
                    source=self.name,
                )
        return None

    def download(self, name: str, version: str = "") -> Path:
        """从远程下载技能包 -> 写入 skills/{name}.skill.json"""
        import httpx

        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        urls = (
            [
                f"{self._registry_url.rsplit('/', 1)[0]}/skills/{name}.skill.json",
                f"{self._registry_url.rsplit('/', 1)[0]}/skills/{name}/SKILL.md",
            ]
            if self._registry_url
            else []
        )
        urls += [
            f"https://api.codebuddy.tencent.com/v1/skills/{name}",
            f"https://copilot.tencent.com/api/plugins/{name}",
            f"https://raw.githubusercontent.com/codebuddy-ai/marketplace/main/skills/{name}.skill.json",
            f"https://raw.githubusercontent.com/codebuddy-ai/marketplace/main/skills/{name}/SKILL.md",
        ]

        for url in urls:
            try:
                r = httpx.get(
                    url, timeout=httpx.Timeout(20, connect=8), trust_env=False, follow_redirects=True, headers=headers
                )
                if r.status_code != 200:
                    continue
                content = r.text
                data = json.loads(content) if url.endswith(".json") else self._md_to_skill(name, content)
                if data.get("name"):
                    dest = SKILLS_DIR / f"{name}.skill.json"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                    return dest
            except (httpx.HTTPError, OSError):
                continue
        raise FileNotFoundError(f"Skill '{name}' not found in remote marketplace")

    def _md_to_skill(self, name: str, content: str) -> dict:
        """SKILL.md 正文 -> skill.json 格式"""
        name_from_title = name
        desc = ""
        for line in content.split("\n"):
            s = line.strip()
            if s.startswith("# ") and not name_from_title:
                name_from_title = s[2:].strip()
            elif s.startswith("## Description") or s.lower().startswith("## description"):
                desc = s.split("## ", 1)[-1].strip()
        return {
            "name": name,
            "description": desc or name_from_title,
            "version": "1.0.0",
            "author": "Remote Market",
            "prompt": content[:5000],
            "source": self.name,
            "tags": [],
        }

    def list_available(self) -> list[SkillPackage]:
        results = []
        for raw in self._fetch_registry():
            results.append(
                SkillPackage(
                    name=raw.get("name", ""),
                    description=(raw.get("description") or raw.get("description_zh", ""))[:120],
                    version=raw.get("version", "1.0.0"),
                    author=raw.get("author", ""),
                    source=self.name,
                    installed=(SKILLS_DIR / f"{raw.get('name', '')}.skill.json").exists(),
                    installable=True,
                )
            )
        return results


# ═══════════════════════════════════════════════════════════════
# 市场客户端 — 统一入口
# ═══════════════════════════════════════════════════════════════


class MarketplaceClient:
    """多市场技能管理客户端"""

    def __init__(self) -> None:
        import os

        home = os.path.expanduser("~")

        self.local = LocalRegistry()

        # CodeBuddy 技能市场（本地 ~/.codebuddy）
        self.codebuddy = CodeBuddyAdapter(name="codebuddy")

        # CodeBuddy 官方插件市场（从根目录递归扫描）
        official_dir = str(Path(home) / ".codebuddy" / "plugins" / "marketplaces" / "codebuddy-plugins-official")
        self.official = CodeBuddyAdapter(name="official", market_dir=official_dir)

        # 远程市场（GitHub raw / 可配置 URL）
        self.remote = RemoteMarketplaceAdapter(name="remote")

        self._adapters: list[MarketplaceAdapter] = [
            self.local,
            self.codebuddy,
            self.official,
            self.remote,
        ]

    @property
    def adapters(self) -> list[MarketplaceAdapter]:
        return [
            a for a in self._adapters if not isinstance(a, (CodeBuddyAdapter, RemoteMarketplaceAdapter)) or a.enabled
        ]

    def search(self, query: str, category: str = "") -> list[SkillPackage]:
        """跨所有市场搜索技能包"""
        results = []
        for adapter in self.adapters:
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                results.extend(adapter.search(query, category))
        # 去重：同名取版本最高的
        seen = {}
        for pkg in results:
            if pkg.name not in seen or pkg.version > seen[pkg.name].version:
                seen[pkg.name] = pkg
        return sorted(seen.values(), key=lambda p: -p.rating)

    def install(self, name: str, source: str = "") -> bool:
        """安装技能包到本地 skills/ 目录。

        流程:
          1. 在指定市场查找
          2. 下载包文件
          3. 验证并保存到 skills/{name}.skill.json
          4. 注册到 SkillManager
        """
        # 查找
        pkg = None
        for adapter in self.adapters:
            if source and adapter.name != source:
                continue
            pkg = adapter.fetch(name)
            if pkg:
                break

        if not pkg:
            return False

        # 下载并保存
        adapter = next((a for a in self.adapters if a.name == pkg.source), self.local)
        try:
            dest = adapter.download(pkg.name, pkg.version)
            return dest.exists()
        except (OSError, ValueError, RuntimeError):
            return pkg.source == "local"

    def uninstall(self, name: str) -> bool:
        """卸载本地技能包"""
        f = SKILLS_DIR / f"{name}.skill.json"
        if f.exists():
            f.unlink()
            return True
        return False

    def list_installed(self) -> list[SkillPackage]:
        """列出已安装的技能包"""
        return self.local.list_available()

    def list_all(self) -> list[SkillPackage]:
        """列出所有可用技能包（本地 + 市场）"""
        results = []
        seen = set()
        for adapter in self.adapters:
            try:
                for pkg in adapter.list_available():
                    if pkg.name not in seen:
                        seen.add(pkg.name)
                        results.append(pkg)
            except (OSError, ValueError, RuntimeError):
                pass
        return results

    def check_updates(self) -> dict[str, str]:
        """检查所有已安装技能包是否有更新"""
        installed_names = [p.name for p in self.list_installed()]
        all_updates = {}
        for adapter in self.adapters:
            try:
                updates = adapter.check_updates(installed_names)
                all_updates.update(updates)
            except (OSError, ValueError, RuntimeError):
                pass
        return all_updates

    def categories(self) -> list[str]:
        """返回所有技能分类"""
        cats = set()
        for pkg in self.local.list_available():
            cats.add(pkg.category)
        return sorted(cats)

    def summary(self) -> str:
        """市场概况（注入系统提示词）"""
        installed = len(self.list_installed())
        cats = self.categories()
        cb_status = "已连接" if self.codebuddy.enabled else "未配置"
        remote_status = "已连接" if (hasattr(self, "remote") and self.remote.enabled) else "待网络"
        total_available = len(self.list_all())
        lines = [
            "## 技能市场",
            f"- 已安装: {installed} 个技能包",
            f"- 市场可用: {total_available} 个",
            f"- 分类: {', '.join(cats)}",
            f"- CodeBuddy 本地市场: {cb_status}",
            f"- CodeBuddy 远程市场: {remote_status}",
            "- 安装技能: /skill install <name>",
            "- 搜索技能: /skill search <keyword>",
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 单例（线程安全双重检查锁）
# ═══════════════════════════════════════════════════════════════

_marketplace: MarketplaceClient | None = None
_marketplace_lock = threading.Lock()


def get_marketplace() -> MarketplaceClient:
    global _marketplace
    if _marketplace is None:
        with _marketplace_lock:
            if _marketplace is None:
                _marketplace = MarketplaceClient()
    return _marketplace


def reset_marketplace() -> None:
    """Reset the marketplace singleton (test isolation / hot reload).

    MarketplaceClient adapters hold short-TTL caches only; no threads or
    open handles. Lock is stateless and reused.
    """
    global _marketplace
    with _marketplace_lock:
        _marketplace = None
