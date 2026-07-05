import subprocess, sys, os

# Call Claude Code directly to review the DAG code
script = r"""
cd /d C:\Users\huangjiancheng\agnes-smart-studio
C:\Users\huangjiancheng\.local\bin\claude.EXE -p "Review _build_dag_layers in core/multi_agent.py. 1) Edge cases? 2) Improvements? 3) Bug risks? Keep under 200 words." --print 2>&1
"""

result = subprocess.run(['cmd', '/c', script], capture_output=True, text=True, timeout=60)
print("STDOUT:", result.stdout[:1000])
if result.stderr:
    print("STDERR:", result.stderr[:200])
print("RC:", result.returncode)
