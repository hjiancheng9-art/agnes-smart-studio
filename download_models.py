"""模型下载脚本 — 用 hf-mirror.com"""
import urllib.request, os, time, sys

MIRROR = "https://hf-mirror.com"

MODELS = [
    {
        "name": "T5XXL FP8",
        "url": "/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors",
        "target": r"D:\ComfyUI_windows_portable\ComfyUI\models\clip\t5xxl_fp8_e4m3fn.safetensors",
        "size_gb": 4.7,
    },
    {
        "name": "Flux.1 Dev FP8",
        "url": "/Kijai/flux-fp8/resolve/main/flux1-dev-fp8.safetensors",
        "target": r"D:\ComfyUI_windows_portable\ComfyUI\models\unet\flux1-dev-fp8.safetensors",
        "size_gb": 11.3,
    },
    {
        "name": "4x-UltraSharp",
        "url": "/lokCX/4x-Ultrasharp/resolve/main/4x-UltraSharp.pth",
        "target": r"D:\ComfyUI_windows_portable\ComfyUI\models\upscale_models\4x-UltraSharp.pth",
        "size_gb": 0.044,
    },
]

def download(name, url, target, size_gb):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    temp = target + ".download"
    
    if os.path.exists(target):
        actual = os.path.getsize(target) / 1024 / 1024 / 1024
        if actual >= size_gb * 0.9:
            print(f"[{name}] ✅ 已存在 {actual:.1f}GB")
            return True
    
    resume = 0
    if os.path.exists(temp):
        resume = os.path.getsize(temp)
        print(f"[{name}] 📌 续传 {resume/1024/1024:.1f}MB")
    
    full_url = MIRROR + url
    print(f"[{name}] 📥 开始下载 {size_gb:.1f}GB...")
    
    try:
        headers = {"Range": f"bytes={resume}-"} if resume else {}
        req = urllib.request.Request(full_url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=60)
        total = int(resp.headers.get("content-length", 0)) + resume
        print(f"[{name}]   总大小: {total/1024/1024:.0f}MB")
    except Exception as e:
        print(f"[{name}] ❌ 连接失败: {e}")
        return False
    
    downloaded = resume
    start = time.time()
    mode = "ab" if resume else "wb"
    
    try:
        with open(temp, mode) as f:
            while True:
                chunk = resp.read(1048576)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                
                elapsed = time.time() - start
                if elapsed > 0:
                    speed = downloaded / 1024 / 1024 / elapsed
                    pct = downloaded / total * 100
                    eta = (total - downloaded) / (downloaded / elapsed) if downloaded > 0 else 0
                    sys.stdout.write(f"\r  [{name}] {pct:.1f}% | {downloaded/1024/1024:.0f}/{total/1024/1024:.0f}MB | {speed:.1f}MB/s | ETA {eta:.0f}s  ")
                    sys.stdout.flush()
        
        if os.path.exists(temp):
            if os.path.exists(target):
                os.remove(target)
            os.rename(temp, target)
            elapsed = time.time() - start
            print(f"\n  [{name}] ✅ 完成! {downloaded/1024/1024:.0f}MB in {elapsed:.0f}s ({downloaded/1024/1024/elapsed:.1f}MB/s)")
            return True
    except Exception as e:
        print(f"\n  [{name}] ❌ 下载中断: {e}")
        return False

if __name__ == "__main__":
    # 支持命令行选择下载哪个
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["all"]
    
    for m in MODELS:
        if targets[0] == "all" or m["name"] in targets or any(t in m["name"].lower() for t in targets):
            download(m["name"], m["url"], m["target"], m["size_gb"])
            print()
