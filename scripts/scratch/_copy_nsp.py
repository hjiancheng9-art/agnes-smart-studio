import os
import shutil

root = r"C:\Users\huangjiancheng\WorkBuddy\nsp-downloader"
dest = r"C:\Users\huangjiancheng\crux-smart-studio\_nsp_src"

os.makedirs(dest, exist_ok=True)

# Copy key source files
key_files = [
    "package.json",
    "forge.config.js",
    "tsconfig.json",
    "vite.config.ts",
    "content.js",
    "popup.js",
    "page-hook.js",
    "src/main/index.ts",
    "src/main/video-parser.ts",
    "src/main/video-download-manager.ts",
    "src/main/m3u8-downloader.ts",
    "src/main/aria2-manager.ts",
    "src/main/http-proxy.ts",
    "src/main/ipc-handlers.ts",
    "src/main/cookie-extractor.ts",
    "src/main/clipboard-monitor.ts",
    "src/main/store.ts",
    "src/preload/index.ts",
    "src/preload/float-preload.ts",
    "src/renderer/App.tsx",
    "src/renderer/float.tsx",
    "src/renderer/i18n.ts",
    "src/renderer/main.tsx",
]

for f in key_files:
    src = os.path.join(root, f)
    dst = os.path.join(dest, os.path.basename(f) if '/' not in f and '\\' not in f else f.replace('\\', '_').replace('/', '_'))
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"OK: {f} -> {dst}")
    else:
        print(f"MISS: {f}")

print("\nDone!")
