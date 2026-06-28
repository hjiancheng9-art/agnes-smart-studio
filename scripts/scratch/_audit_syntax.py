#!/usr/bin/env python3
"""Syntax audit - check all .py files can be parsed."""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
errors = []

for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d != '__pycache__' and not d.startswith('.')]
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            rel = os.path.relpath(path, ROOT)
            try:
                with open(path, encoding='utf-8') as fh:
                    source = fh.read()
                ast.parse(source)
            except SyntaxError as e:
                errors.append(f'{rel}: {e}')
            except Exception as e:
                errors.append(f'{rel}: {type(e).__name__}: {e}')

if errors:
    print(f'FAIL: {len(errors)} syntax errors')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
else:
    print(f'ALL CLEAN: {sum(1 for r,d,fs in os.walk(ROOT) for f in fs if f.endswith(".py") and "__pycache__" not in r)} .py files parsed OK')
    sys.exit(0)
