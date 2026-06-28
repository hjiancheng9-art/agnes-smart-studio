"""Intimate slots import & smoke test."""

import os
import sys

sys.path.insert(0, ".")
os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")

results = []

# Test 1: Import all 7
for mod_name, cn_name in [
    ("talisman", "护符"),
    ("inner_armor", "内甲"),
    ("backpack", "行囊"),
    ("belt", "腰带"),
    ("left_ring", "左戒"),
    ("right_ring", "右戒"),
    ("cloak", "披风"),
]:
    try:
        mod = __import__(f"core.intimate_slots.{mod_name}", fromlist=["_"])
        results.append(f"[{cn_name}] OK - imported")
    except Exception as e:
        results.append(f"[{cn_name}] FAIL import - {e}")

# Test 2: Smoke test each
try:
    from core.intimate_slots.talisman import circuit

    ok, reason = circuit.check()
    results.append(f"[护符] check() -> {ok}, {reason}")
    circuit.record_success("test")
except Exception as e:
    results.append(f"[护符] smoke FAIL - {e}")

try:
    from core.intimate_slots.inner_armor import vault

    vault.set("_test_key", "_test_val")
    val = vault.get("_test_key")
    vault.delete("_test_key")
    results.append(f"[内甲] set/get/delete -> {val}")
except Exception as e:
    results.append(f"[内甲] smoke FAIL - {e}")

try:
    from core.intimate_slots.backpack import backpack

    name = backpack.snapshot("test")
    snaps = backpack.list_snapshots()
    results.append(f"[行囊] snapshot '{name}', total: {len(snaps)}")
except Exception as e:
    results.append(f"[行囊] smoke FAIL - {e}")

try:
    from core.intimate_slots.belt import pipeline

    pipeline.push("hello", "test")
    results.append(f"[腰带] push OK, buffer: {len(pipeline._buffer)}")
except Exception as e:
    results.append(f"[腰带] smoke FAIL - {e}")

try:
    from core.intimate_slots.left_ring import telemetry

    telemetry.log("test", tool="smoke_test", latency=0.1)
    results.append(f"[左戒] log OK, calls: {telemetry._counts['calls']}")
except Exception as e:
    results.append(f"[左戒] smoke FAIL - {e}")

try:
    from core.intimate_slots.right_ring import healer

    status = healer.check()
    results.append(f"[右戒] health: {status.get('health', '?')}/100")
except Exception as e:
    results.append(f"[右戒] smoke FAIL - {e}")

try:
    from core.intimate_slots.cloak import cloak

    test = "hello sk-1234567890abcdefghijklmnop"
    sanitized = cloak.sanitize(test)
    results.append(f"[披风] sanitize OK, len: {len(sanitized)}")
except Exception as e:
    results.append(f"[披风] smoke FAIL - {e}")

# Test 3: Lazy-load via __init__
try:
    import core.intimate_slots as slots

    t = slots.talisman
    results.append("[__init__] lazy-load talisman OK")
except Exception as e:
    results.append(f"[__init__] lazy-load FAIL - {e}")

print("\n".join(results))
print("\n=== DONE ===")
