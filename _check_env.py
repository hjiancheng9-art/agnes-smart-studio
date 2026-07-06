import sys, asyncio
print(f"Python: {sys.executable}")
print(f"CWD: {__import__('os').getcwd()}")

# Check if playwright works
try:
    import playwright
    print(f"Playwright found at: {playwright.__file__}")
except ImportError:
    print("Playwright NOT importable")

# List processes
import subprocess
r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq msedge.exe'], capture_output=True, text=True, timeout=5)
print(r.stdout[:500])
