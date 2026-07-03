"""Automated test generation and execution loop for AI agent.

Provides:
- TestGenerator: analyze source files and generate pytest test code via LLM
- TestRunner: execute pytest and parse structured results
- TestLoop: orchestrator that generates tests, runs them, analyzes failures,
  applies LLM-suggested fixes, and repeats until passing or max iterations

Tool definitions and executor map are provided for ToolRegistry integration.
"""

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from core.mcp_servers._mcp_utils import run_subprocess

__all__ = [
    "TEST_LOOP_EXECUTOR_MAP",
    "TEST_LOOP_TOOL_DEFS",
    "TestGenerator",
    "TestLoop",
    "TestRunner",
]


# ======================================================================
# Test Generator
# ======================================================================


class TestGenerator:
    """Generate pytest test code for Python source files using LLM."""

    __test__ = False  # Not a pytest test class

    def __init__(self, client, model: str = "deepseek-v4-pro") -> None:
        """Initialize with an CruxClient for LLM calls.

        Args:
            client: CruxClient instance with .chat() method.
            model: LLM model id used for generation (default: deepseek-v4-pro).
        """
        self.client = client
        self.model = model

    def generate_tests(self, file_path: str, function_name: str = "") -> str:
        """Analyze a Python file and generate pytest test code.

        Args:
            file_path: Path to the Python source file to test.
            function_name: Optional specific function to target.

        Returns:
            String containing the generated pytest test code.
        """
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")

        prompt = (
            "You are a test engineer. Generate comprehensive pytest tests for the "
            "following Python source code.\n\n"
            f"Source file: {file_path}\n\n"
        )
        if function_name:
            prompt += f"Focus on testing the function: {function_name}\n\n"

        prompt += (
            "Rules:\n"
            "1. Import the module correctly (use the file's module path).\n"
            "2. Cover edge cases, normal cases, and error cases.\n"
            "3. Use descriptive test names.\n"
            "4. Include only the test code, no explanations.\n"
            "5. Output a complete, runnable test file.\n\n"
            f"Source code:\n```\n{source}\n```\n\n"
            "Generate the test file content now:"
        )

        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
        )

        content = ""
        choices = response.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        # Extract code block if wrapped in markdown fences
        code_match = re.search(r"```(?:python)?\s*\n(.*?)```", content, re.DOTALL)
        if code_match:
            content = code_match.group(1)

        return content.strip()

    def generate_test_file(self, file_path: str, function_name: str = "") -> str:
        """Generate tests and save to a test file alongside the source.

        Args:
            file_path: Path to the Python source file.
            function_name: Optional specific function to target.

        Returns:
            Path to the generated test file.
        """
        test_code = self.generate_tests(file_path, function_name)

        source_path = Path(file_path)
        test_dir = source_path.parent
        test_name = f"test_{source_path.name}"
        test_path = test_dir / test_name

        test_path.write_text(test_code, encoding="utf-8")

        return str(test_path)


# ======================================================================
# Test Runner
# ======================================================================


class TestRunner:
    """Execute pytest and parse structured results."""

    def run_tests(self, test_path: str, verbose: bool = False) -> dict:
        """Run pytest on a test file and return structured results.

        Args:
            test_path: Path to the pytest test file.
            verbose: Whether to use verbose output mode.

        Returns:
            Dict with: passed, failed, errors, total, duration_s,
            failures, success, raw_output.
        """
        args = [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short"]
        if verbose:
            args.append("-vv")

        start = time.time()
        result = run_subprocess(args, timeout=120)
        duration = time.time() - start

        output = result.stdout + result.stderr
        raw_output = output[:5000]

        passed = 0
        failed = 0
        errors = 0
        failures = []

        # Parse PASSED/FAILED/ERROR lines from pytest -v output
        for line in output.splitlines():
            line = line.strip()
            if line.endswith(" PASSED"):
                passed += 1
            elif line.endswith(" FAILED"):
                failed += 1
                # Extract test name
                test_name = line.split(" FAILED")[0].strip()
                failures.append({"test_name": test_name, "error": ""})
            elif line.endswith(" ERROR"):
                errors += 1
                test_name = line.split(" ERROR")[0].strip()
                failures.append({"test_name": test_name, "error": "collection/session error"})

        # Parse failure details from --tb=short output
        if failures:
            # Try to extract error details per test
            detail_sections = re.findall(r"={2,}\s*FAILURES\s*={2,}\n(.*)", output, re.DOTALL)
            if detail_sections:
                detail_text = detail_sections[0]
                # Match individual failure blocks
                fail_blocks = re.split(r"_{10,}\s*", detail_text)
                for i, block in enumerate(fail_blocks):
                    if i < len(failures) and block.strip():
                        failures[i]["error"] = block.strip()[:500]

        total = passed + failed + errors

        return {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": total,
            "duration_s": round(duration, 3),
            "failures": failures,
            "success": failed == 0 and errors == 0 and total > 0,
            "raw_output": raw_output,
        }

    def run_single_test(self, test_path: str, test_name: str) -> dict:
        """Run a single test by name.

        Args:
            test_path: Path to the pytest test file.
            test_name: Specific test function name (e.g. 'test_add_numbers').

        Returns:
            Same structured dict as run_tests.
        """
        # pytest -k filters by substring match on test name
        args = [
            sys.executable,
            "-m",
            "pytest",
            test_path,
            "-v",
            "--tb=short",
            "-k",
            test_name,
        ]

        start = time.time()
        result = run_subprocess(args, timeout=60)
        duration = time.time() - start

        output = result.stdout + result.stderr
        raw_output = output[:5000]

        passed = 0
        failed = 0
        errors = 0
        failures = []

        for line in output.splitlines():
            line = line.strip()
            if line.endswith(" PASSED"):
                passed += 1
            elif line.endswith(" FAILED"):
                failed += 1
                test_name_found = line.split(" FAILED")[0].strip()
                failures.append({"test_name": test_name_found, "error": ""})
            elif line.endswith(" ERROR"):
                errors += 1
                test_name_found = line.split(" ERROR")[0].strip()
                failures.append({"test_name": test_name_found, "error": "collection/session error"})

        total = passed + failed + errors

        return {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": total,
            "duration_s": round(duration, 3),
            "failures": failures,
            "success": failed == 0 and errors == 0 and total > 0,
            "raw_output": raw_output,
        }


# ======================================================================
# Test Loop (Main Orchestrator)
# ======================================================================


class TestLoop:
    """Orchestrate test generation, execution, failure analysis, and fix application.

    The full loop:
    1. Generate tests for the file/function
    2. Run tests
    3. If tests fail, use LLM to analyze failures and suggest a fix
    4. Apply the fix (write fixed code with backup)
    5. Re-run tests
    6. Repeat up to max_iterations
    """

    __test__ = False  # Not a pytest test class

    def __init__(self, client, model: str = "deepseek-v4-pro") -> None:
        """Initialize with CruxClient.

        Args:
            client: CruxClient instance with .chat() method.
            model: LLM model id used for generation & analysis
                   (default: deepseek-v4-pro).
        """
        self.client = client
        self.model = model
        self.generator = TestGenerator(client, model=model)
        self.runner = TestRunner()

    def run(self, file_path: str, function_name: str = "", max_iterations: int = 3) -> dict:
        """Execute the full test loop.

        Args:
            file_path: Path to the Python source file to test and fix.
            function_name: Optional specific function to target.
            max_iterations: Maximum number of generate/run/fix cycles.

        Returns:
            Dict with: test_file, iterations, final_status, total_duration_s.
        """
        start_time = time.time()
        iterations = []
        test_file = ""

        # Step 1: Generate test file
        test_file = self.generator.generate_test_file(file_path, function_name)

        for i in range(1, max_iterations + 1):
            # Step 2: Run tests
            result = self.runner.run_tests(test_file)
            iteration_data = {
                "iteration": i,
                "passed": result["passed"],
                "failed": result["failed"],
                "fix_applied": "",
            }

            # Step 3: If all tests pass, we're done
            if result["success"]:
                iterations.append(iteration_data)
                break

            # Step 4: Analyze failure and generate fix
            source_code = Path(file_path).read_text(encoding="utf-8", errors="replace")
            tool_name = function_name or Path(file_path).stem
            fix_description = self.analyze_failure(result["raw_output"], source_code, tool_name)

            iteration_data["fix_applied"] = fix_description[:200]

            # Step 5: Apply fix
            fixed_code = self._extract_fix_code(fix_description)
            if fixed_code:
                self.apply_fix(file_path, fixed_code)

                # Record the test pattern for cross-session learning
                try:
                    from utils.memory import record_test_pattern

                    record_test_pattern(
                        tool_name=tool_name,
                        failure_pattern=result["raw_output"][:300],
                        fix_applied=fixed_code[:500],
                    )
                except (OSError, UnicodeDecodeError):
                    pass

            iterations.append(iteration_data)

            # Step 6: Re-run tests (will happen in next iteration)
            # If last iteration, report max_iterations_reached
            if i == max_iterations:
                # Run one final test to get current status
                final_result = self.runner.run_tests(test_file)
                iterations[-1]["passed"] = final_result["passed"]
                iterations[-1]["failed"] = final_result["failed"]

        total_duration = time.time() - start_time

        # Determine final status
        if iterations and iterations[-1]["failed"] == 0 and iterations[-1]["passed"] > 0:
            final_status = "passed"
        elif len(iterations) >= max_iterations:
            final_status = "max_iterations_reached"
        else:
            final_status = "failed"

        return {
            "test_file": test_file,
            "iterations": iterations,
            "final_status": final_status,
            "total_duration_s": round(total_duration, 3),
        }

    def analyze_failure(self, test_output: str, source_code: str, tool_name: str = "") -> str:
        """Use LLM to analyze test failure and suggest a code fix.

        Injects past test patterns (from memory) so the LLM can reference
        solutions that worked for similar failures in previous sessions.

        Args:
            test_output: The pytest output showing failures.
            source_code: The current source code of the file being tested.
            tool_name: Optional name of the function/module being tested,
                       used to filter past test patterns.

        Returns:
            LLM response containing analysis and suggested fix.
        """
        # Inject past test patterns for cross-session learning
        past_patterns = ""
        try:
            from utils.memory import build_test_context

            past_patterns = build_test_context(tool_name)
        except (OSError, ValueError, RuntimeError):
            pass

        prompt = (
            "You are a debugging expert. Analyze the following test failure output "
            "and the source code, then suggest a fix.\n\n"
            "Rules:\n"
            "1. Identify the root cause of each failure.\n"
            "2. Provide the COMPLETE corrected source code (not just the changed parts).\n"
            "3. Wrap the corrected code in ```python``` markdown fences.\n"
            "4. Do not change the test file - fix only the source code.\n\n"
        )

        if past_patterns:
            prompt += f"{past_patterns}\n\nReference the patterns above if the current failure is similar.\n\n"

        prompt += (
            f"Test output:\n```\n{test_output[:3000]}\n```\n\n"
            f"Source code:\n```\n{source_code}\n```\n\n"
            "Provide your analysis and the corrected source code now:"
        )

        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4096,
        )

        content = ""
        choices = response.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        return content

    def apply_fix(self, file_path: str, fixed_code: str):
        """Write fixed code to file, creating a backup first.

        Args:
            file_path: Path to the source file to fix.
            fixed_code: The corrected source code to write.
        """
        backup_path = file_path + ".bak"
        # Create backup of original file
        shutil.copy2(file_path, backup_path)

        # Write fixed code with UTF-8 encoding
        Path(file_path).write_text(fixed_code, encoding="utf-8")

    def _extract_fix_code(self, llm_response: str) -> str:
        """Extract the fixed code block from LLM response.

        Args:
            llm_response: Full LLM response containing analysis and code block.

        Returns:
            The extracted code string, or empty string if no code block found.
        """
        # Look for the last python code block (the fix)
        code_blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", llm_response, re.DOTALL)
        if code_blocks:
            # Return the last code block (likely the complete fix)
            return code_blocks[-1].strip()
        return ""


# ======================================================================
# Tool Definitions for ToolRegistry
# ======================================================================

TEST_LOOP_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "generate_tests",
            "description": "Analyze a Python source file and generate pytest test code. Returns the test file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the Python source file to generate tests for",
                    },
                    "function_name": {
                        "type": "string",
                        "description": "Optional: specific function to focus tests on",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run pytest on a test file and return structured results with pass/fail counts and failure details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_path": {
                        "type": "string",
                        "description": "Path to the pytest test file to run",
                    },
                    "verbose": {
                        "type": "boolean",
                        "description": "Use verbose output mode",
                    },
                },
                "required": ["test_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_test_loop",
            "description": "Execute the full test loop: generate tests, run them, analyze failures, apply LLM-suggested fixes, and repeat until passing or max iterations reached.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the Python source file to test and fix",
                    },
                    "function_name": {
                        "type": "string",
                        "description": "Optional: specific function to focus on",
                    },
                    "max_iterations": {
                        "type": "integer",
                        "description": "Maximum number of generate/run/fix cycles (default: 3)",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
]


# ======================================================================
# Executor Map for ToolRegistry
# ======================================================================

# Module-level client reference, set by the caller before tool execution
_client = None


def _set_client(client):
    """Set the CruxClient instance for tool executors."""
    global _client
    _client = client


def _execute_generate_tests(**kwargs) -> str:
    """Tool executor: generate tests for a source file."""
    if not _client:
        return json.dumps({"error": "No client configured"}, ensure_ascii=False)
    generator = TestGenerator(_client)
    file_path = kwargs.get("file_path", "")
    function_name = kwargs.get("function_name", "")
    if not file_path:
        return json.dumps({"error": "file_path is required"}, ensure_ascii=False)
    try:
        test_path = generator.generate_test_file(file_path, function_name)
        return json.dumps(
            {
                "test_file": test_path,
                "source_file": file_path,
            },
            ensure_ascii=False,
        )
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _execute_run_tests(**kwargs) -> str:
    """Tool executor: run pytest on a test file."""
    test_path = kwargs.get("test_path", "")
    verbose = kwargs.get("verbose", False)
    if not test_path:
        return json.dumps({"error": "test_path is required"}, ensure_ascii=False)
    runner = TestRunner()
    try:
        result = runner.run_tests(test_path, verbose=verbose)
        return json.dumps(result, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, KeyError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _execute_run_test_loop(**kwargs) -> str:
    """Tool executor: run the full test loop."""
    if not _client:
        return json.dumps({"error": "No client configured"}, ensure_ascii=False)
    file_path = kwargs.get("file_path", "")
    function_name = kwargs.get("function_name", "")
    max_iterations = kwargs.get("max_iterations", 3)
    if not file_path:
        return json.dumps({"error": "file_path is required"}, ensure_ascii=False)
    loop = TestLoop(_client)
    try:
        result = loop.run(file_path, function_name, max_iterations)
        return json.dumps(result, ensure_ascii=False)
    except (subprocess.SubprocessError, OSError) as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


TEST_LOOP_EXECUTOR_MAP = {
    "generate_tests": _execute_generate_tests,
    "run_tests": _execute_run_tests,
    "run_test_loop": _execute_run_test_loop,
}
