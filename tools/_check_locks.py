with open("ui/tui_v2.py", encoding="utf-8") as f:
    lines = f.readlines()
targets = ["_closing", "_streaming", "_thinking", "_cancel_requested"]
results = []
for i, line in enumerate(lines):
    for t in targets:
        if "self." + t + " =" in line or "self." + t + "=" in line:
            results.append((i + 1, t, line.rstrip()[:120]))
            break
with open("tools/_lock_check_result.txt", "w", encoding="utf-8") as out:
    for r in results:
        out.write(f"L{r[0]:4d} | {r[1]:20s} | {r[2]}\n")
print(f"Written {len(results)} lines to tools/_lock_check_result.txt")
