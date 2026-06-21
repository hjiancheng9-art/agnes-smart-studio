"""Self-evolution engine powered by local 30B model.

Analyzes tool failures, proposes fixes, and auto-implements simple improvements.
The local model runs analysis-heavy reasoning that would be expensive via cloud API.

Architecture:
    core/self_evolve.py    <- this file
    output/traces.jsonl     <- input: tool call traces
    output/tool_audit.jsonl <- input: tool success/failure audit
    output/history.jsonl    <- input: image/video generation history
    -> local model analysis -> proposed patches / new tools
"""

import json
import re
from pathlib import Path

from core.config import OUTPUT_DIR

__all__ = [
    'SELF_EVOLVE_EXECUTOR_MAP', 'SELF_EVOLVE_TOOL_DEFS', 'apply_patch_safe', 'build_analysis_prompt', 'collect_failure_logs', 'collect_recent_code', 'exec_self_evolve', 'extract_file_patches', 'parse_evolution_output',
]


def collect_failure_logs(max_entries: int = 30) -> list[dict]:
    """Collect recent tool failures from trace and audit logs.

    Returns list of failure entries, newest first.
    """
    entries = []

    # From tool_audit.jsonl
    audit_path = OUTPUT_DIR / "tool_audit.jsonl"
    if audit_path.exists():
        try:
            for line in audit_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if not entry.get("success", True):
                        entries.append({
                            "source": "tool_audit",
                            "tool": entry.get("tool", "?"),
                            "error": entry.get("error", entry.get("error_type", "?")),
                            "args": entry.get("args", {}),
                        })
                except json.JSONDecodeError:
                    pass
        except (OSError, UnicodeDecodeError):
            pass

    # From traces.jsonl (last N lines)
    traces_path = OUTPUT_DIR / "traces.jsonl"
    if traces_path.exists():
        try:
            lines = traces_path.read_text(encoding="utf-8").strip().split("\n")
            for line in lines[-max_entries:]:
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if not entry.get("success", True):
                        entries.append({
                            "source": "traces",
                            "tool": entry.get("tool", "?"),
                            "error": entry.get("error", "?"),
                            "args": entry.get("args", {}),
                            "timestamp": entry.get("timestamp", ""),
                        })
                except json.JSONDecodeError:
                    pass
        except (OSError, UnicodeDecodeError):
            pass

    return entries[-max_entries:]


def collect_recent_code(files: list[str] | None = None) -> str:
    """Collect recent source code for the local model to analyze.

    If files is None, collects all .py files in core/ and engines/.
    Returns concatenated source with file headers.
    """
    if files is None:
        project_root = Path(__file__).parent.parent
        patterns = ["core/*.py", "engines/*.py", "ui/*.py", "utils/*.py"]
        collected = []
        for pat in patterns:
            for fp in sorted(project_root.glob(pat)):
                try:
                    content = fp.read_text(encoding="utf-8")
                    if len(content) > 15000:
                        content = content[:15000] + "\n# ... (truncated)"
                    collected.append(f"=== {fp.name} ===\n{content}")
                except (OSError, UnicodeDecodeError):
                    pass
        return "\n\n".join(collected)

    result = []
    for fp in files:
        p = Path(fp)
        if p.exists():
            try:
                result.append(f"=== {p.name} ===\n{p.read_text(encoding='utf-8')}")
            except (OSError, UnicodeDecodeError):
                result.append(f"=== {p.name} ===\n[read error]")
    return "\n\n".join(result)


def build_analysis_prompt(failures: list[dict], code_snippet: str = "",
                          priority_files: list[str] | None = None) -> str:
    """Build a structured prompt for the local model to analyze.

    Uses smart code collection that:
    - Prioritizes files mentioned in failures
    - Shows full small files, head+tail for large files
    - Fits within 32K token budget

    The prompt asks the model to:
    1. Categorize each failure
    2. Identify root causes
    3. Propose concrete code fixes with exact FILE/FIND/REPLACE blocks
    """
    failures_json = json.dumps(failures, ensure_ascii=False, indent=2)

    # If code_snippet is empty, collect source code
    if not code_snippet:
        # Extract referenced file paths from failures
        ref_files = set()
        for f in failures:
            tool = f.get("tool", "")
            if tool in ("read_file", "write_file", "edit_file"):
                path = f.get("args", {}).get("path", "")
                if path:
                    ref_files.add(path)
        code_snippet = collect_recent_code(
            files=list(ref_files) if ref_files else None,
        )

    prompt = f"""You are an expert Python code reviewer and systems engineer analyzing "Agnes Smart Studio", a private AI tool.

Analyze the tool call failures below and the source code. Provide EXACT file patches using the FILE:/FIND:/REPLACE: format.

## Failures ({len(failures)} entries)
```json
{failures_json[:8000]}
```

## Source Code (smart-chunked for 32K context)
{code_snippet[:18000]}

## Your Task
Write a structured analysis:

### 1. Failure Categories
Group failures by type and root cause.

### 2. Critical Fixes (must-fix)
For impactful issues, propose EXACT code changes. Use this format:
```
FILE: core/agent.py
FIND: <EXACT old code from the source above, copy-paste precisely>
REPLACE: <EXACT new code>
REASON: <one line explanation>
```

IMPORTANT: 
- FILE paths must match the actual project structure (core/..., engines/..., ui/..., utils/...)
- FIND text must be verbatim from the source code provided above
- Propose minimal, safe changes

### 3. Preventive Measures
New validation checks or guardrails that prevent similar failures.

### 4. New Tool Suggestions
Missing capabilities that would reduce failures.

Only output the structured analysis. No conversational filler."""
    return prompt


def parse_evolution_output(raw_output: str) -> dict:
    """Parse the local model's analysis output into structured data.

    Returns dict with keys: categories, fixes, preventions, suggestions, edit_file_tasks
    edit_file_tasks are ready for DeepSeek to execute with edit_file tool.
    """
    result = {
        "categories": [],
        "fixes": [],
        "preventions": [],
        "suggestions": [],
        "edit_file_tasks": [],
        "raw": raw_output,
    }

    current_section = None
    for line in raw_output.split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("### 1.") or line.startswith("### Failure"):
            current_section = "categories"
            continue
        elif line.startswith("### 2.") or line.startswith("### Critical"):
            current_section = "fixes"
            continue
        elif line.startswith("### 3.") or line.startswith("### Preventive"):
            current_section = "preventions"
            continue
        elif line.startswith("### 4.") or line.startswith("### New Tool"):
            current_section = "suggestions"
            continue

        if current_section == "categories":
            result["categories"].append(line)
        elif current_section == "fixes":
            result["fixes"].append(line)
        elif current_section == "preventions":
            result["preventions"].append(line)
        elif current_section == "suggestions":
            result["suggestions"].append(line)

    # Extract EDIT_FILE_* blocks for DeepSeek execution
    task_pattern = re.compile(
        r"EDIT_FILE_PATH:\s*(.+?)\nEDIT_FILE_FIND:\s*\n?(.*?)\nEDIT_FILE_REPLACE:\s*\n?(.*?)\nREASON:\s*(.*?)(?:\n|$)",
        re.DOTALL | re.IGNORECASE,
    )
    for match in task_pattern.finditer(raw_output):
        result["edit_file_tasks"].append({
            "path": match.group(1).strip(),
            "find": match.group(2).strip(),
            "replace": match.group(3).strip(),
            "reason": match.group(4).strip(),
            "action": "Run edit_file tool with these params",
        })

    return result


def extract_file_patches(analysis_text: str) -> list[dict]:
    """Extract file patches from analysis output.

    Looks for blocks like:
    FILE: path/to/file.py
    FIND: <old code>
    REPLACE: <new code>
    REASON: <why>
    """
    patches = []
    pattern = re.compile(
        r"FILE:\s*(.+?)\n.*?FIND:\s*\n?(.*?)\n.*?REPLACE:\s*\n?(.*?)\n.*?REASON:\s*(.*?)(?:\n|$)",
        re.DOTALL | re.IGNORECASE,
    )

    for match in pattern.finditer(analysis_text):
        filepath = match.group(1).strip()
        find = match.group(2).strip()
        replace = match.group(3).strip()
        reason = match.group(4).strip()
        patches.append({
            "file": filepath,
            "find": find,
            "replace": replace,
            "reason": reason,
        })

    return patches


def apply_patch_safe(patch: dict, dry_run: bool = True) -> dict:
    """Safely apply a single file patch.

    In dry_run mode, only validates the patch can be applied.
    Returns {"success": bool, "file": str, "error": str}.
    """
    filepath = patch["file"]
    p = Path(filepath)
    if not p.is_absolute():
        p = Path(__file__).parent.parent / p

    if not p.exists():
        return {"success": False, "file": filepath, "error": "File not found"}

    try:
        original = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {"success": False, "file": filepath, "error": str(e)}

    find_text = patch["find"]
    if find_text not in original:
        return {
            "success": False,
            "file": filepath,
            "error": f"FIND text not found in file (first 60 chars: {find_text[:60]!r})",
        }

    if dry_run:
        return {"success": True, "file": filepath, "dry_run": True}

    # Apply the patch
    new_content = original.replace(find_text, patch["replace"], 1)
    try:
        # Create backup
        backup_path = p.with_suffix(p.suffix + ".bak")
        p.rename(backup_path)
        # Write new content
        p.write_text(new_content, encoding="utf-8")
        return {
            "success": True,
            "file": filepath,
            "backup": str(backup_path),
            "reason": patch.get("reason", ""),
        }
    except (OSError, PermissionError) as e:
        return {"success": False, "file": filepath, "error": str(e)}


# ─── Tool executor functions for chat.py registration ────

def exec_self_evolve(**kwargs) -> str:
    """Execute self-evolution analysis using the local model.

    Tool executor registered in ToolRegistry.
    """
    mode = kwargs.get("mode", "analyze")
    max_failures = kwargs.get("max_failures", 20)

    if mode == "analyze":
        failures = collect_failure_logs(max_entries=max_failures)
        if not failures:
            return json.dumps({
                "status": "ok",
                "message": "No recent failures found. Everything looks healthy.",
                "failure_count": 0,
            }, ensure_ascii=False, indent=2)

        code = collect_recent_code()
        prompt = build_analysis_prompt(failures, code)
        analysis = _call_local_model(prompt, max_tokens=3000)

        parsed = parse_evolution_output(analysis)
        patches = extract_file_patches(analysis)

        return json.dumps({
            "status": "ok",
            "failure_count": len(failures),
            "analysis": parsed,
            "edit_file_tasks": parsed.get("edit_file_tasks", []),
            "extracted_patches": len(patches),
            "patches": patches[:5],
            "raw_analysis": analysis[:2000],
            "_collaboration_instruction": (
                "30B local model diagnosed these failures. "
                + f"{len(parsed.get('edit_file_tasks', []))} edit_file tasks are ready. "
                + "DeepSeek: use read_file to verify FIND text matches actual file content, "
                + "then use edit_file to apply each task. After applying, run tests to verify."
            ),
        }, ensure_ascii=False, indent=2)

    elif mode == "apply":
        # Extract and apply patches from the last analysis
        failures = collect_failure_logs(max_entries=max_failures)
        if not failures:
            return json.dumps({
                "status": "ok",
                "message": "No failures to fix.",
            }, ensure_ascii=False, indent=2)

        code = collect_recent_code()
        prompt = build_analysis_prompt(failures, code)
        analysis = _call_local_model(prompt, max_tokens=3000)
        patches = extract_file_patches(analysis)

        results = []
        for p in patches:
            r = apply_patch_safe(p, dry_run=kwargs.get("dry_run", True))
            results.append(r)

        return json.dumps({
            "status": "ok",
            "patches_found": len(patches),
            "results": results,
        }, ensure_ascii=False, indent=2)

    return json.dumps({
        "status": "error",
        "message": f"Unknown mode: {mode}. Use 'analyze' or 'apply'.",
    }, ensure_ascii=False)


def _call_local_model(prompt: str, max_tokens: int = 3000) -> str:
    """Call the local llama-server model and return its output."""
    import httpx

    LLAMA_BASE = "http://127.0.0.1:8080"
    model_id = "local-model"

    # Auto-detect model
    try:
        with httpx.Client(trust_env=False, timeout=10) as probe:
            r = probe.get(f"{LLAMA_BASE}/v1/models")
            if r.status_code == 200:
                models = r.json().get("models", [])
                if models:
                    model_id = models[0].get("name", model_id)
    except (httpx.HTTPError, OSError, KeyError):
        pass  # llama-server probe failed

    try:
        with httpx.Client(trust_env=False, timeout=300) as client:
            r = client.post(
                f"{LLAMA_BASE}/v1/chat/completions",
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": "You are an expert software engineer. Output structured analysis only."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                },
            )
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        return f"[local model error: HTTP {r.status_code}]"
    except (httpx.HTTPError, OSError, KeyError) as e:
        return f"[local model unavailable: {type(e).__name__}: {e}]"


# Tool definitions for ToolRegistry
SELF_EVOLVE_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "self_evolve",
            "description": (
                "Analyze recent tool failures and propose improvements using the local AI model. "
                "Mode 'analyze' reads failure logs and returns root cause analysis with suggested fixes. "
                "Mode 'apply' also attempts to apply safe patches automatically. "
                "Use this when you notice patterns of tool failures."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "analyze = read logs and propose fixes; apply = also auto-apply safe patches",
                        "enum": ["analyze", "apply"],
                    },
                    "max_failures": {
                        "type": "integer",
                        "description": "Maximum number of failure entries to analyze (default: 20)",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "In apply mode, only validate patches without writing (default: true)",
                    },
                },
                "required": [],
            },
        },
    },
]

SELF_EVOLVE_EXECUTOR_MAP = {
    "self_evolve": exec_self_evolve,
}
