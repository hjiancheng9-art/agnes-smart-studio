"""Skill Manifest Schema — 技能包最小可行规范

基于 GPT 架构审计 Q2 建议：
- 必填：name, version, description, runtime, permissions, requires, entrypoint
- 可选：integrity(sha256), min_crux_version, author
- permission 基于 capability 模型，不是 crude filesystem r/w
- runtime 决定加载方式：prompt | declarative | python_subprocess

加载时机：只做 integrity 校验 + manifest 解析，不做运行时沙箱扫描。
运行时隔离由 runtime 字段决定执行方式，不依赖 manifest 静态分析。
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Literal

# ── Capability-based permissions (not filesystem r/w) ─────
# 参考: browser-control 技能 -> 声明 ["cdp", "clipboard:read"]
# 而非 "filesystem:write", "network:outbound"
KNOWN_PERMISSIONS = {
    # Browser
    "cdp": "Chrome DevTools Protocol access",
    "browser:navigate": "Navigate browser to URLs",
    "browser:screenshot": "Take browser screenshots",
    "browser:input": "Inject input into browser pages",
    # Filesystem (scoped)
    "fs:read": "Read files from filesystem",
    "fs:write": "Write files to filesystem",
    "fs:project": "Access project directory only",
    # Network
    "network:outbound": "Make outbound HTTP requests",
    "network:listen": "Listen on network ports",
    # Execution
    "exec:python": "Execute Python code (subprocess)",
    "exec:shell": "Execute shell commands",
    # Media
    "media:image": "Generate/process images",
    "media:video": "Generate/process videos",
    "media:audio": "Generate/process audio",
    # AI
    "ai:prompt": "Send prompts to external AI APIs",
    "ai:embedding": "Generate embeddings",
    # System
    "system:env": "Read environment variables",
    "system:process": "Spawn/manage processes",
}

RuntimeType = Literal["prompt", "declarative", "python_subprocess", "python_inline", "docker"]


ConfidenceScore = float  # 0.0 - 1.0

ReviewStatus = Literal[
    "auto-inferred",  # 自动推断，置信度高
    "auto-inferred-degraded",  # 自动推断，置信度中（运行时降级）
    "user-confirmed",  # 用户确认过
    "user-modified",  # 用户修改过
]


@dataclass
class SkillManifest:
    """Minimum viable skill manifest."""

    # Required
    name: str
    version: str  # semver
    description: str
    runtime: RuntimeType = "prompt"
    permissions: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)  # other skill names
    entrypoint: str = ""  # path to skill definition file

    # Optional
    integrity: str = ""  # sha256 of entrypoint file
    min_crux_version: str = ""
    author: str = ""
    homepage: str = ""
    license: str = ""
    review_status: str = ""
    inference_confidence: float = 0.0

    def validate(self) -> list[str]:
        """Validate manifest. Returns list of errors (empty = valid)."""
        errors = []

        if not self.name or not self.name.strip():
            errors.append("name is required")

        if not self.version:
            errors.append("version is required")
        elif not _is_semver(self.version):
            errors.append(f"version '{self.version}' is not valid semver")

        if not self.description:
            errors.append("description is required")

        valid_runtimes = {"prompt", "declarative", "python_subprocess", "python_inline", "docker"}
        if self.runtime not in valid_runtimes:
            errors.append(f"runtime '{self.runtime}' not in {valid_runtimes}")

        # Check permissions against known set
        unknown_perms = [p for p in self.permissions if p not in KNOWN_PERMISSIONS]
        if unknown_perms:
            # Not a hard error, just a warning — skills can define custom permissions
            pass

        if not self.entrypoint:
            errors.append("entrypoint is required")

        return errors

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "runtime": self.runtime,
            "permissions": self.permissions,
            "requires": self.requires,
            "entrypoint": self.entrypoint,
            "integrity": self.integrity,
            "min_crux_version": self.min_crux_version,
            "author": self.author,
            "homepage": self.homepage,
            "license": self.license,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SkillManifest":
        return cls(
            name=data.get("name", ""),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            runtime=data.get("runtime", "prompt"),
            permissions=data.get("permissions", []),
            requires=data.get("requires", []),
            entrypoint=data.get("entrypoint", ""),
            integrity=data.get("integrity", ""),
            min_crux_version=data.get("min_crux_version", ""),
            author=data.get("author", ""),
            homepage=data.get("homepage", ""),
            license=data.get("license", ""),
        )

    def verify_integrity(self, base_dir: str = ".") -> bool:
        """Verify sha256 of entrypoint file matches integrity field."""
        if not self.integrity or not self.entrypoint:
            return True  # no integrity check requested

        fpath = os.path.join(base_dir, self.entrypoint)
        if not os.path.exists(fpath):
            return False

        try:
            with open(fpath, "rb") as f:
                actual = hashlib.sha256(f.read()).hexdigest()
            return actual == self.integrity
        except Exception:
            return False


def _is_semver(version: str) -> bool:
    """Basic semver check: X.Y.Z or X.Y.Z-pre+meta."""
    import re

    pattern = r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$"
    return bool(re.match(pattern, version))


def load_manifest(path: str) -> SkillManifest:
    """Load a skill manifest from JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    manifest = SkillManifest.from_dict(data)
    errors = manifest.validate()
    if errors:
        raise ValueError(f"Invalid manifest at {path}: {'; '.join(errors)}")
    return manifest


# ── Runtime Inference for Legacy Skills ────────────────────

# Patterns for inferring runtime from skill content
_RUNTIME_HINTS = {
    "declarative": [
        "steps",
        "workflow",
        "nodes",
        "connections",
        "browser",
        "cdp",
        "playwright",
        "screenshot",
        "navigate",
        "comfyui",
        "imagegen",
        "dimension",
        "resolution",
        "cinematic",
        "audio",
        "media",
        "encode",
    ],
    "python_subprocess": [
        "script",
        "command",
        "execute",
        "subprocess",
        "run_bash",
        "shell",
        "pip",
        "install",
        "process",
    ],
    "python_inline": [
        "import ",
        "def ",
        "class ",
        "asyncio",
        "__init__",
    ],
    "docker": [
        "container",
        "docker",
        "image:",
        "Dockerfile",
    ],
}


def infer_runtime(skill_data: dict) -> tuple[str, float]:
    """从技能内容推断最佳 runtime 类型，返回 (runtime, confidence)。

    优先级: declarative > python_inline > python_subprocess > docker > prompt
    Confidence 计算：
      - 严格匹配（keys/structure）→ 0.9+
      - 松散匹配（关键词）→ 0.6-0.8
      - 冲突匹配（同时命中多个）→ 0.3-0.5
      - 无匹配 → 0.1（prompt fallback）

    Args:
        skill_data: 技能定义的字典

    Returns:
        (RuntimeType, confidence_score)
    """
    skill_str = json.dumps(skill_data).lower()

    # Count hints for each runtime
    scores: dict[str, int] = {}
    for runtime, hints in _RUNTIME_HINTS.items():
        scores[runtime] = sum(1 for h in hints if h in skill_str)

    total_hints = sum(scores.values())

    # ── Strict matches (high confidence) ──
    if isinstance(skill_data, dict):
        # "steps" at top level → almost certainly declarative
        if "steps" in skill_data:
            # Check if steps look like declarations (list of dicts) vs text
            steps = skill_data.get("steps", [])
            if isinstance(steps, list) and len(steps) > 0:
                if isinstance(steps[0], dict) and "action" in steps[0]:
                    return "declarative", 0.95
            return "declarative", 0.85

        workflow_keys = {"workflow", "nodes", "connections", "workflow_json"}
        if any(k in skill_data for k in workflow_keys):
            return "declarative", 0.90

        # "script" or "command" at top level → python_subprocess
        if "script" in skill_data or "command" in skill_data:
            return "python_subprocess", 0.80

    # ── Keyword-based (medium confidence) ──
    scores.get("declarative", 0)
    scores.get("python_inline", 0)
    scores.get("python_subprocess", 0)

    # Check for conflicts: if description is the main source of keywords
    desc = ""
    if isinstance(skill_data, dict):
        desc = (skill_data.get("description", "") or "").lower()

    # Downweight description-only matches
    for runtime in _RUNTIME_HINTS:
        desc_hits = sum(1 for h in _RUNTIME_HINTS[runtime] if h in desc)
        if desc_hits > 0 and scores.get(runtime, 0) == desc_hits:
            # All hits came from description → low weight
            scores[runtime] = desc_hits * 0.1  # description hits worth 0.1

    # Recalculate with weighted scores
    weighted_decl = scores.get("declarative", 0)
    weighted_py = scores.get("python_inline", 0)
    weighted_sub = scores.get("python_subprocess", 0)
    weighted_docker = scores.get("docker", 0)

    # Browser / CDP → declarative
    if weighted_decl >= 2:
        return "declarative", min(0.85, 0.6 + weighted_decl * 0.08)

    # Python code
    if weighted_py >= 2:
        conf = min(0.80, 0.5 + weighted_py * 0.08)
        return "python_inline", conf

    # Subprocess
    if weighted_sub >= 2:
        conf = min(0.75, 0.5 + weighted_sub * 0.08)
        return "python_subprocess", conf

    # Docker
    if weighted_docker >= 1:
        return "docker", 0.60

    # Edge case: multiple weak matches → low confidence
    if total_hints > 0:
        best_runtime = max(scores, key=scores.get)
        best_score = scores[best_runtime]
        return best_runtime, max(0.3, best_score * 0.3)

    # Default: prompt (safest fallback)
    return "prompt", 0.10


def infer_permissions(skill_data: dict) -> list[str]:
    """从技能内容推断权限声明（带 description 加权降级）。"""
    skill_str = json.dumps(skill_data).lower()
    perms = set()

    # Separate description from actual content
    if isinstance(skill_data, dict):
        (skill_data.get("description", "") or "").lower()

    _perm_hints = {
        "cdp": ["browser", "cdp", "playwright", "navigate", "screenshot"],
        "browser:navigate": ["navigate", "goto", "url"],
        "browser:screenshot": ["screenshot", "capture"],
        "browser:input": ["input", "click", "type", "fill", "keyboard"],
        "fs:read": ["read_file", "file_path", "path", "open("],
        "fs:write": ["write_file", "create_file", "patch_file"],
        "network:outbound": ["http", "request", "api", "fetch", "download"],
        "exec:python": ["python", "run_python", "exec"],
        "exec:shell": ["bash", "shell", "command", "subprocess"],
        "media:image": ["image", "picture", "photo", "pixel", "resolution"],
        "media:video": ["video", "animation", "frame", "motion"],
        "media:audio": ["audio", "sound", "voice", "tts", "speech"],
        "ai:prompt": ["prompt", "llm", "model", "generate"],
    }

    for perm, hints in _perm_hints.items():
        if any(h in skill_str for h in hints):
            perms.add(perm)

    return sorted(perms)


def generate_legacy_manifest(
    skill_path: str,
    skill_data: dict | None = None,
) -> "SkillManifest":
    """为旧技能生成兼容 manifest（阶段 1 迁移）。

    自动推断 runtime + permissions，附带 confidence score。
    根据 confidence 设置 review_status：
      >= 0.8  → auto-inferred
      0.5-0.8 → auto-inferred-degraded（运行时降级）
      < 0.5   → 不设置 review_status（需人工确认）

    Args:
        skill_path: 技能文件路径（如 skills/browser-control.skill.json）
        skill_data: 已加载的技能数据（可选，不传则从文件读取）

    Returns:
        SkillManifest 实例
    """
    if skill_data is None:
        with open(skill_path, encoding="utf-8") as f:
            skill_data = json.load(f)

    name = os.path.splitext(os.path.basename(skill_path))[0]
    if name.endswith(".skill"):
        name = name[:-6]

    runtime, confidence = infer_runtime(skill_data)
    permissions = infer_permissions(skill_data)

    # Determine review_status from confidence
    if confidence >= 0.8:
        review_status = "auto-inferred"
    elif confidence >= 0.5:
        review_status = "auto-inferred-degraded"
    else:
        review_status = ""

    requires = []
    if isinstance(skill_data, dict):
        requires = skill_data.get("requires", []) or []

    description = ""
    if isinstance(skill_data, dict):
        description = skill_data.get("description", "")

    author = ""
    if isinstance(skill_data, dict):
        author = skill_data.get("author", "")

    return SkillManifest(
        name=name,
        version="0.0.0-legacy",
        description=description or f"Auto-generated legacy manifest for {name}",
        runtime=runtime,
        permissions=permissions,
        requires=list(requires) if requires else [],
        entrypoint=skill_path,
        author=author or "Auto-generated",
        min_crux_version="5.0.0",
        review_status=review_status,
        inference_confidence=confidence,
    )


# ── Example manifest for browser-control ─────────────────
EXAMPLE_MANIFEST = SkillManifest(
    name="browser-control",
    version="1.2.0",
    description="Playwright CDP 全浏览器操控 — 通过 Chrome DevTools Protocol 远程操控 Edge/Chrome 浏览器",
    runtime="declarative",
    permissions=["cdp", "browser:navigate", "browser:screenshot", "browser:input", "network:outbound"],
    requires=[],
    entrypoint="skills/browser-control.skill.json",
    author="CRUX Studio",
    min_crux_version="5.0.0",
)
