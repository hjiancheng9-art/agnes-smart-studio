# core/benchmark/tasks.py
"""Real-world benchmark tasks for measuring CRUX capability.

Each task is a self-contained challenge with:
- A user prompt (what the user asks)
- Expected behaviors to check
- Tools likely needed
- Scoring criteria
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class BenchmarkTask:
    """A single benchmark task."""

    id: str
    category: str  # "code_gen", "debug", "refactor", "qa", "tool_use", "multi_step"
    prompt: str
    difficulty: str  # "easy", "medium", "hard"
    expected_tools: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)
    forbidden_keywords: list[str] = field(default_factory=list)
    min_response_length: int = 50
    max_tool_calls: int = 10
    timeout_seconds: int = 60
    tags: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "prompt": self.prompt,
            "difficulty": self.difficulty,
            "expected_tools": self.expected_tools,
            "expected_keywords": self.expected_keywords,
            "forbidden_keywords": self.forbidden_keywords,
            "min_response_length": self.min_response_length,
            "max_tool_calls": self.max_tool_calls,
            "timeout_seconds": self.timeout_seconds,
            "tags": self.tags,
            "description": self.description,
        }


@dataclass
class TaskSuite:
    """A collection of benchmark tasks organized by category."""

    name: str = "default"
    tasks: list[BenchmarkTask] = field(default_factory=list)
    description: str = ""

    def by_category(self, category: str) -> list[BenchmarkTask]:
        return [t for t in self.tasks if t.category == category]

    def by_difficulty(self, difficulty: str) -> list[BenchmarkTask]:
        return [t for t in self.tasks if t.difficulty == difficulty]

    @property
    def total(self) -> int:
        return len(self.tasks)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "total": self.total,
            "tasks": [t.to_dict() for t in self.tasks],
        }


def get_default_suite() -> TaskSuite:
    """Return the default benchmark task suite.

    Contains tasks across 5 categories at 3 difficulty levels.
    """
    return TaskSuite(
        name="CRUX Core Capabilities",
        description="Measures CRUX's ability to handle real-world coding tasks",
        tasks=[
            # ── Code Generation ──
            BenchmarkTask(
                id="code_gen_simple",
                category="code_gen",
                difficulty="easy",
                prompt="Write a Python function to check if a string is a palindrome, ignoring spaces and case.",
                expected_keywords=["def ", "palindrome", "return"],
                forbidden_keywords=["input("],
                min_response_length=80,
                tags=["python", "function"],
            ),
            BenchmarkTask(
                id="code_gen_class",
                category="code_gen",
                difficulty="medium",
                prompt="Create a Python class called `Task` with fields: id (str), title (str), done (bool). Add a method `mark_done()` and a `__str__` method.",
                expected_keywords=["class Task", "def mark_done", "def __str__"],
                min_response_length=150,
                tags=["python", "oop"],
            ),
            BenchmarkTask(
                id="code_gen_sort",
                category="code_gen",
                difficulty="medium",
                prompt="Write a function that takes a list of dictionaries and sorts them by a specified key. Handle missing keys gracefully.",
                expected_keywords=["def ", "sorted(", "key="],
                expected_tools=["write_file"],
                min_response_length=100,
                tags=["python", "sorting"],
            ),
            # ── Debug ──
            BenchmarkTask(
                id="debug_syntax",
                category="debug",
                difficulty="easy",
                prompt="This code has a bug: `def add(a, b): return a + b; print(add(5))`. Fix it.",
                expected_keywords=["def add", "return"],
                min_response_length=40,
                tags=["debug", "python"],
            ),
            BenchmarkTask(
                id="debug_logic",
                category="debug",
                difficulty="medium",
                prompt="The function below should return the factorial of n, but it returns 0 for all inputs. Find and fix the bug.\n\n```python\ndef factorial(n):\n    result = 0\n    for i in range(1, n):\n        result *= i\n    return result\n```",
                expected_keywords=["factorial", "result = 1", "range(1, n+1)"],
                min_response_length=100,
                tags=["debug", "python", "math"],
            ),
            BenchmarkTask(
                id="debug_index_error",
                category="debug",
                difficulty="hard",
                prompt="This code sometimes crashes with IndexError. Fix it robustly.\n\n```python\ndef get_item(lst, index):\n    return lst[index]\n```",
                expected_keywords=["if", "len(", "IndexError", "try", "except"],
                min_response_length=80,
                tags=["debug", "python", "error-handling"],
            ),
            # ── Code Reading & QA ──
            BenchmarkTask(
                id="qa_explain",
                category="qa",
                difficulty="easy",
                prompt="What does the `git stash` command do?",
                expected_keywords=["save", "temporary", "working directory"],
                min_response_length=60,
                tags=["git", "explain"],
            ),
            BenchmarkTask(
                id="qa_time_complexity",
                category="qa",
                difficulty="medium",
                prompt="What is the time complexity of quicksort in the average case? Explain briefly.",
                expected_keywords=["O(n log n)", "average"],
                min_response_length=60,
                tags=["algorithm", "complexity"],
            ),
            BenchmarkTask(
                id="qa_diff_vs_patch",
                category="qa",
                difficulty="medium",
                prompt="What's the difference between `git diff` and `git patch`? When would you use each?",
                expected_keywords=["diff", "patch", "apply"],
                min_response_length=80,
                tags=["git", "explain"],
            ),
            # ── Tool Use ──
            BenchmarkTask(
                id="tool_read_write",
                category="tool_use",
                difficulty="easy",
                prompt="Read the file 'hello.txt' and tell me what it contains.",
                expected_tools=["read_file"],
                expected_keywords=["hello.txt"],
                min_response_length=20,
                tags=["tool", "read"],
            ),
            BenchmarkTask(
                id="tool_search_code",
                category="tool_use",
                difficulty="medium",
                prompt="Find all Python files in the project that define a class called 'User' and show me their import statements.",
                expected_tools=["search_files", "read_file"],
                expected_keywords=["class User", "import"],
                max_tool_calls=15,
                tags=["tool", "search"],
            ),
            BenchmarkTask(
                id="tool_run_test",
                category="tool_use",
                difficulty="hard",
                prompt="Find the test file for 'auth.py', run it, and report the results. If it fails, suggest a fix.",
                expected_tools=["search_files", "run_bash", "read_file"],
                expected_keywords=["test", "auth", "pytest"],
                max_tool_calls=20,
                tags=["tool", "test", "debug"],
            ),
            # ── Multi-step ──
            BenchmarkTask(
                id="multi_refactor_variable",
                category="multi_step",
                difficulty="medium",
                prompt="Rename all occurrences of the variable `old_name` to `new_name` in 'example.py'. First read the file, then make the change, then verify.",
                expected_tools=["read_file", "write_file", "run_bash"],
                expected_keywords=["old_name", "new_name"],
                max_tool_calls=8,
                tags=["refactor", "rename"],
            ),
            BenchmarkTask(
                id="multi_create_and_test",
                category="multi_step",
                difficulty="hard",
                prompt="Create a Python module called 'calculator.py' with add, subtract, multiply, divide functions. Then create a test file 'test_calculator.py' with pytest tests for all four functions. Run the tests and report results.",
                expected_tools=["write_file", "run_bash"],
                expected_keywords=["def add", "def test_add", "pytest"],
                max_tool_calls=15,
                min_response_length=200,
                tags=["create", "test", "multi-step"],
            ),
            # ── Edge Cases ──
            BenchmarkTask(
                id="edge_empty_response",
                category="debug",
                difficulty="easy",
                prompt="Why is my function returning None?\n\n```python\ndef add(a, b):\n    result = a + b\n```",
                expected_keywords=["return", "missing"],
                min_response_length=50,
                tags=["debug", "python"],
            ),
        ],
    )


def load_suite(path: str) -> TaskSuite:
    """Load a task suite from a JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    suite = TaskSuite(name=data.get("name", "custom"), description=data.get("description", ""))
    for td in data.get("tasks", []):
        suite.tasks.append(BenchmarkTask(**td))
    return suite


def save_suite(suite: TaskSuite, path: str):
    """Save a task suite to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(suite.to_dict(), f, indent=2, ensure_ascii=False)
