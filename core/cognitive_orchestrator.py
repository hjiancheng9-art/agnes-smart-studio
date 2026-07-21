"""Cognitive orchestrator — multi-model deliberation for complex questions.

When a user prompt is complex enough, it's sent to 2-3 models in parallel.
A light comparator model synthesizes the responses into a consensus answer.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import re

logger = logging.getLogger(__name__)

COMPARE_PROMPT = """You are a consensus builder. Below are {n} different AI responses to the same question.
Synthesize them into ONE best answer. If they agree, state the consensus clearly.
If they disagree, present the majority view and note the dissenting opinion.

User question: {question}

Responses:
{responses}

Output format:
CONSENSUS: <one clear answer>
CONFIDENCE: <high/medium/low>
DISSENT: <briefly note any disagreement, or "none">
"""

COMPLEXITY_PATTERN = re.compile(
    r"architecture|design\s+(?:system|pattern|decision)|security\s+(?:audit|review)|"
    r"best\s+(?:practice|approach|way)|trade.?off|pros?.?(?:and|&).?cons|"
    r"migrat(?:e|ion)|scale|performance|optimize|"
    r"recommend|compare|evaluate|analyze",
    re.IGNORECASE,
)


def is_complex(prompt: str) -> bool:
    """Heuristic: does this prompt warrant multi-model deliberation?"""
    return len(prompt) > 40 and bool(COMPLEXITY_PATTERN.search(prompt))


class CognitiveOrchestrator:
    """Parallel multi-model deliberation engine."""

    def __init__(self, client_factory=None) -> None:
        # client_factory: callable returning CruxClient for a given provider id
        self._client_factory = client_factory
        self.vote_count = 0
        self.last_confidence = ""

    def deliberate(self, prompt: str, models: list[str] | None = None) -> dict:
        """Run parallel deliberation and return consensus result.

        Args:
            prompt: the user's question
            models: list of model IDs to consult. Default: derived from router config
                    (DEEP profile candidates, up to 2 text models).

        Returns:
            {"answer": str, "confidence": str, "dissenting": str, "models_used": int}
        """
        if models is None:
            models = self._default_models()

        self.vote_count += 1

        # Phase 1: parallel calls
        responses = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
            futures = {executor.submit(self._call_model, model, prompt): model for model in models}
            for future in concurrent.futures.as_completed(futures, timeout=60):
                model = futures[future]
                try:
                    responses[model] = future.result()
                except Exception as e:
                    logger.debug("model %s failed in deliberation: %s", model, e)

        if len(responses) < 2:
            # Only one model responded — return it directly
            only = next(iter(responses.values())) if responses else prompt
            return {
                "answer": only,
                "confidence": "low",
                "dissenting": "insufficient responses",
                "models_used": len(responses),
            }

        # Phase 2: synthesize with a light comparator
        response_texts = "\n\n---\n\n".join(f"[{m}]: {r[:1000]}" for m, r in responses.items())
        synthesis = self._call_model(
            "deepseek-v4-flash",
            COMPARE_PROMPT.format(n=len(responses), question=prompt[:500], responses=response_texts),
        )

        # Parse synthesis
        answer = synthesis
        confidence = "medium"
        dissenting = "none"
        for line in synthesis.split("\n"):
            low = line.strip()
            if low.upper().startswith("CONSENSUS:"):
                answer = low.split(":", 1)[1].strip()
            elif low.upper().startswith("CONFIDENCE:"):
                confidence = low.split(":", 1)[1].strip().lower()
            elif low.upper().startswith("DISSENT:"):
                dissenting = low.split(":", 1)[1].strip()

        self.last_confidence = confidence
        return {
            "answer": answer,
            "confidence": confidence,
            "dissenting": dissenting,
            "models_used": len(responses),
        }

    def _default_models(self) -> list[str]:
        """Derive deliberation models from router config (DEEP profile candidates).

        Picks the first 2 available text models from the DEEP profile candidates,
        falling back to a hardcoded safe list if config is unavailable.
        """
        try:
            from core.router import TaskProfile, get_profile_candidates

            candidates = get_profile_candidates(TaskProfile.DEEP)
            if candidates:
                # Filter to models whose providers are actually available
                from core.provider import MODEL_REGISTRY, get_provider_manager

                mgr = get_provider_manager()
                state = mgr.state
                available: list[str] = []
                for mid in candidates:
                    info = MODEL_REGISTRY.get(mid)
                    if info is None:
                        continue
                    pid = info.provider_id
                    if state.is_down(pid):
                        continue
                    pdata = mgr.providers.get(pid, {})
                    key = pdata.get("api_key", "") or os.getenv(f"{pid.upper()}_API_KEY", "")
                    auth_required = pdata.get("auth_required", True)
                    if key or not auth_required:
                        available.append(mid)
                if available:
                    return available[:2]
        except (ImportError, OSError) as e:
            logger.debug("router config unavailable for deliberation: %s", e)

        # Safe fallback: DeepSeek family (most capable text models)
        return ["deepseek-v4-pro", "deepseek-v4-flash"]

    def _call_model(self, model: str, prompt: str) -> str:
        """Call a single model and return its text response.

        Uses ProviderManager to locate the correct provider and create a client
        with the proper API key. Falls back gracefully if the provider is unavailable.
        """
        try:
            from core.provider import MODEL_REGISTRY, get_provider_manager

            mgr = get_provider_manager()
            info = MODEL_REGISTRY.get(model)
            if info is not None:
                pid = info.provider_id
                client = mgr.create_client(pid)
                resp = client.chat(
                    model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1024,
                )
                choices = resp.get("choices", [{}])
                return choices[0].get("message", {}).get("content", "") if choices else ""
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("model %s call via ProviderManager failed: %s", model, e)

        # Last-resort fallback: try any provider that lists this model
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            for pid, pdata in mgr.providers.items():
                if model in pdata.get("models", {}).values():
                    client = mgr.create_client(pid)
                    resp = client.chat(
                        model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                        max_tokens=1024,
                    )
                    choices = resp.get("choices", [{}])
                    return choices[0].get("message", {}).get("content", "") if choices else ""
        except (ImportError, OSError, RuntimeError) as e:
            logger.debug("model %s fallback call failed: %s", model, e)

        return ""  # all paths exhausted, return empty
