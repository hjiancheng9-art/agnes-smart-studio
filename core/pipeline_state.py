"""Pipeline state engine — shared state, quality gates, chain presets.

Solves the 4 structural gaps:
1. State passing between chained skills
2. Quality gate with auto-retry feedback loop
3. One-click pipeline loading
4. Asset version tracking across pipeline runs

Usage:
    from core.pipeline_state import PipelineEngine

    # One-click video production
    engine = PipelineEngine(session)
    engine.run("video-production", initial_input="a cyberpunk city at night")

    # Or step-by-step with quality gates
    engine.run_with_qa("world-building", "design a fantasy race")
"""

import json
import time
from pathlib import Path
from typing import Any

__all__ = [
    'PIPELINES', 'PIPELINE_RUNS_DIR', 'PipelineEngine', 'PipelineState', 'ROOT',
]

ROOT = Path(__file__).resolve().parent.parent
PIPELINE_RUNS_DIR = ROOT / "output" / "pipeline_runs"


# ── 10 Pipeline Presets ──

PIPELINES = {
    "video-production": {
        "name": "完整视频制片",
        "skills": ["prompt-director", "storyboard-director", "visual-director",
                   "motion-director", "cinematic-keyframe", "qc-inspector", "delivery-handoff"],
        "output_type": "video",
        "qa_gates": ["qc-inspector"],
    },
    "comfyui-studio": {
        "name": "ComfyUI 专业站",
        "skills": ["comfyui-bridge", "creative-engine", "model-routing", "master-quality"],
        "output_type": "image/video",
        "qa_gates": ["master-quality"],
    },
    "combat-action": {
        "name": "战斗动作管线",
        "skills": ["gaming-action-engine", "i2v-motion-rules", "negative-prompt-rules", "motion-director"],
        "output_type": "video",
        "qa_gates": [],
    },
    "creative-image": {
        "name": "高创意出图",
        "skills": ["creative-leap-pro", "cinematic-master", "prompt-engineering",
                   "model-routing", "negative-prompt-rules"],
        "output_type": "image",
        "qa_gates": [],
    },
    "world-building": {
        "name": "世界观资产",
        "skills": ["world-building-engine", "ip-adaptation-guard", "actor-craft",
                   "asset-manager", "visual-director"],
        "output_type": "assets",
        "qa_gates": [],
    },
    "script-to-audio": {
        "name": "剧本到配音",
        "skills": ["script-writer", "story-copywriter", "audio-director"],
        "output_type": "audio",
        "qa_gates": [],
    },
    "novel-publishing": {
        "name": "小说出版",
        "skills": ["novel-writer", "copywriting-master", "publishing-packager"],
        "output_type": "document",
        "qa_gates": [],
    },
    "comic-storyboard": {
        "name": "漫画分镜",
        "skills": ["comic-drama-writer", "copywriting-master", "storyboard-director", "visual-director"],
        "output_type": "storyboard",
        "qa_gates": [],
    },
    "self-evolve": {
        "name": "自进化修复",
        "skills": ["self-audit", "self-evolution", "debug-master", "code-review-autofix"],
        "output_type": "code",
        "qa_gates": ["code-review-autofix", "self-audit"],
    },
    "api-development": {
        "name": "API 开发",
        "skills": ["api-designer", "python-expert", "shell-master"],
        "output_type": "code",
        "qa_gates": [],
    },
}


class PipelineState:
    """Shared state passed between chained skills. Skills read/write via this object."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.data: dict[str, Any] = {}
        self.step_results: dict[str, str] = {}
        self.assets: list[dict] = []
        self.qa_log: list[dict] = []
        self.start_time = time.time()
        self.current_step: str = ""

    def set(self, key: str, value: Any):
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def record_step(self, skill: str, result: str):
        self.step_results[skill] = result[:500]
        self.current_step = skill

    def add_asset(self, path: str, step: str, desc: str = ""):
        self.assets.append({
            "path": path, "step": step, "desc": desc,
            "run_id": self.run_id, "ts": time.time(),
        })

    def log_qa(self, step: str, passed: bool, note: str = ""):
        self.qa_log.append({
            "step": step, "passed": passed, "note": note,
            "ts": time.time(),
        })

    def context_for_next(self) -> str:
        """Build context string for the next skill in the chain."""
        parts = []
        if self.step_results:
            last = list(self.step_results.keys())[-1]
            parts.append(f"[Previous step: {last}]")
            parts.append(self.step_results[last][:300])
        if self.data.get("constraints"):
            parts.append(f"[Constraints: {self.data['constraints']}]")
        if self.assets:
            parts.append(f"[Assets ({len(self.assets)}): {', '.join(a['path'] for a in self.assets[-3:])}]")
        return "\n".join(parts)


class PipelineEngine:
    """Orchestrates multi-skill pipeline runs with state, QA gates, and asset tracking."""

    def __init__(self, cli_instance=None) -> None:
        self.cli = cli_instance
        self.state: PipelineState | None = None
        self._skill_mgr = None

    def _get_skill_mgr(self):
        if not self._skill_mgr:
            from core.skills import get_manager
            self._skill_mgr = get_manager()
            self._skill_mgr.discover()
        return self._skill_mgr

    def list_pipelines(self) -> list[dict]:
        return [{"id": pid, "name": p["name"],
                 "skills": len(p["skills"]),
                 "output": p["output_type"]}
                for pid, p in PIPELINES.items()]

    def run(self, pipeline_id: str, initial_input: str,
            on_step=None) -> PipelineState:
        """Run a full pipeline. Returns final state with all results."""
        if pipeline_id not in PIPELINES:
            raise ValueError(f"Unknown pipeline: {pipeline_id}. Options: {list(PIPELINES.keys())}")

        pipe = PIPELINES[pipeline_id]
        run_id = f"{pipeline_id}_{int(time.time())}"
        self.state = PipelineState(run_id)
        self.state.set("initial_input", initial_input)
        self.state.set("pipeline", pipeline_id)

        mgr = self._get_skill_mgr()
        context = initial_input
        max_retries = 2

        for skill_name in pipe["skills"]:
            self.state.current_step = skill_name
            if on_step:
                on_step(skill_name, "loading")

            # Load skill
            result = mgr.load(skill_name)
            if not result:
                self.state.record_step(skill_name, f"[FAIL] Skill not found: {skill_name}")
                continue

            # Build prompt with previous state context
            state_context = self.state.context_for_next()
            full_prompt = f"{context}\n\n{state_context}" if state_context else context

            # Execute (via CLI chat session if available)
            response = self._execute_skill(skill_name, full_prompt)
            self.state.record_step(skill_name, response)

            if on_step:
                on_step(skill_name, "done")

            # QA gate check
            if skill_name in pipe.get("qa_gates", []):
                for attempt in range(max_retries + 1):
                    qa_passed = self._check_quality(skill_name, response)
                    self.state.log_qa(skill_name, qa_passed,
                                      f"attempt {attempt+1}" if attempt > 0 else "first pass")
                    if qa_passed:
                        break
                    elif attempt < max_retries:
                        # Feed QA feedback back as context and retry previous step
                        prev_step = self._prev_step(pipe["skills"], skill_name)
                        if prev_step:
                            context = f"[QA feedback: {self.state.qa_log[-1]['note']}] Retry: {context}"
                            mgr.load(prev_step)
                            response = self._execute_skill(prev_step, context)
                            self.state.record_step(prev_step + "_retry", response)

            # Next step's input is this step's output
            context = response

        # Track output assets
        output_dir = PIPELINE_RUNS_DIR / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "state.json").write_text(
            json.dumps({
                "run_id": run_id,
                "pipeline": pipeline_id,
                "step_results": self.state.step_results,
                "assets": self.state.assets,
                "qa_log": self.state.qa_log,
                "elapsed": time.time() - self.state.start_time,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return self.state

    def _execute_skill(self, skill_name: str, prompt: str) -> str:
        """Execute a loaded skill by sending prompt through the chat session."""
        if self.cli and hasattr(self.cli, '_chat_session'):
            session = self.cli._chat_session
            responses = list(session.send_stream(prompt))
            texts = [p for kind, p in responses if kind == "text"]
            return "".join(texts) if texts else "(no response)"
        # Fallback: return the prompt as-is for testing
        return f"[Skill {skill_name} loaded. Awaiting input...]"

    def _prev_step(self, skills: list[str], current: str) -> str | None:
        """Get the step before current in the skills list."""
        try:
            idx = skills.index(current)
            return skills[idx - 1] if idx > 0 else None
        except ValueError:
            return None

    def _check_quality(self, skill_name: str, output: str) -> bool:
        """Simple QA heuristic: check output is non-empty and not an error."""
        if not output or output.startswith("[FAIL]") or output.startswith("[错误]"):
            assert self.state is not None  # guaranteed by execute()
            self.state.log_qa(skill_name, False, "empty or error output")
            return False
        return True
