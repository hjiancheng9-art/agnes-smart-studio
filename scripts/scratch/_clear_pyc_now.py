import contextlib
import glob
import os

for d in glob.glob(r"C:\Users\huangjiancheng\agnes-smart-studio\**\__pycache__", recursive=True):
    for f in glob.glob(d + "/*.pyc"):
        with contextlib.suppress(Exception):
            os.remove(f)
print("done")
