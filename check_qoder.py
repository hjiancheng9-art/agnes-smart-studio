import subprocess, json

# Try qoder with different syntax
r = subprocess.run(['cmd', '/c', 'qodercli', '-p', 'Review the architecture of project at C:\Users\huangjiancheng\agnes-smart-studio\core. Give top 3 issues.', '--print'],
                   capture_output=True, text=True, timeout=60, shell=True)
print(f"RC: {r.returncode}")
print(f"STDOUT: {r.stdout[:1000]}")
print(f"STDERR: {r.stderr[:300]}")
