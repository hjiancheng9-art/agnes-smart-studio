"""Check tools.json for format string issues."""
import json
import re
from pathlib import Path

data = Path('tools.json').read_text(encoding='utf-8')
cfg = json.loads(data)

# Check all {xxx} placeholders
print("=== All {xxx} in full file ===")
for m in re.finditer(r'\{[a-zA-Z_]\w*\}', data):
    ctx_start = max(0, m.start() - 10)
    ctx_end = min(len(data), m.end() + 10)
    print(f"  pos={m.start()}: {m.group()!r}  context: ...{data[ctx_start:ctx_end]!r}...")

print("\n=== Per-tool format check ===")
bad = []
for t in cfg.get("tools", []):
    name = t.get("name", "?")
    cmd = t.get("command", "")
    params = set(t.get("parameters", {}).keys())
    placeholders = set(re.findall(r"\{([a-zA-Z_]\w*)\}", cmd))
    unexpected = placeholders - params
    if unexpected:
        bad.append(f"{name}: unexpected={unexpected}, params={params}, placeholders={placeholders}")
        print(f"  BAD: {name}: unexpected={unexpected}, all_placeholders={placeholders}, params={params}")
    else:
        print(f"  OK: {name}: placeholders={placeholders}, params={params}")

if bad:
    print(f"\n{len(bad)} tool(s) have conflicts:")
    for b in bad:
        print(f"  - {b}")
else:
    print("\nAll tools clean!")
