#!/usr/bin/env python3
import contextlib
import os

base = r"C:\Users\huangjiancheng\agnes-smart-studio"
for root, _dirs, files in os.walk(base):
    if "__pycache__" in root:
        for f in files:
            if f.endswith(".pyc"):
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(root, f))
print("pyc cleared")
