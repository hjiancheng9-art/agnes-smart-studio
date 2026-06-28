import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
with open("tools.json", encoding="utf-8") as f:
    cfg = json.load(f)
tools = cfg["tools"]
print(f"Total: {len(tools)} tools\n")
from collections import Counter

cats = Counter(t["type"] for t in tools)
for c, n in cats.most_common():
    names = [t["name"] for t in tools if t.get("type") == c]
    print(f"[{c}] x{n}")
    for nm in sorted(names):
        print(f"  - {nm}")
    print()
