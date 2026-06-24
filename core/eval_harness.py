"""Evaluation harness -- benchmark suite for agent quality measurement.

Predefined benchmark tasks that test core agent capabilities:
code_search, bug_fix, refactor, understand, generate.

Each task has: goal, expected_outcome, scoring function.
"""

import time
from pathlib import Path

__all__ = ['BENCHMARKS', 'EvalEngine', 'ROOT', 'run_evals']

ROOT = Path(__file__).resolve().parent.parent


BENCHMARKS = [
    {
        "id": "bench_find_config",
        "name": "Find configuration value",
        "goal": "Find where the API base URL is configured",
        "category": "code_search",
        "expected_keywords": ["base_url", "models.json", "SETTINGS"],
        "weight": 1.0,
    },
    {
        "id": "bench_syntax_check",
        "name": "Syntax check all Python files",
        "goal": "Verify all Python files have valid syntax",
        "category": "code_quality",
        "expected_keywords": ["OK", "passed", "no errors"],
        "weight": 1.0,
    },
    {
        "id": "bench_read_docs",
        "name": "Read project documentation",
        "goal": "Find and summarize the project architecture",
        "category": "understand",
        "expected_keywords": ["architecture", "core", "engines", "UI"],
        "weight": 1.0,
    },
    {
        "id": "bench_tool_list",
        "name": "List available tools",
        "goal": "List all available agent tools",
        "category": "code_search",
        "expected_keywords": ["read_file", "write_file", "search_files"],
        "weight": 0.5,
    },
    {
        "id": "bench_env_check",
        "name": "Environment health check",
        "goal": "Run environment health check and report status",
        "category": "code_quality",
        "expected_keywords": ["Python", "encoding", "OK"],
        "weight": 1.0,
    },
]


class EvalEngine:
    """Run benchmarks and score agent performance."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ROOT
        self.results: list[dict] = []

    def run_benchmark(self, benchmark: dict, tool_executor) -> dict:
        """Run a single benchmark task."""
        result = {
            "id": benchmark["id"],
            "name": benchmark["name"],
            "category": benchmark["category"],
            "started": time.time(),
            "status": "pending",
            "score": 0.0,
            "output": "",
        }
        try:
            # Execute via env_check and search_files as proxies for agent tools
            if benchmark["category"] == "code_search":
                output = tool_executor("search_files",
                                       {"pattern": benchmark["goal"].split()[0]})
            elif benchmark["category"] == "code_quality":
                output = tool_executor("env_check", {})
            else:
                output = tool_executor("read_file",
                                       {"path": "README.md"})
            result["output"] = output[:500]

            # Score: check if expected keywords found
            keywords_found = sum(
                1 for kw in benchmark["expected_keywords"]
                if kw.lower() in output.lower()
            )
            result["score"] = round(
                keywords_found / max(len(benchmark["expected_keywords"]), 1)
                * benchmark["weight"], 2
            )
            result["status"] = "pass" if result["score"] >= 0.5 else "fail"
        except (OSError, ValueError, RuntimeError) as e:
            result["status"] = "error"
            result["output"] = str(e)[:200]
        result["elapsed"] = round(time.time() - result["started"], 2)
        return result

    def run_all(self, tool_executor=None) -> dict:
        """Run all benchmarks and return report."""
        if tool_executor is None:
            from core.tools import get_registry
            reg = get_registry()
            tool_executor = reg.execute
        self.results = []
        for bench in BENCHMARKS:
            result = self.run_benchmark(bench, tool_executor)
            self.results.append(result)
        passed = sum(1 for r in self.results if r["status"] == "pass")
        total_weight = sum(b["weight"] for b in BENCHMARKS)
        total_score = sum(r["score"] for r in self.results)
        return {
            "suite": "CRUX Core Benchmarks",
            "total": len(self.results),
            "passed": passed,
            "failed": len(self.results) - passed,
            "score": round(total_score / max(total_weight, 1) * 100, 1),
            "results": self.results,
        }


def run_evals() -> dict:
    return EvalEngine().run_all()
