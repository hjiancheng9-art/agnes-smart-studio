import subprocess, sys
r = subprocess.run([r'C:\Users\huangjiancheng\.kimi-code\bin\kimi.EXE', '--help'], 
                   capture_output=True, text=True, timeout=10)
print("stdout:", r.stdout[:500])
print("stderr:", r.stderr[:500])
print("rc:", r.returncode)
