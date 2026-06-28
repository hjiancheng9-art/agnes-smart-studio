import os

import httpx

# reload env
os.environ['CODEBUDDY_API_KEY'] = 'ck_fph1efw1bxmo.NZs39LiQ5L9FgkF-Z77qk4KK00SXpqm8wd73fTmTkdE'
os.environ.pop('DOTENV_LOADED', None)

from dotenv import load_dotenv

load_dotenv(override=True)

KEY = os.getenv('CODEBUDDY_API_KEY','')
print(f"KEY loaded: {KEY[:15]}...")

endpoints = [
    ("marketplace plugins", "https://copilot.tencent.com/api/plugins"),
    ("marketplace skills", "https://copilot.tencent.com/api/skills"),
    ("marketplace v1", "https://copilot.tencent.com/v1/plugins"),
    ("API skills list", "https://api.codebuddy.tencent.com/v1/skills"),
    ("API plugins", "https://api.codebuddy.tencent.com/v1/plugins"),
    ("API marketplace", "https://api.codebuddy.tencent.com/v1/marketplace"),
]

results = []
for label, url in endpoints:
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {KEY}"},
                     timeout=httpx.Timeout(10, connect=6), trust_env=False,
                     follow_redirects=True)
        results.append(f"[{r.status_code}] {label}: {r.text[:200]}")
    except Exception as e:
        results.append(f"[FAIL] {label}: {type(e).__name__}")

with open('_cb_api_result.txt','w',encoding='utf-8') as f:
    f.write('\n'.join(results))
