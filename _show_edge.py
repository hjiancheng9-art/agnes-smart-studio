import sys

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
with open("tools/edge/edge_connect.py", encoding="utf-8") as f:
    lines = f.readlines()
for i, line in enumerate(lines[:95]):
    print(f"{i+1}: {line}", end="")
