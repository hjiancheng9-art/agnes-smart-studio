import os

root = r"C:\Users\huangjiancheng\WorkBuddy\nsp-downloader"

# list src recursively
for dirpath, _dirnames, filenames in os.walk(os.path.join(root, "src")):
    for f in filenames:
        fp = os.path.join(dirpath, f)
        print(fp)

# read package.json
with open(os.path.join(root, "package.json"), encoding="utf-8") as fh:
    print("\n=== package.json ===")
    print(fh.read())

# read forge.config
with open(os.path.join(root, "forge.config.js"), encoding="utf-8") as fh:
    print("\n=== forge.config.js ===")
    print(fh.read())
