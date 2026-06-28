"""Check if ComfyUI is running and accessible."""
import json
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8188"

# Test 1: Basic connectivity
print("=== Testing ComfyUI at", BASE_URL, "===")

# Test /system_stats
try:
    req = urllib.request.Request(f"{BASE_URL}/system_stats")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
        print(f"system_stats: status={resp.status}, content-type={content_type}, size={len(data)}")
        if "json" in content_type:
            print(json.dumps(json.loads(data), ensure_ascii=False, indent=2)[:600])
        else:
            print("Raw (first 300 bytes):", repr(data[:300]))
except urllib.error.URLError as e:
    print(f"system_stats: FAILED - {e.reason}")
except Exception as e:
    print(f"system_stats: ERROR - {e}")

# Test /queue
try:
    req = urllib.request.Request(f"{BASE_URL}/queue")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
        print(f"\nqueue: status={resp.status}, content-type={content_type}, size={len(data)}")
        if "json" in content_type:
            print(json.dumps(json.loads(data), ensure_ascii=False, indent=2)[:600])
        else:
            print("Raw:", repr(data[:200]))
except urllib.error.URLError as e:
    print(f"queue: FAILED - {e.reason}")
except Exception as e:
    print(f"queue: ERROR - {e}")

# Test /object_info (just count keys)
try:
    req = urllib.request.Request(f"{BASE_URL}/object_info")
    with urllib.request.urlopen(req, timeout=5) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
        print(f"\nobject_info: status={resp.status}, content-type={content_type}, size={len(data)}")
        if "json" in content_type:
            obj = json.loads(data)
            if isinstance(obj, dict):
                print(f"  Node types: {len(obj)}")
                print(f"  Sample keys: {list(obj.keys())[:10]}")
        else:
            print("Raw:", repr(data[:200]))
except urllib.error.URLError as e:
    print(f"object_info: FAILED - {e.reason}")
except Exception as e:
    print(f"object_info: ERROR - {e}")

print("\n=== Done ===")
