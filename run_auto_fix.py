"""GPT-driven auto-fix loop: report → plan → execute → repeat."""
import subprocess, os, re, time, sys
import core.cdp_browser as cb

MAX_ROUNDS = 5
TEST_FILES = [
    "tests/test_interfaces.py", "tests/test_approval_gate.py",
    "tests/test_sandbox_executor.py", "tests/test_trm_routing.py",
    "tests/test_contracts.py", "tests/test_capability_registry.py",
    "tests/test_mcp_lsp_contracts.py",
]

os.makedirs(".crux/auto_fix", exist_ok=True)

def run_tests():
    r = subprocess.run(
        ["python", "-m", "pytest"] + TEST_FILES + ["--tb=line", "--maxfail=5", "-p", "no:cacheprovider"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, cwd=".", encoding="utf-8", errors="replace")
    out = r.stdout + r.stderr
    m = re.search(r'(\d+)\s+passed', out)
    passed = int(m.group(1)) if m else 0
    m = re.search(r'(\d+)\s+failed', out)
    failed = int(m.group(1)) if m else 0
    err_lines = [l for l in out.split('\n') if 'FAILED' in l or 'ERROR' in l]
    return passed, failed, '\n'.join(err_lines[:8])

for i in range(1, MAX_ROUNDS + 1):
    passed, failed, err_str = run_tests()
    print(f"\n{'='*50}")
    print(f"Round {i}: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    
    prompt = f"CRUX Round {i}: {passed} passed, {failed} failed. Errors: {err_str[:150] or 'none'}. Give ONE next step: TASK: <desc> CMD: <command> or TASK: DONE"
    print("Asking GPT...")
    resp = cb.ask_chatgpt(prompt, wait=True)
    
    t = re.search(r'TASK:\s*(.+)', resp)
    c = re.search(r'CMD:\s*(.+)', resp)
    
    if not t:
        print(f"Parse failed: {resp[:200]}")
        break
    
    task = t.group(1).strip()
    
    if "DONE" in task.upper():
        print(f"DONE at round {i}!")
        break
    
    cmd = c.group(1).strip() if c else ""
    print(f"TASK: {task}")
    print(f"CMD: {cmd}")
    
    if not cmd:
        continue
    
    try:
        r2 = subprocess.run(cmd.split(), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, cwd=".")
        ok = r2.returncode == 0
        print(f"Result: {'OK' if ok else 'FAIL'}")
        if r2.stdout:
            print(f"  OUT: {r2.stdout[:200]}")
        if r2.stderr:
            print(f"  ERR: {r2.stderr[:200]}")
    except Exception as e:
        print(f"Exec error: {e}")
    
    time.sleep(1)

passed, failed, _ = run_tests()
print(f"\nFinal: {passed} passed, {failed} failed")
