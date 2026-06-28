import os
import subprocess
import sys

nl = chr(10)
tb = chr(96) * 3

def run_audit(self, session, root):
    # Phase 1: Syntax
    console.print('[bold]=== Phase 1/3: Syntax Check ===[/]')
    ok = True
    for d in ['core','engines','utils','ui']:
        dp = os.path.join(root, d)
        if os.path.isdir(dp):
            for dp2,_,fs in os.walk(dp):
                for f in fs:
                    if f.endswith('.py'):
                        fp = os.path.join(dp2, f)
                        try:
                            subprocess.run([sys.executable,'-m','py_compile',fp],capture_output=True,check=True)
                        except Exception:
                            console.print(f'[red]FAIL: {fp}[/]')
                            ok = False
    if ok: console.print('[green]All Python files pass syntax check[/]')

    # Phase 2: Health
    console.print('[bold]=== Phase 2/3: Health Check ===[/]')
    try:
        from core.startup_checks import run_all
        for _cat, ok2, msg in run_all():
            console.print(f'  [{"green" if ok2 else "red"}]{msg}[/]')
    except Exception:
        console.print('[yellow]Health check skipped[/]')

    # Phase 3: AI Analysis
    console.print('[bold]=== Phase 3/3: AI Source Analysis ===[/]')
    session.unlimited_tools = True
    session._skip_tools = True
    if not session.code_mode: session.code_mode = True
    sources = []
    tc = 0
    for sub in ['core','engines']:
        for dp3,_,fs3 in os.walk(os.path.join(root, sub)):
            for f3 in sorted(fs3):
                if f3.endswith('.py') and not f3.startswith('_'):
                    fp3 = os.path.join(dp3, f3)
                    try:
                        c3 = open(fp3,encoding='utf-8').read()
                        sources.append('### ' + sub + '/' + f3 + nl + tb + 'python' + nl + c3 + nl + tb)
                        tc += len(c3)
                        if tc > 120000: break
                    except Exception: pass
            if tc > 120000: break
        if tc > 120000: break
    ctx = (
        '=== HARD RULE: DO NOT call any tools. All source code is IN THIS MESSAGE. ===' + nl + nl +
        'CRUX Studio source code audit. Output three sections: Bug risks, API compliance, Optimization suggestions.' + nl + nl +
        nl.join(sources)
    )
    console.print('[dim]AI analyzing source...[/]')
    # 直接用底层 API，不走工具调用循环
    for delta in session.client.chat_stream(
        model=session.model,
        messages=[{"role": "user", "content": ctx}],
        max_tokens=4096,
    ):
        if "content" in delta:
            console.print(delta["content"], end="")
    console.print()
from rich.console import Console

console = Console()
from rich.console import Console

console = Console()
