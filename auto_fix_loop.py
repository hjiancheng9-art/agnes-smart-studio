#!/usr/bin/env python3
"""GPT-driven auto-repair loop — report → plan → execute → repeat.

Usage:
    python auto_fix_loop.py          # Run until exhausted
    python auto_fix_loop.py --once   # Single iteration
    python auto_fix_loop.py --dry    # Show what would happen, no exec
"""

import subprocess
import re
import sys
import json
import os
import time
from datetime import datetime

DRY_RUN = "--dry" in sys.argv
ONCE = "--once" in sys.argv

PROJECT = "CRUX Studio"
MAX_ITERATIONS = 20


def run(cmd_list, timeout=30, cwd="."):
    """Run command as list (no shell), return (stdout, stderr, returncode)."""
    if DRY_RUN:
        print(f"  [DRY] would run: {' '.join(cmd_list)}")
        return "", "", 0
    r = subprocess.run(cmd_list, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       timeout=timeout, cwd=cwd)
    return r.stdout.strip(), r.stderr.strip(), r.returncode


def pytest_summary():
    """Get test pass/fail summary for new test suite."""
    test_files = [
        "tests/test_interfaces.py", "tests/test_approval_gate.py",
        "tests/test_sandbox_executor.py", "tests/test_trm_routing.py",
        "tests/test_contracts.py", "tests/test_capability_registry.py",
        "tests/test_mcp_lsp_contracts.py",
    ]
    out, err, rc = run(["python", "-m", "pytest"] + test_files + ["--tb=line", "--maxfail=5", "-p", "no:cacheprovider"], timeout=60)
    # Extract pass/fail
    m = re.search(r'(\d+)\s+passed', out)
    passed = int(m.group(1)) if m else 0
    m = re.search(r'(\d+)\s+failed', out)
    failed = int(m.group(1)) if m else 0
    m = re.search(r'(\d+)\s+skipped', out)
    skipped = int(m.group(1)) if m else 0
    return passed, failed, skipped, err[:300] if err else ""


def git_diff_summary():
    """Get recent changes."""
    out, _, _ = run(["git", "diff", "HEAD", "--name-only"], timeout=10)
    files = [f for f in out.split('\n') if f.strip()] if out else []
    return files[:20]


def count_lines():
    """Count total .py lines."""
    total = 0
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if not d.startswith(('.','node_modules','__pycache__'))]
        for f in files:
            if f.endswith('.py'):
                try:
                    with open(os.path.join(root,f), encoding='utf-8', errors='ignore') as fh:
                        total += sum(1 for _ in fh)
                except:
                    pass
    return str(total)


def gather_state() -> dict:
    """Collect full project state snapshot."""
    passed, failed, skipped, err = pytest_summary()
    
    # Total collectable
    out, _, _ = run(["python", "-m", "pytest", "tests/", "--co", "-q"], timeout=30)
    total_tests = str(len([l for l in out.split('\n') if '::' in l])) if out else "?"
    
    py_lines = count_lines()
    recent_changes = git_diff_summary()
    
    return {
        "test_pass": passed,
        "test_fail": failed,
        "test_skip": skipped,
        "total_collectable": total_tests,
        "test_errors": err[:500],
        "python_lines": py_lines,
        "recent_files": recent_changes[:10],
    }


def send_to_gpt(state: dict, iteration: int) -> str:
    """Send state to ChatGPT via CDP, return response."""
    prompt = f"""你正在自动化修复 {PROJECT}。第 {iteration} 轮。

## 当前状态
- 测试: {state['test_pass']} passed, {state['test_fail']} failed, {state['test_skip']} skipped
- 可收集测试总数: {state['total_collectable']}
- Python 代码行数: {state['python_lines']}
- 最近修改文件: {', '.join(state['recent_files'][:8])}

## 测试错误
{state['test_errors'][:400] or '无错误'}

## 你的任务
基于当前状态，给出**一个具体可执行的下一步**。只需要一条指令，格式：
```
TASK: <简短描述>
CMD: <可执行的 shell 或 python 命令>
```
或者如果认为当前状态已经足够好，回复：
```
TASK: DONE
```
只回复一条指令。"""
    
    print(f"\n{'='*60}")
    print(f"📤 发送给 GPT (第{iteration}轮)...")
    print(f"{'='*60}")
    
    import core.cdp_browser as cb
    result = cb.ask_chatgpt(prompt, wait=True)
    
    # Save for debugging
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f".crux/auto_fix/round_{iteration:03d}_{ts}.txt", "w", encoding="utf-8") as f:
        f.write(f"=== PROMPT ===\n{prompt}\n\n=== RESPONSE ===\n{result}")
    
    return result


def parse_task(response: str):
    """Extract TASK and CMD from GPT response."""
    task_match = re.search(r'TASK:\s*(.+)', response)
    cmd_match = re.search(r'CMD:\s*(.+?)(?:\n|$)', response)
    
    task = task_match.group(1).strip() if task_match else ""
    cmd = cmd_match.group(1).strip() if cmd_match else ""
    
    if "DONE" in task.upper():
        return "DONE", ""
    return task, cmd


def execute_task(task: str, cmd: str) -> bool:
    """Execute the task, return True if successful."""
    if not cmd:
        print(f"  ⚠ No command to execute")
        return False
    
    print(f"\n  🎯 TASK: {task}")
    print(f"  ⚡ CMD: {cmd}")
    
    if DRY_RUN:
        return True
    
    # Split command for safe execution
    cmd_parts = cmd.split()
    try:
        out, err, rc = run(cmd_parts, timeout=60)
        if rc == 0:
            print(f"  ✅ OK")
            if out:
                print(f"  📝 {out[:200]}")
            return True
        else:
            print(f"  ❌ Failed (rc={rc})")
            if err:
                print(f"  🔴 {err[:300]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ⏱️ Timeout")
        return False
    except Exception as e:
        print(f"  💥 {e}")
        return False


def main():
    os.makedirs(".crux/auto_fix", exist_ok=True)
    
    print("=" * 60)
    print(f"🤖 {PROJECT} Auto-Fix Loop")
    print(f"   模式: {'DRY RUN' if DRY_RUN else 'REAL'}")
    print(f"   最大迭代: {MAX_ITERATIONS}")
    print("=" * 60)
    
    for i in range(1, MAX_ITERATIONS + 1):
        print(f"\n{'─'*60}")
        print(f"📍 第 {i}/{MAX_ITERATIONS} 轮 — {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'─'*60}")
        
        # 1. Gather state
        print("\n📊 收集状态...")
        state = gather_state()
        print(f"   Tests: {state['test_pass']}✓ {state['test_fail']}✗ {state['test_skip']}⊘")
        print(f"   Total: {state['total_collectable']} collectable")
        print(f"   Python: {state['python_lines']} lines")
        
        # 2. Send to GPT
        response = send_to_gpt(state, i)
        
        # 3. Parse task
        task, cmd = parse_task(response)
        
        if task == "DONE":
            print(f"\n🏁 GPT says DONE at iteration {i}")
            break
        
        if not task:
            print(f"\n⚠ Could not parse task from GPT response")
            print(f"   Response: {response[:300]}...")
            break
        
        # 4. Execute
        ok = execute_task(task, cmd)
        
        # 5. Verify
        passed, failed, skipped, _ = pytest_summary()
        print(f"   After: {passed}✓ {failed}✗ {skipped}⊘")
        
        if ONCE:
            break
        
        time.sleep(1)
    
    # Final report
    print(f"\n{'='*60}")
    passed, failed, skipped, _ = pytest_summary()
    print(f"🏁 Auto-fix complete: {passed}✓ {failed}✗ {skipped}⊘")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
