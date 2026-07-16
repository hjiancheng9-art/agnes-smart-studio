"""CRUX Showrunner — Creative pipeline director.

CRUX is the Showrunner: goal -> plan -> skill steps -> generation -> delivery.

Pipeline templates:
  - short_video:    brainstorm -> script -> prompts -> images -> animate -> review -> deliver
  - concept_art:    explore -> prompts -> generate -> curate -> deliver
  - novel_chapter:  expand -> write -> illustrate -> polish -> export

Sources (with optional fallback):
  AGNES (API) | COMFYUI (local) | EXTERNAL (web) | API | CLI
"""

import asyncio
import contextlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

logger = logging.getLogger("crux.showrunner")


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════


class StepKind(Enum):
    THINK = "think"
    PROMPT = "prompt"
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    REVIEW = "review"
    DELIVER = "deliver"
    CUSTOM = "custom"


class SourceKind(Enum):
    AGNES = "crux"
    EXTERNAL = "external"
    API = "api"
    CLI = "cli"


# ═══════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════


@dataclass
class StepResult:
    step_name: str
    kind: StepKind
    source: SourceKind
    success: bool = False
    output: dict | str | None = None
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0
    retries: int = 0


@dataclass
class PipelineRun:
    goal: str
    steps: list[StepResult] = field(default_factory=list)
    started_at: float = 0
    finished_at: float = 0
    status: str = "pending"


# ═══════════════════════════════════════════════════════════════════
# Pipeline Templates
# ═══════════════════════════════════════════════════════════════════

__all__ = [
    "ROOT",
    "PipelineRun",
    "PipelineTemplates",
    "Showrunner",
    "SourceKind",
    "StepKind",
    "StepResult",
    "create_showrunner",
    "list_pipeline_templates",
]


class PipelineTemplates:
    """Predefined pipeline templates for common creative tasks."""

    @staticmethod
    def short_video(topic):
        """短视频: 构思 → 脚本 → 提示词 → 关键帧 → 动画 → 质检 → 交付。"""
        return [
            {"step": "brainstorm", "kind": StepKind.THINK, "desc": f"Brainstorm: {topic}", "source": SourceKind.AGNES},
            {"step": "script", "kind": StepKind.TEXT, "desc": "Write 20-30s video script", "source": SourceKind.AGNES},
            {"step": "prompts", "kind": StepKind.PROMPT, "desc": "Extract visual prompts", "source": SourceKind.AGNES},
            {
                "step": "images",
                "kind": StepKind.IMAGE,
                "desc": "Generate keyframes",
                "source": SourceKind.COMFYUI,
                "fallback": SourceKind.EXTERNAL,
            },
            {
                "step": "animate",
                "kind": StepKind.VIDEO,
                "desc": "Image-to-video",
                "source": SourceKind.COMFYUI,
                "fallback": SourceKind.AGNES,
            },
            {"step": "review", "kind": StepKind.REVIEW, "desc": "Quality check", "source": SourceKind.AGNES},
            {"step": "deliver", "kind": StepKind.DELIVER, "desc": "Output video", "source": SourceKind.CLI},
        ]

    @staticmethod
    def concept_art(concept):
        """概念图: 探索 → 提示词 → 生成 → 筛选 → 交付。"""
        return [
            {"step": "explore", "kind": StepKind.THINK, "desc": f"Explore: {concept}", "source": SourceKind.AGNES},
            {"step": "prompts", "kind": StepKind.PROMPT, "desc": "Multi-style prompts", "source": SourceKind.AGNES},
            {
                "step": "generate",
                "kind": StepKind.IMAGE,
                "desc": "Generate images",
                "source": SourceKind.COMFYUI,
                "fallback": SourceKind.EXTERNAL,
            },
            {"step": "curate", "kind": StepKind.REVIEW, "desc": "Curate best", "source": SourceKind.AGNES},
            {"step": "deliver", "kind": StepKind.DELIVER, "desc": "Output collection", "source": SourceKind.CLI},
        ]

    @staticmethod
    def novel_chapter(outline):
        """小说章节: 扩写 → 写作 → 插图 → 润色 → 导出。"""
        return [
            {"step": "expand", "kind": StepKind.THINK, "desc": f"Expand: {outline}", "source": SourceKind.AGNES},
            {"step": "write", "kind": StepKind.TEXT, "desc": "Write chapter", "source": SourceKind.AGNES},
            {
                "step": "illustrate",
                "kind": StepKind.IMAGE,
                "desc": "Create illustrations",
                "source": SourceKind.COMFYUI,
                "fallback": SourceKind.EXTERNAL,
            },
            {"step": "polish", "kind": StepKind.REVIEW, "desc": "Polish text", "source": SourceKind.AGNES},
            {"step": "deliver", "kind": StepKind.DELIVER, "desc": "Export EPUB/PDF", "source": SourceKind.CLI},
        ]

    @staticmethod
    def custom(goal, specs):
        """从用户提供的 spec 列表构建自定义流水线。"""
        km = {
            "think": StepKind.THINK,
            "prompt": StepKind.PROMPT,
            "text": StepKind.TEXT,
            "image": StepKind.IMAGE,
            "video": StepKind.VIDEO,
            "audio": StepKind.AUDIO,
            "review": StepKind.REVIEW,
            "deliver": StepKind.DELIVER,
        }
        sm = {
            "crux": SourceKind.AGNES,
            "external": SourceKind.EXTERNAL,
            "api": SourceKind.API,
            "cli": SourceKind.CLI,
        }
        result = []
        for s in specs:
            item = {
                "step": s.get("name", "step"),
                "kind": km.get(s.get("kind", ""), StepKind.CUSTOM),
                "desc": s.get("desc", ""),
                "source": sm.get(s.get("source", ""), SourceKind.AGNES),
            }
            if "fallback" in s:
                item["fallback"] = sm.get(s["fallback"])
            result.append(item)
        return result


# ═══════════════════════════════════════════════════════════════════
# Showrunner
# ═══════════════════════════════════════════════════════════════════


class Showrunner:
    """CRUX creative pipeline director.

    Orchestrates a multi-step creative pipeline with retry + fallback logic.
    Each step dispatches to a source (CRUX API / ComfyUI / External / CLI).
    """

    def __init__(self, client=None, brain=None, ext_gen=None) -> None:
        self.client = client
        self.brain = brain
        self.ext_gen = ext_gen
        self._pipeline = None
        self._context = {}
        self._on_step = None

    def on_step(self, cb):
        """Register a step progress callback: cb(name, status)."""
        self._on_step = cb

    def _notify(self, name, status):
        if self._on_step:
            with contextlib.suppress(TypeError, ValueError, RuntimeError):
                self._on_step(name, status)

    # ── Planning ──────────────────────────────────────────

    def plan(self, goal):
        """根据目标关键词自动选择流水线模板。"""
        g = goal.lower()
        if any(k in g for k in ["video", "animation", "short", "clip", "reel", "tiktok"]):
            return PipelineTemplates.short_video(goal)
        if any(k in g for k in ["concept", "illustration", "character", "scene", "mood", "style", "art"]):
            return PipelineTemplates.concept_art(goal)
        if any(k in g for k in ["novel", "chapter", "story", "script", "write"]):
            return PipelineTemplates.novel_chapter(goal)
        # 默认通用流水线
        return [
            {"step": "think", "kind": StepKind.THINK, "desc": f"Analyze: {goal}", "source": SourceKind.AGNES},
            {"step": "create", "kind": StepKind.TEXT, "desc": "Generate content", "source": SourceKind.AGNES},
            {
                "step": "visualize",
                "kind": StepKind.IMAGE,
                "desc": "Generate visuals",
                "source": SourceKind.COMFYUI,
                "fallback": SourceKind.EXTERNAL,
            },
            {"step": "deliver", "kind": StepKind.DELIVER, "desc": "Deliver", "source": SourceKind.CLI},
        ]

    # ── Execution ─────────────────────────────────────────

    async def run(self, goal, pipeline=None, max_retries=2):
        """执行完整流水线，返回 PipelineRun。"""
        if pipeline is None:
            pipeline = self.plan(goal)

        rec = PipelineRun(goal=goal, started_at=time.time())
        self._pipeline = rec
        self._context = {"goal": goal}

        for i, spec in enumerate(pipeline):
            name = spec.get("step", f"step_{i}")
            kind = spec.get("kind", StepKind.CUSTOM)
            src = spec.get("source", SourceKind.AGNES)
            fb = spec.get("fallback")
            desc = spec.get("desc", "")
            # 步骤级 max_retries 优先于流水线默认值
            step_retries = spec.get("max_retries", max_retries)

            self._notify(name, "running")
            res = await self._exec(name, kind, src, desc, step_retries, fb)
            rec.steps.append(res)
            self._notify(name, "done" if res.success else "failed")

            if not res.success and res.error:
                logger.error("[Showrunner] %s: %s", name, res.error)

        rec.finished_at = time.time()
        rec.status = "completed" if all(s.success for s in rec.steps) else "partial"
        return rec

    async def _exec(self, name, kind, src, desc, max_retries, fallback):
        """执行单个步骤，带重试和 fallback 源切换。"""
        t0 = time.time()
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                out = await self._dispatch(name, kind, src, desc)
                return StepResult(
                    step_name=name,
                    kind=kind,
                    source=src,
                    success=True,
                    output=out,
                    duration_ms=(time.time() - t0) * 1000,
                    retries=attempt,
                )
            except (RuntimeError, OSError, KeyError) as e:
                last_error = str(e)
            if attempt < max_retries:
                await asyncio.sleep(1.0 * (attempt + 1))

        # 主源全部失败 → 尝试 fallback 源
        if fallback and fallback != src:
            try:
                out = await self._dispatch(name, kind, fallback, desc)
                return StepResult(
                    step_name=name,
                    kind=kind,
                    source=fallback,
                    success=True,
                    output=out,
                    duration_ms=(time.time() - t0) * 1000,
                    retries=max_retries + 1,
                )
            except (RuntimeError, OSError, KeyError) as e:
                last_error = str(e)

        return StepResult(
            step_name=name,
            kind=kind,
            source=src,
            success=False,
            error=last_error,
            duration_ms=(time.time() - t0) * 1000,
        )

    async def _dispatch(self, name, kind, src, desc):
        """按步骤类型路由到对应的生成方法。"""
        if kind == StepKind.THINK:
            return await self._think(desc)
        if kind == StepKind.PROMPT:
            return await self._gen_prompt(desc)
        if kind == StepKind.TEXT:
            return await self._gen_text(desc)
        if kind == StepKind.IMAGE:
            return await self._gen_image(desc, src)
        if kind == StepKind.VIDEO:
            return await self._gen_video(desc, src)
        if kind == StepKind.REVIEW:
            return await self._review(desc)
        if kind == StepKind.DELIVER:
            return await self._deliver(desc)
        return await self._think(desc)

    # ── Text generation steps ─────────────────────────────

    async def _think(self, desc):
        if not self.client:
            return {"thought": desc}
        sys_prompt = "You are the CRUX Showrunner. Plan creative pipelines concisely."
        try:
            r = self.client.chat(
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": desc}],
                temperature=0.7,
                max_tokens=1000,
            )
            return {"thought": r["choices"][0]["message"]["content"]}
        except (RuntimeError, OSError, KeyError):
            return {"thought": desc}

    async def _gen_prompt(self, desc):
        if not self.client:
            return {"prompt": desc}
        sys_prompt = "You are a pro AI prompt engineer. Output the best English prompt."
        try:
            r = self.client.chat(
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": desc}],
                temperature=0.8,
                max_tokens=500,
            )
            content = r["choices"][0]["message"]["content"].strip()
            self._context["last_prompt"] = content
            return {"prompt": content}
        except (RuntimeError, OSError, KeyError):
            return {"prompt": desc}

    async def _gen_text(self, desc):
        if not self.client:
            return {"text": desc}
        sys_prompt = "You are a professional creative writer."
        try:
            r = self.client.chat(
                messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": desc}],
                temperature=0.9,
                max_tokens=2000,
            )
            content = r["choices"][0]["message"]["content"]
            self._context["last_text"] = content
            return {"text": content}
        except (RuntimeError, OSError, KeyError):
            return {"text": desc}

    # ── Image generation steps ────────────────────────────

    async def _gen_image(self, desc, src):
        p = self._context.get("last_prompt", desc)
        if src == SourceKind.EXTERNAL:
            return await self._ext_img(p)
        if src == SourceKind.AGNES:
            return await self._agnes_img(p)
        return await self._agnes_img(p)

    async def _agnes_img(self, prompt):
        if not self.client:
            raise RuntimeError("No client")
        from engines.text_to_image import TextToImageEngine

        engine = TextToImageEngine(self.client)
        r = await asyncio.to_thread(engine.generate, prompt)
        # 落盘路径作为产出图片；URL 回退到 local_path
        imgs = [r.get("local_path") or r.get("url", "")]
        imgs = [i for i in imgs if i]
        self._context["last_images"] = imgs
        return {"crux": r, "source": "crux"}

    async def _ext_img(self, prompt):
        if self.ext_gen:
            r = await self.ext_gen.generate_image(prompt)
            return {"external": r, "source": "external"}
        raise RuntimeError("No external generator")

    # ── Video generation steps ────────────────────────────

    async def _gen_video(self, desc, src):
        p = self._context.get("last_prompt", desc)
        imgs = self._context.get("last_images", [])
        if src == SourceKind.EXTERNAL:
            return await self._ext_vid(p, imgs)
        if src == SourceKind.AGNES:
            return await self._agnes_vid(p, imgs)
        return await self._agnes_vid(p, imgs)

    async def _agnes_vid(self, prompt, imgs):
        if not self.client:
            raise RuntimeError("No client")
        from engines.video import VideoEngine

        engine = VideoEngine(self.client)
        # 有首帧图 → 图生视频；否则文生视频
        if imgs:
            first = imgs[0]
            r = await asyncio.to_thread(lambda: engine.image_to_video(prompt=prompt, image_url=first, timeout=120.0))
        else:
            r = await asyncio.to_thread(lambda: engine.text_to_video(prompt=prompt, timeout=120.0))
        return {"crux": r, "source": "crux"}

    async def _ext_vid(self, prompt, imgs):
        if self.ext_gen:
            r = await self.ext_gen.generate_video(prompt, imgs)
            return {"external": r, "source": "external"}
        raise RuntimeError("No external generator")

    # ── Review & Deliver ──────────────────────────────────

    async def _review(self, desc):
        if not self.client:
            return {"review": "ok"}
        sys_prompt = "You are a creative content quality reviewer."
        ctx = json.dumps(
            {
                "goal": self._context.get("goal", ""),
                "text": str(self._context.get("last_text", ""))[:200],
            }
        )
        try:
            r = self.client.chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"Review: {desc} | Context: {ctx}"},
                ],
                temperature=0.5,
                max_tokens=500,
            )
            return {"review": r["choices"][0]["message"]["content"]}
        except (RuntimeError, OSError, KeyError):
            return {"review": "ok"}

    async def _deliver(self, desc):
        artifacts = []
        out_dir = ROOT / "output"
        if out_dir.exists():
            for p in sorted(out_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if p.suffix.lower() in (".png", ".jpg", ".mp4", ".webm", ".gif"):
                    artifacts.append(str(p))
        return {
            "delivered": True,
            "artifacts": artifacts[:10],
            "output_dir": str(out_dir),
            "summary": desc,
        }


# ═══════════════════════════════════════════════════════════════════
# Factory & helpers
# ═══════════════════════════════════════════════════════════════════


def create_showrunner(client=None, brain=None, ext_gen=None):
    """创建一个 Showrunner 实例。"""
    return Showrunner(client=client, brain=brain, ext_gen=ext_gen)


def list_pipeline_templates():
    """返回所有可用流水线模板的说明。"""
    return {
        "short_video": "Short video: brainstorm->script->prompts->images->animate->review->deliver",
        "concept_art": "Concept art: explore->prompts->generate->curate->deliver",
        "novel_chapter": "Novel chapter: expand->write->illustrate->polish->export",
    }

    @property
    def COMFYUI_AGENT_URL(self) -> str:
        """ComfyUI agent URL — resolved per-call to support runtime env changes."""
        return os.environ.get("COMFYUI_AGENT_URL", "http://127.0.0.1:5000").strip().rstrip("/")

    # ═══════════════════════════════════════════════
    #  ComfyUI Agent 桥接 (V4 集成)
    # ═══════════════════════════════════════════════

    async def _comfyui_bridge(self, prompt: str, mode: str = "image", style: str = "cinematic") -> dict:
        """通过 ComfyUI Agent Orchestrator 生成（异步，不阻塞事件循环）"""
        import asyncio

        def _post_sync():
            import requests

            resp = requests.post(
                f"{self.COMFYUI_AGENT_URL}/produce/quick",
                json={"prompt": prompt, "style": style},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            data = await asyncio.to_thread(_post_sync)
            if data.get("success"):
                return {
                    "source": "comfyui",
                    "outputs": data.get("outputs", []),
                    "mode": mode,
                }
            return {"source": "comfyui", "error": data.get("error", "unknown"), "mode": mode}
        except Exception as e:
            return {"source": "comfyui", "error": str(e), "fallback": "direct"}

    async def produce_shot_plan(self, plan: dict) -> dict:
        """提交完整 ShotPlan 到 ComfyUI Agent（异步，不阻塞事件循环）"""
        import asyncio

        def _post_sync():
            import requests

            resp = requests.post(
                f"{self.COMFYUI_AGENT_URL}/produce",
                json=plan,
                timeout=300,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            return await asyncio.to_thread(_post_sync)
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def design_character(self, name: str, description: str = "", archetype: str = "") -> dict:
        """通过 Actor-craft 设计角色（异步，不阻塞事件循环）"""
        import asyncio

        def _post_sync():
            import requests

            resp = requests.post(
                f"{self.COMFYUI_AGENT_URL}/actor/design",
                json={"name": name, "description": description, "archetype": archetype},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            return await asyncio.to_thread(_post_sync)
        except Exception as e:
            return {"success": False, "error": str(e)}
