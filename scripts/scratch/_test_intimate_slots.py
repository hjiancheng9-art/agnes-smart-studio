import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")

output_lines = []


def test_module(name, import_path, test_fn):
    try:
        result = test_fn()
        output_lines.append(f"[{name}] OK - {result}")
    except Exception as e:
        output_lines.append(f"[{name}] FAIL - {e}")


# 1
test_module(
    "护符",
    "core.intimate_slots.talisman",
    lambda: (__import__("core.intimate_slots.talisman", fromlist=["circuit"]).circuit.check(), "imported")[1],
)

# Simple direct tests
import importlib

mods = {
    "护符": "core.intimate_slots.talisman",
    "内甲": "core.intimate_slots.inner_armor",
    "行囊": "core.intimate_slots.backpack",
    "腰带": "core.intimate_slots.belt",
    "左戒": "core.intimate_slots.left_ring",
    "右戒": "core.intimate_slots.right_ring",
    "披风": "core.intimate_slots.cloak",
}

ok = 0
for name, mod_path in mods.items():
    try:
        importlib.import_module(mod_path)
        output_lines.append(f"[{name}] OK - imported")
        ok += 1
    except Exception as e:
        output_lines.append(f"[{name}] FAIL - {e}")

output_lines.append(f"\nTotal: {ok}/{len(mods)}")

with open("_test_intimate_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))
