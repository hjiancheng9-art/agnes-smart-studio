#!/usr/bin/env python
"""CRUX color demo."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.colors import ANSI

c = ANSI

print(f"{c['bold']}{c['cyan']}╔══════════════════════╗")
print("║   CRUX Color Demo    ║")
print(f"╚══════════════════════╝{c['reset']}\n")

print(f" {c['bold']}Standard colors:{c['reset']}")
for name in ["red", "green", "yellow", "blue", "magenta", "cyan", "white"]:
    print(f"   {c[name]}{name:>7}{c['reset']}")

print(f"\n {c['bold']}User vs AI:{c['reset']}")
print(f"   {c['bright_green']}You: hello CRUX!{c['reset']}")
print(f"   {c['ai']}CRUX: hello! any help?{c['reset']}")
print()
