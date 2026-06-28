
import httpx

KEY = "sk-9b7e2dadfc0a42c2aeec410eaabe9edb"

endpoints = [
    ("CodeBuddy skills", "https://api.codebuddy.tencent.com/v1/skills"),
    ("CodeBuddy plugins", "https://copilot.tencent.com/api/plugins"),
    ("GitHub marketplace", "https://raw.githubusercontent.com/codebuddy-ai/marketplace/main/registry.json"),
    ("GitHub skills", "https://raw.githubusercontent.com/codebuddy-ai/skills/main/index.json"),
]

results = []
for label, url in endpoints:
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {KEY}"},
                     timeout=httpx.Timeout(10, connect=6), trust_env=False)
        results.append(f"{label}: {r.status_code} {len(r.text)}chars")
        if r.status_code == 200:
            results.append(f"  FIRST 300: {r.text[:300]}")
    except Exception as e:
        results.append(f"{label}: {type(e).__name__}")

with open('_api_probe.txt','w',encoding='utf-8') as f:
    f.write('\n'.join(results))
    f.write('\n\nDONE')
