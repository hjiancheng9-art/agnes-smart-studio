import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('ui/tui_v2.py', encoding='utf-8') as f:
    content = f.read()
lines = content.split('\n')
for i, line in enumerate(lines[-93:], start=len(lines)-92):
    print(repr(line))
