"""Cognitive orchestrator — multi-model deliberation for complex questions.

When a user prompt is complex enough, it's sent to 2-3 models in parallel.
A light comparator model synthesizes the responses into a consensus answer.
"""

from __future__ import annotations

import concurrent.futures
import logging
import re

logger = logging.getLogger("crux.cognitive")

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
            models: list of model IDs to consult. Default: [deepseek-v4-pro, deepseek-v4-flash]

        Returns:
            {"answer": str, "confidence": str, "dissenting": str, "models_used": int}
        """
        if models is None:
            models = ["deepseek-v4-pro", "deepseek-v4-flash"]

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

    def _call_model(self, model: str, prompt: str) -> str:
        """Call a single model and return its text response."""
        if self._client_factory:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            # Find which provider has this model
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
            # Fallback: try with default client
            from core.client import CruxClient

            resp = CruxClient().chat(
                model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )
            choices = resp.get("choices", [{}])
            return choices[0].get("message", {}).get("content", "") if choices else ""

        return prompt  # no client factory, identity passthrough
