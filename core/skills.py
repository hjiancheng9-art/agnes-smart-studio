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
import threading
from pathlib import Path

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = ["SKILLS_DIR", "Skill", "SkillManager", "get_manager"]


SKILLS_DIR = Path(__file__).parent.parent / "skills"


class Skill:
    """单个技能"""

    # 三态 trigger（对标 Claude 的 on / user-invocable-only / name-only）
    TRIGGER_AUTO = "auto"  # 自动注入 system prompt（如 coding-rules）
    TRIGGER_MANUAL = "manual"  # 仅 /skill load 显式加载（默认，向后兼容）
    TRIGGER_OFF = "off"  # 完全隐藏，不出现在 list
    _VALID_TRIGGERS = (TRIGGER_AUTO, TRIGGER_MANUAL, TRIGGER_OFF)

    def __init__(self, data: dict, file_path: Path) -> None:
        self.name = data.get("name", file_path.stem)
        self.description = data.get("description", "")
        self.version = data.get("version", "1.0")
        self.prompt = data.get("prompt", "")
        self.icon = data.get("icon", "")
        self.tools = data.get("tools", [])
        self.trigger = data.get("trigger", self.TRIGGER_MANUAL)
        # 兜底：非法值归 manual
        if self.trigger not in self._VALID_TRIGGERS:
            self.trigger = self.TRIGGER_MANUAL
        self.file = file_path

    def __repr__(self):
        return f"Skill({self.name}, trigger={self.trigger})"


class SkillManager:
    """技能管理器：发现、加载、卸载"""

    # overrides 配置文件路径（对标 Claude 的 skillOverrides）
    OVERRIDES_FILE = Path(__file__).parent.parent / "output" / "skill_overrides.json"

    def __init__(self, skills_dir: Path | None = None) -> None:
        self._dir = skills_dir or SKILLS_DIR
        self._loaded: Skill | None = None
        self._available: dict[str, Skill] = {}  # auto/manual 态（用户可见）
        self._all_skills: dict[str, Skill] = {}  # 全量（含 off 态，给 /skill mode 用）
        self._overrides: dict[str, str] = {}  # name -> trigger 覆盖
        # 实例锁：保护 _overrides / _available / _all_skills 的读-改-写一致性
        # （discover/set_trigger/_save_overrides 均在锁内）
        self._lock = threading.RLock()

    def _load_overrides(self) -> dict[str, str]:
        """从 output/skill_overrides.json 读 trigger 覆盖配置。

        格式: {"skill-name": "auto"|"manual"|"off", ...}
        缺失或损坏时返回空 dict（不阻塞 discover）。
        """
        if not self.OVERRIDES_FILE.exists():
            return {}
        try:
            data = json.loads(self.OVERRIDES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # 只保留合法值
                return {k: v for k, v in data.items() if v in Skill._VALID_TRIGGERS}
        except (json.JSONDecodeError, OSError):
            pass
        return {}

    def discover(self) -> dict[str, Skill]:
        """扫描 skills/ 目录，发现所有可用技能

        应用 trigger 三态：
        - off: 不加入 _available（完全隐藏）
        - auto/manual: 加入 _available
        - overrides 优先级 > skill 文件中的 trigger 字段

        同时维护 _all_skills（全量，含 off 态），供 /skill mode 列举。
        """
        with self._lock:
            return self._discover_inner()

    def _discover_inner(self) -> dict[str, Skill]:
        """discover 的实际实现（必须在 _lock 内调用）。"""
        self._available.clear()
        self._all_skills.clear()
        self._overrides = self._load_overrides()
        if not self._dir.exists():
            self._dir.mkdir(parents=True, exist_ok=True)
            return self._available

        for f in sorted(self._dir.glob("*.skill.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                skill = Skill(data, f)
                # 应用 overrides（优先级最高）
                if skill.name in self._overrides:
                    skill.trigger = self._overrides[skill.name]
                # _all_skills 始终收录（含 off 态，给 /skill mode 用）
                self._all_skills[skill.name] = skill
                # off 态：不加入 _available（用户不可见）
                if skill.trigger == Skill.TRIGGER_OFF:
                    continue
                self._available[skill.name] = skill
            except (json.JSONDecodeError, KeyError):
                pass
        return self._available

    @property
    def loaded(self) -> Skill | None:
        return self._loaded

    @property
    def available_names(self) -> list[str]:
        return list(self._available.keys())

    def load(self, name: str) -> Skill | None:
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

    def auto_skills_prompt(self, base_prompt: str) -> str:
        """扫描所有 trigger=auto 的技能，注入其 prompt 到 base_prompt 末尾。

        对标 Claude 的 auto-trigger skills（如 coding-rules）。
        与手动 load 的 skill 共存：手动加载的技能 prompt 由 get_system_prompt 处理，
        auto 类技能由本方法在 _build_system_prompt 末尾统一注入。

        Args:
            base_prompt: 当前 system prompt（可能已含手动 skill）
        Returns:
            拼接 auto skills 后的完整 prompt
        """
        # 确保 _available 已 discover（首次调用兜底）
        if not self._available:
            self.discover()
        auto_skills = [
            s
            for s in self._available.values()
            if s.trigger == Skill.TRIGGER_AUTO and s.name != (self._loaded.name if self._loaded else "")
        ]
        if not auto_skills:
            return base_prompt
        parts = [base_prompt]
        for skill in auto_skills:
            sp = skill.prompt.strip()
            if sp:
                parts.append(f"\n\n[Skill 自动激活: {skill.name}]\n{sp}")
        return "".join(parts)

    # ── 三态控制（/skill mode 命令的后端）──

    def get_trigger(self, name: str) -> str | None:
        """查询技能当前生效 trigger 态。

        Returns:
            "auto" / "manual" / "off"，或 None（技能不存在）。
        优先返回 overrides 中的值；否则返回 skill 文件中的 trigger。
        """
        if not self._all_skills:
            self.discover()
        skill = self._all_skills.get(name)
        if skill is None:
            return None
        return self._overrides.get(name, skill.trigger)

    def set_trigger(self, name: str, trigger: str) -> bool:
        """设置技能 trigger 态，持久化到 output/skill_overrides.json。

        Args:
            name: 技能名
            trigger: "auto" / "manual" / "off"（非法值拒绝）
        Returns:
            True 成功；False（技能不存在或 trigger 非法）
        """
        if trigger not in Skill._VALID_TRIGGERS:
            return False
        with self._lock:
            if not self._all_skills:
                self._discover_inner()
            if name not in self._all_skills:
                return False
            # 比较当前生效值（overrides 优先于文件原值），避免基准错误
            current = self._overrides.get(name, self._all_skills[name].trigger)
            if trigger == current:
                return True
            old_override = self._overrides.get(name)
            self._overrides[name] = trigger
            if not self._save_overrides():
                # 写盘失败 → 回滚内存，保证内存与磁盘一致
                if old_override is not None:
                    self._overrides[name] = old_override
                else:
                    self._overrides.pop(name, None)
                return False
            self._discover_inner()
            return True

    def _save_overrides(self) -> bool:
        """把 _overrides 持久化到 output/skill_overrides.json（原子写）。

        Returns:
            True 写盘成功；False 写盘失败（调用方负责回滚内存）。
        """
        tmp = self.OVERRIDES_FILE.with_suffix(".json.tmp")
        try:
            self.OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps(self._overrides, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self.OVERRIDES_FILE)
            return True
        except OSError:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            return False

    def list_all(self) -> list[Skill]:
        """返回全量技能列表（含 off 态），按 trigger 分组方便 /skill mode 展示。"""
        if not self._all_skills:
            self.discover()
        return sorted(self._all_skills.values(), key=lambda s: s.name)

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

            except (json.JSONDecodeError, TypeError, KeyError) as e:
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


# 全局单例（线程安全双重检查锁）
_manager: SkillManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> SkillManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = SkillManager()
                _manager.create_examples()
                _manager.discover()
    return _manager


def reset_skill_manager() -> None:
    """Reset the skill manager singleton (test isolation / hot reload).

    SkillManager is pure in-memory (loaded/available/overrides dicts). The
    next get_manager() call re-runs create_examples()/discover(), which is
    idempotent. Lock is stateless and reused.
    """
    global _manager
    with _manager_lock:
        _manager = None


def resolve_skill_executor(tool_name: str, tool_def: dict | None = None):
    """Return a real executor callable for a skill tool, or a deprecation stub."""
    import logging
    import os
    import tempfile

    _log = logging.getLogger("crux.skills.exec")

    if tool_name in ("generate_image", "imagegen", "text_to_image", "t2i"):

        def _exec(**kw):
            from core.client import CruxClient
            from engines.text_to_image import TextToImageEngine

            with CruxClient() as c:
                return TextToImageEngine(c).generate(
                    prompt=kw.get("prompt", ""),
                    size=kw.get("size", "1024x768"),
                    seed=kw.get("seed"),
                    negative_prompt=kw.get("negative_prompt"),
                )

        return _exec

    if tool_name in ("image_to_image", "i2i", "img2img"):

        def _exec(**kw):
            from core.client import CruxClient
            from engines.image_to_image import ImageToImageEngine

            with CruxClient() as c:
                url = kw.get("image_url", "")
                return ImageToImageEngine(c).edit(
                    prompt=kw.get("prompt", ""), image_urls=[url] if url else [], size=kw.get("size", "1024x768")
                )

        return _exec

    if tool_name in ("generate_video", "videogen", "text_to_video", "t2v"):

        def _exec(**kw):
            from core.client import CruxClient
            from engines.video import VideoEngine

            with CruxClient() as c:
                return VideoEngine(c).text_to_video(
                    prompt=kw.get("prompt", ""), negative_prompt=kw.get("negative_prompt"), seed=kw.get("seed")
                )

        return _exec

    if tool_name in ("text_to_speech", "tts", "tts_narration"):

        def _exec(**kw):
            text = kw.get("text", "")
            out = kw.get("output", "") or os.path.join(tempfile.gettempdir(), f"tts_{hash(text) % 10000}.mp3")
            r = run_subprocess(["edge-tts", "--text", text, "--write-media", out], timeout=30)
            return f"TTS generated: {out}" if r.returncode == 0 else f"TTS failed: {r.stderr}"

        return _exec

    if tool_name in ("run_python", "python"):

        def _exec(**kw):
            code = kw.get("code", "")
            with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8") as f:
                f.write(code)
            r = run_subprocess(["python", f.name], timeout=30)
            return r.stdout or r.stderr or "[no output]"

        return _exec

    if tool_name in ("run_test", "run_pytest"):

        def _exec(**kw):
            path = kw.get("path", "tests/")
            r = run_subprocess(["python", "-m", "pytest", path, "-q", "--tb=short"], timeout=120)
            return r.stdout or r.stderr or "[pytest done]"

        return _exec

    _log.warning("Skill tool '%s' has no real executor — using deprecation stub", tool_name)
    return lambda **kw: f"[{tool_name}] executor not implemented. Args: {list(kw.keys())}. This is a placeholder."
