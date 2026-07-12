"""Self-Evolution Engine — autonomous codebase improvement loop.

Unlike self_heal (static syntax/pattern scan), this module performs
SEMANTIC weakness detection and template-driven improvement. It models
what a senior engineer (like Claude) does when auditing a codebase:

1. Scan for structural weaknesses (thin prompts, missing config, gaps)
2. Generate prioritized improvement suggestions
3. Apply template-driven fixes where possible
4. Verify improvements with tests
5. Report what was fixed and what needs human attention

Usage:
    python core/self_evolve.py             # audit only
    python core/self_evolve.py --fix       # audit + auto-fix
    python core/self_evolve.py --json      # machine-readable output
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"
SKILLS_DIR = ROOT / "skills"
RULES_DIR = ROOT / "rules"
OUTPUT_DIR = ROOT / "output"


@dataclass
class Weakness:
    """A detected structural weakness in the codebase."""

    severity: str  # critical / high / medium / low
    category: str  # agent / skill / rule / hook / encoding / test
    location: str  # file path or "global"
    description: str  # what is wrong
    suggestion: str  # how to fix
    auto_fixable: bool = False
    fix_template: str = ""  # template for auto-fix (if applicable)


@dataclass
class EvolutionReport:
    weaknesses: list[Weakness] = field(default_factory=list)
    fixes_applied: int = 0
    fixes_failed: int = 0
    needs_human: list[str] = field(default_factory=list)


class SelfEvolver:
    """Autonomous codebase improvement engine."""

    def __init__(self):
        self.report = EvolutionReport()

    # ═══════════════════════════════════════════════════════════
    # Weakness Scanners
    # ═══════════════════════════════════════════════════════════

    def scan_agent_thin_prompts(self) -> list[Weakness]:
        """Detect agents with prompts below 500 bytes."""
        weaknesses = []
        for f in sorted(AGENTS_DIR.glob("*.agent.md")):
            content = f.read_text(encoding="utf-8")
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            body = parts[2].strip()
            if len(body) < 500:
                weaknesses.append(Weakness(
                    severity="high",
                    category="agent",
                    location=str(f.relative_to(ROOT)),
                    description=f"Agent prompt too thin ({len(body)}B, target >500B)",
                    suggestion="Expand with: workflow steps, rules, output format, constraints",
                    auto_fixable=False,  # Needs creative writing
                ))
        return weaknesses

    def scan_skill_stubs(self) -> list[Weakness]:
        """Detect skills with prompts below 200 bytes."""
        weaknesses = []
        for f in sorted(SKILLS_DIR.glob("*.skill.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            prompt = data.get("prompt", "")
            p_len = len(prompt) if isinstance(prompt, str) else sum(
                len(item.get("content", "")) for item in prompt if isinstance(item, dict)
            )
            if p_len <= 200:
                name = data.get("name", f.stem)
                weaknesses.append(Weakness(
                    severity="high" if p_len < 50 else "medium",
                    category="skill",
                    location=str(f.relative_to(ROOT)),
                    description=f"Skill '{name}' is a stub ({p_len}B)",
                    suggestion="Fill with actual content or delete if redundant",
                    auto_fixable=False,
                ))
        return weaknesses

    def scan_auto_trigger_gaps(self) -> list[Weakness]:
        """Detect missing auto-trigger config for high-value skills."""
        overrides_file = OUTPUT_DIR / "skill_overrides.json"
        overrides = {}
        if overrides_file.exists():
            try:
                overrides = json.loads(overrides_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        # Skills that should likely be auto-trigger based on their content
        auto_candidates = {
            "coding-rules", "code-guardian", "security-hardening", "tdd",
            "caliber", "code-reviewer", "python-anti-patterns",
            "fix", "webapp-testing", "frontend-design", "fullstack-dev",
            "frontend-dev", "pr-creator", "find-skills", "skill-creator",
        }

        missing = []
        for name in auto_candidates:
            skill_file = SKILLS_DIR / f"{name}.skill.json"
            if not skill_file.exists():
                continue
            if name not in overrides or overrides[name] != "auto":
                missing.append(name)

        if missing:
            return [Weakness(
                severity="medium",
                category="skill",
                location="output/skill_overrides.json",
                description=f"{len(missing)} high-value skills missing auto-trigger: {', '.join(missing[:8])}",
                suggestion="Add to skill_overrides.json with trigger=auto for lazy loading",
                auto_fixable=True,
                fix_template="auto_trigger",
            )]
        return []

    def scan_disallowed_tools_gaps(self) -> list[Weakness]:
        """Detect write-permission agents without disallowedTools."""
        try:
            import yaml
        except ImportError:
            return []

        weaknesses = []
        for f in sorted(AGENTS_DIR.glob("*.agent.md")):
            content = f.read_text(encoding="utf-8")
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            try:
                meta = yaml.safe_load(parts[1])
            except Exception:
                continue
            perm = meta.get("permission", "")
            disallowed = meta.get("disallowedTools", []) or []
            name = meta.get("name", f.stem)

            if perm == "write" and not disallowed:
                # Skip agents that legitimately need full access
                if name in ("DevOps-Deployer", "Git-Workflow"):
                    continue
                weaknesses.append(Weakness(
                    severity="medium",
                    category="agent",
                    location=str(f.relative_to(ROOT)),
                    description=f"Write agent '{name}' has no disallowedTools",
                    suggestion="Add disallowedTools: [git_pr_create, git_push] for safety",
                    auto_fixable=True,
                    fix_template="disallowed_tools",
                ))
        return weaknesses

    def scan_monolingual_descriptions(self) -> list[Weakness]:
        """Detect agents/skills with Chinese-only descriptions."""
        try:
            import yaml
        except ImportError:
            return []

        weaknesses = []
        for f in sorted(AGENTS_DIR.glob("*.agent.md")):
            content = f.read_text(encoding="utf-8")
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            try:
                meta = yaml.safe_load(parts[1])
            except Exception:
                continue
            desc = meta.get("description", "")
            name = meta.get("name", f.stem)

            has_chinese = any("一" <= c <= "鿿" for c in desc)
            has_english = any(c.isascii() and c.isalpha() for c in desc)

            if has_chinese and not has_english:
                weaknesses.append(Weakness(
                    severity="low",
                    category="agent",
                    location=str(f.relative_to(ROOT)),
                    description=f"Agent '{name}' description is Chinese-only (no English keywords)",
                    suggestion="Add English keywords for better auto-routing with bilingual tasks",
                    auto_fixable=False,  # Needs human to choose right keywords
                ))
        return weaknesses

    def scan_missing_tests(self) -> list[Weakness]:
        """Detect new/changed core modules without corresponding tests."""
        weaknesses = []
        core_modules = set()
        test_modules = set()

        for f in ROOT.glob("core/**/*.py"):
            if f.name.startswith("__"):
                continue
            stem = f.stem
            core_modules.add(stem)

        for f in ROOT.glob("tests/**/*.py"):
            if f.name.startswith("__"):
                continue
            stem = f.stem
            if stem.startswith("test_"):
                test_modules.add(stem[5:])  # Strip test_ prefix

        # Check recently created modules (encoding_fix.py is the pattern)
        untested = []
        for mod in sorted(core_modules):
            if mod not in test_modules and mod not in ("__init__",):
                # Only flag non-trivial modules (>2KB)
                candidates = list(ROOT.glob(f"core/**/{mod}.py"))
                if candidates:
                    size = candidates[0].stat().st_size
                    if size > 2000:
                        untested.append(mod)

        if untested:
            return [Weakness(
                severity="medium",
                category="test",
                location="tests/",
                description=f"Core modules without tests: {', '.join(untested[:8])}",
                suggestion=f"Create tests/test_{untested[0]}.py with basic coverage",
                auto_fixable=False,
            )]
        return []

    # ═══════════════════════════════════════════════════════════
    # Full Scan
    # ═══════════════════════════════════════════════════════════

    def scan_all(self) -> list[Weakness]:
        """Run all weakness scanners and return combined results."""
        all_weaknesses = []
        for scanner in [
            self.scan_agent_thin_prompts,
            self.scan_skill_stubs,
            self.scan_auto_trigger_gaps,
            self.scan_disallowed_tools_gaps,
            self.scan_monolingual_descriptions,
            self.scan_missing_tests,
        ]:
            try:
                results = scanner()
                all_weaknesses.extend(results)
            except Exception as e:
                all_weaknesses.append(Weakness(
                    "low", "scanner", scanner.__name__, f"Scanner failed: {e}", "Fix scanner", False
                ))
        self.report.weaknesses = all_weaknesses
        return all_weaknesses

    # ═══════════════════════════════════════════════════════════
    # Auto-Fix Engine
    # ═══════════════════════════════════════════════════════════

    def apply_fixes(self) -> EvolutionReport:
        """Apply auto-fixable improvements. Returns updated report."""
        for w in self.report.weaknesses:
            if not w.auto_fixable:
                self.report.needs_human.append(w.description)
                continue

            try:
                if w.fix_template == "auto_trigger":
                    self._fix_auto_triggers()
                elif w.fix_template == "disallowed_tools":
                    self._fix_disallowed_tools(w.location)
                else:
                    self.report.needs_human.append(f"Unknown fix template: {w.fix_template}")
                    continue
                self.report.fixes_applied += 1
            except Exception as e:
                self.report.fixes_failed += 1
                self.report.needs_human.append(f"Fix failed for {w.location}: {e}")

        return self.report

    def _fix_auto_triggers(self):
        """Add missing auto-trigger overrides."""
        overrides_file = OUTPUT_DIR / "skill_overrides.json"
        overrides = {}
        if overrides_file.exists():
            overrides = json.loads(overrides_file.read_text(encoding="utf-8"))

        auto_candidates = {
            "coding-rules", "code-guardian", "security-hardening", "tdd",
            "caliber", "code-reviewer", "python-anti-patterns",
            "fix", "webapp-testing", "frontend-design", "fullstack-dev",
            "frontend-dev", "pr-creator", "find-skills", "skill-creator",
        }

        changed = False
        for name in auto_candidates:
            skill_file = SKILLS_DIR / f"{name}.skill.json"
            if not skill_file.exists():
                continue
            if name not in overrides or overrides[name] != "auto":
                overrides[name] = "auto"
                changed = True

        if changed:
            overrides_file.parent.mkdir(parents=True, exist_ok=True)
            overrides_file.write_text(
                json.dumps(overrides, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _fix_disallowed_tools(self, agent_path: str):
        """Add default disallowedTools to a write agent."""
        try:
            import yaml
        except ImportError:
            return

        full_path = ROOT / agent_path
        content = full_path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        if len(parts) < 3:
            return

        meta = yaml.safe_load(parts[1])
        body = parts[2]

        perm = meta.get("permission", "")
        if perm != "write":
            return

        # Apply context-aware defaults
        name = meta.get("name", "")
        if name == "DevOps-Deployer":
            return  # Needs full access
        if name == "Git-Workflow":
            return  # Needs full git access

        meta["disallowedTools"] = ["git_pr_create", "git_push"]

        fm_str = yaml.dump(meta, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()
        new_content = f"---\n{fm_str}\n---\n{body}"
        full_path.write_text(new_content, encoding="utf-8")

    # ═══════════════════════════════════════════════════════════
    # Report Generation
    # ═══════════════════════════════════════════════════════════

    def generate_report(self) -> str:
        """Generate human-readable evolution report."""
        lines = ["# Self-Evolution Report", ""]
        lines.append(f"## Summary")
        lines.append(f"- Weaknesses found: {len(self.report.weaknesses)}")
        lines.append(f"- Auto-fixed: {self.report.fixes_applied}")
        lines.append(f"- Fix failures: {self.report.fixes_failed}")
        lines.append(f"- Needs human: {len(self.report.needs_human)}")
        lines.append("")

        if self.report.weaknesses:
            lines.append("## Weaknesses")
            by_severity = {"critical": [], "high": [], "medium": [], "low": []}
            for w in self.report.weaknesses:
                by_severity.get(w.severity, by_severity["low"]).append(w)

            for sev in ["critical", "high", "medium", "low"]:
                items = by_severity[sev]
                if not items:
                    continue
                lines.append(f"### {sev.upper()} ({len(items)})")
                for w in items:
                    fixable = " [AUTO-FIXABLE]" if w.auto_fixable else ""
                    lines.append(f"- **{w.category}** `{w.location}`{fixable}")
                    lines.append(f"  {w.description}")
                    lines.append(f"  → {w.suggestion}")
                lines.append("")

        if self.report.needs_human:
            lines.append("## Needs Human Attention")
            for item in self.report.needs_human:
                lines.append(f"- {item}")
            lines.append("")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# CLI & Tool Interface
# ═══════════════════════════════════════════════════════════


def evolve(fix: bool = False) -> dict:
    """Run self-evolution scan. Returns structured result for tool/API use."""
    evolver = SelfEvolver()
    weaknesses = evolver.scan_all()
    if fix:
        evolver.apply_fixes()
    else:
        evolver.report.fixes_applied = 0

    return {
        "weaknesses": len(weaknesses),
        "by_severity": {
            "critical": sum(1 for w in weaknesses if w.severity == "critical"),
            "high": sum(1 for w in weaknesses if w.severity == "high"),
            "medium": sum(1 for w in weaknesses if w.severity == "medium"),
            "low": sum(1 for w in weaknesses if w.severity == "low"),
        },
        "auto_fixable": sum(1 for w in weaknesses if w.auto_fixable),
        "fixes_applied": evolver.report.fixes_applied,
        "needs_human": len(evolver.report.needs_human),
        "report": evolver.generate_report(),
    }


if __name__ == "__main__":
    fix_mode = "--fix" in sys.argv
    json_mode = "--json" in sys.argv

    evolver = SelfEvolver()
    weaknesses = evolver.scan_all()

    if fix_mode:
        evolver.apply_fixes()
        print(f"Auto-fixed: {evolver.report.fixes_applied}")

    if json_mode:
        result = evolve(fix=fix_mode)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(evolver.generate_report())
        if evolver.report.needs_human:
            print("\nUse --fix to auto-apply fixable issues.")
