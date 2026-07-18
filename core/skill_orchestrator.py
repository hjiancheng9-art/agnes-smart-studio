"""Skill Orchestrator — 智能体工具技能三层编排中枢。

Usage:
    from core.skill_orchestrator import SkillOrchestrator
    orch = SkillOrchestrator()
    plan = orch.plan("建一个用户登录系统")
    result = orch.execute(plan)

Architecture:
    goal → search_skills → compose_plan → execute_plan → learn
"""

from __future__ import annotations

import difflib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("crux.orchestrator")

ROOT = Path(__file__).resolve().parent.parent
SCORE_FILE = ROOT / "output" / "skill_scores.json"


# ── Data model ──────────────────────────────────────────


@dataclass
class SkillMatch:
    name: str
    description: str
    score: float  # 0-1 relevance
    category: str
    installed: bool


@dataclass
class PlanStep:
    skill_name: str
    goal: str
    depends_on: list[str] = field(default_factory=list)
    verify: str = ""  # shell command to verify success
    risk: str = "auto"  # auto | confirm | manual

    @property
    def needs_approval(self) -> bool:
        return self.risk in ("confirm", "manual")


@dataclass
class Plan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    mode: str = "auto"  # auto | semi | manual

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "mode": self.mode,
            "steps": [
                {"skill": s.skill_name, "goal": s.goal, "depends_on": s.depends_on, "verify": s.verify, "risk": s.risk}
                for s in self.steps
            ],
        }


# ── Scoring engine ──────────────────────────────────────


def _load_scores() -> dict[str, int]:
    try:
        if SCORE_FILE.exists():
            return json.loads(SCORE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_scores(scores: dict[str, int]) -> None:
    SCORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCORE_FILE.write_text(json.dumps(scores, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Orchestrator ────────────────────────────────────────


class SkillOrchestrator:
    """Unified entry point for goal→skills→plan→execute→learn pipeline."""

    def __init__(self):
        self._skills: list[dict] | None = None
        self._scores: dict[str, int] = _load_scores()

    # ── Search ───────────────────────────────────────────

    def _load_skills(self) -> list[dict]:
        if self._scores is None:
            self._scores = _load_scores()
        if self._skills is not None:
            return self._skills
        skills = []
        skills_dir = ROOT / "skills"
        if skills_dir.is_dir():
            for f in sorted(skills_dir.glob("*.skill.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if data.get("name"):
                        skills.append(data)
                except (json.JSONDecodeError, OSError):
                    pass
        skills_md = ROOT / "skills_md"
        if skills_md.is_dir():
            for f in sorted(skills_md.glob("*.skill.md")):
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    name = f.stem.replace("-", " ").title()
                    for line in text.split("\n"):
                        if line.startswith("# "):
                            name = line[2:].strip()
                            break
                    skills.append({"name": f.stem, "description": name, "category": "general", "installed": False})
                except OSError:
                    pass
        self._skills = skills
        return skills

    def search(self, goal: str, top_k: int = 5) -> list[SkillMatch]:
        """Semantic-ish search: weighted name match + description + category + history."""
        skills = self._load_skills()
        goal_lower = goal.lower()
        goal_words = set(w for w in goal_lower.split() if len(w) > 1)

        _STOP = frozenset({"the", "a", "an", "for", "in", "of", "to", "and", "or", "is", "my", "with", "this", "that"})
        goal_terms = goal_words - _STOP

        def _relevance(s: dict) -> float:
            name = s.get("name", "")
            desc = s.get("description", "")
            text = f"{name} {desc}".lower()
            text_words = set(text.split())

            # Name match (40% weight) — strongest signal
            name_score = 0.0
            for term in goal_terms:
                if term == name:
                    name_score += 1.0
                elif term in name:
                    name_score += 0.6
                elif name in term:
                    name_score += 0.4
                elif difflib.SequenceMatcher(None, term, name).ratio() > 0.6:
                    name_score += 0.3
            name_score = min(name_score / max(1, len(goal_terms)), 1.0) * 0.4

            # Description overlap (30% weight)
            desc_hits = len(goal_terms & text_words)
            desc_score = (desc_hits / max(1, len(goal_terms))) * 0.3

            # Category match (15% weight)
            cat = s.get("category", "").lower()
            cat_score = 0.15 if cat and any(cat in t or t in cat for t in goal_terms) else 0.0

            # Historical score (10% weight)
            hist = min(self._scores.get(name, 0) / 10.0, 0.1)

            # Installed bonus (5% weight)
            installed = 0.05 if s.get("installed", False) else 0.0

            return name_score + desc_score + cat_score + hist + installed

        scored = [(s, _relevance(s)) for s in skills]
        scored.sort(key=lambda x: -x[1])
        return [
            SkillMatch(
                name=s["name"],
                description=s.get("description", "")[:120],
                score=round(score, 3),
                category=s.get("category", "general"),
                installed=s.get("installed", False),
            )
            for s, score in scored[:top_k]
        ]

    # ── Plan ────────────────────────────────────────────

    def plan(self, goal: str, top_k: int = 5, mode: str = "auto") -> Plan:
        """Given a goal, search skills and compose a sequential plan.

        Args:
            goal: natural-language description of what to do
            top_k: number of skills to consider
            mode: auto (execute all) | semi (confirm writes) | manual (plan only)
        """
        matches = self.search(goal, top_k=top_k)
        if not matches:
            return Plan(goal=goal, mode=mode)

        best = matches[0]
        rest = matches[1:3]
        steps = []
        if best.score > 0.1:
            risk = self._classify_risk(best.name, goal)
            steps.append(PlanStep(skill_name=best.name, goal=goal, verify=self._guess_verify(best.name), risk=risk))
            for r in rest:
                if r.score > 0.1:
                    steps.append(PlanStep(skill_name=r.name, goal=f"补充: {r.description[:60]}", risk="auto"))
        return Plan(goal=goal, steps=steps, mode=mode)

    def _classify_risk(self, skill_name: str, goal: str) -> str:
        """Classify a skill step as auto/confirm/manual based on risk heuristics."""
        name_lower = skill_name.lower()
        goal_lower = goal.lower()
        # High-risk patterns: deployment, database migrations, deletion, production
        if any(w in goal_lower for w in ("deploy", "production", "prod", "delete", "drop", "truncate", "migrate", "schema")):
            return "confirm"
        if any(w in name_lower for w in ("deploy", "migration", "admin", "root")):
            return "confirm"
        # Medium-risk: file writes outside project, pip install
        if any(w in goal_lower for w in ("install", "uninstall", "publish", "release")):
            return "confirm"
        return "auto"

    def _guess_verify(self, skill_name: str) -> str:
        """Heuristic: guess a verification command from skill name."""
        hints = {
            "test": "pytest tests/ -q --tb=short",
            "lint": "ruff check core/",
            "format": "ruff format --check core/",
            "review": "python -c 'from core.code_review import run_review; run_review()'",
            "api": "pytest tests/test_api.py -q 2>/dev/null || echo 'no api tests'",
            "db": "python -c 'from core.sql_tools import test_connection; test_connection()' 2>/dev/null || echo 'no db check'",
            "build": "python -m build 2>/dev/null || pip install -e . --quiet",
            "deploy": "echo 'manual deployment — verify URL'",
        }
        for key, cmd in hints.items():
            if key in skill_name.lower():
                return cmd
        return "echo 'manual verification needed'"

    # ── Execute ─────────────────────────────────────────

    def execute(self, plan: Plan, *, confirm_fn=None) -> dict[str, Any]:
        """Execute a plan step by step, with verification and self-healing.

        Args:
            plan: the composed plan
            confirm_fn: optional callback(step_name, risk) → bool for approval
        """
        import subprocess
        import sys

        results: list[dict] = []
        overall_ok = True
        start = time.time()

        for i, step in enumerate(plan.steps):
            step_start = time.time()
            label = f"[orchestrator] step {i+1}/{len(plan.steps)}: {step.skill_name}"
            logger.info(label)

            # ── Approval gate ──
            if plan.mode == "manual":
                print(f"\n  [{step.risk.upper()}] {step.skill_name}: {step.goal}")
                print(f"     verify: {step.verify or 'none'}")
                if confirm_fn:
                    approved = confirm_fn(step.skill_name, step.risk)
                else:
                    approved = input("  Execute? [Y/n] ").strip().lower() != "n"
                if not approved:
                    results.append({"skill": step.skill_name, "ok": False, "error": "user declined", "duration_ms": 0})
                    overall_ok = False
                    continue
            elif step.needs_approval and plan.mode == "semi":
                print(f"\n  ⚠️  HIGH-RISK: {step.skill_name} ({step.risk})")
                if confirm_fn:
                    approved = confirm_fn(step.skill_name, step.risk)
                else:
                    approved = input("  Approve? [y/N] ").strip().lower() == "y"
                if not approved:
                    results.append({"skill": step.skill_name, "ok": False, "error": "approval denied", "duration_ms": 0})
                    overall_ok = False
                    continue

            # Verify preconditions
            for dep in step.depends_on:
                prev = next((r for r in results if r["skill"] == dep), None)
                if prev and not prev["ok"]:
                    results.append({"skill": step.skill_name, "ok": False, "error": f"dependency {dep} failed", "duration_ms": 0})
                    overall_ok = False
                    continue

            # Load and run the skill
            ok, output = self._run_skill(step.skill_name)
            duration_ms = int((time.time() - step_start) * 1000)

            # Verify
            verify_ok = True
            if step.verify and ok:
                try:
                    r = subprocess.run(step.verify, shell=True, capture_output=True, text=True, timeout=60, cwd=str(ROOT))
                    verify_ok = r.returncode == 0
                    if not verify_ok:
                        logger.info("[orchestrator] verification failed, self-healing")
                        subprocess.run([sys.executable, "core/self_heal.py", "--fix"], capture_output=True, timeout=30, cwd=str(ROOT))
                        r2 = subprocess.run(step.verify, shell=True, capture_output=True, text=True, timeout=60, cwd=str(ROOT))
                        verify_ok = r2.returncode == 0
                except (subprocess.TimeoutExpired, OSError):
                    verify_ok = False

            step_result = {"skill": step.skill_name, "ok": ok and verify_ok, "output": output[:500], "verify_ok": verify_ok, "duration_ms": duration_ms}
            results.append(step_result)
            if not step_result["ok"]:
                overall_ok = False
                break

        total_ms = int((time.time() - start) * 1000)
        summary = {"goal": plan.goal, "ok": overall_ok, "steps": len(plan.steps), "passed": sum(1 for r in results if r["ok"]), "duration_ms": total_ms, "results": results}
        self._learn(plan, results)
        return summary

    def _run_skill(self, skill_name: str) -> tuple[bool, str]:
        """Execute a skill by name. Falls back to skill_loader if available."""
        try:
            from core.skill_loader import load_and_run

            result = load_and_run(skill_name)
            return True, str(result)[:500]
        except ImportError:
            pass
        except Exception as e:
            return False, f"skill execution error: {e}"
        return False, f"skill '{skill_name}' not found or not executable"

    # ── Learn ──────────────────────────────────────────

    def _learn(self, plan: Plan, results: list[dict]) -> None:
        """Update skill scores based on execution results."""
        for r in results:
            name = r["skill"]
            delta = 1 if r["ok"] else -1
            self._scores[name] = self._scores.get(name, 0) + delta
        _save_scores(self._scores)


# ── Singleton ──────────────────────────────────────────

_orchestrator: SkillOrchestrator | None = None


def get_orchestrator() -> SkillOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SkillOrchestrator()
    return _orchestrator


def orchestrate(goal: str, mode: str = "auto") -> dict[str, Any]:
    """One-shot: plan + execute + learn."""
    orch = get_orchestrator()
    plan = orch.plan(goal, mode=mode)
    if not plan.steps:
        return {"ok": False, "error": "no matching skills found", "goal": goal}
    return orch.execute(plan)


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    mode = "auto"
    if "--semi" in args:
        mode = "semi"
        args.remove("--semi")
    if "--manual" in args:
        mode = "manual"
        args.remove("--manual")

    goal = " ".join(args) if args else "create a REST API"
    print(f"Goal: {goal}  Mode: {mode}\n")
    orch = SkillOrchestrator()
    matches = orch.search(goal)
    print("Top skills:")
    for m in matches:
        print(f"  {m.name} (score={m.score:.2f}, {m.category}) — {m.description[:80]}")
    print()
    plan = orch.plan(goal, mode=mode)
    if plan.steps:
        print("Plan:")
        for i, s in enumerate(plan.steps, 1):
            risk_icon = {"auto": "  ", "confirm": "⚠️ ", "manual": "✋"}.get(s.risk, "  ")
            print(f"  {risk_icon}{i}. {s.skill_name}: {s.goal}")
            if s.verify:
                print(f"     verify: {s.verify}")
        if mode == "manual":
            print(f"\n  Manual mode — plan generated. Run with --semi or default to execute.")
        else:
            result = orch.execute(plan)
            print(f"\nResult: {'OK' if result['ok'] else 'FAILED'} "
                  f"({result['passed']}/{result['steps']} passed, {result['duration_ms']}ms)")
    else:
        print("No matching skills found")
