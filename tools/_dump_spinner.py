import sys

with open("ui/widgets_v2.py", encoding="utf-8") as f:
    lines = f.readlines()
idx = next(i for i, line in enumerate(lines) if "class Spinner" in line)
for i in range(idx, min(idx + 50, len(lines))):
    sys.stdout.write(str(i + 1) + ": " + lines[i].rstrip() + "\n")
