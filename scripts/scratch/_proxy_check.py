import json
import os
import re
import subprocess
import time
from pathlib import Path

import httpx

out = {}

for k in ['HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy']:
    v = os.environ.get(k,'')
    if v: out[k] = v

try:
    r = subprocess.run(['netsh','winhttp','show','proxy'], capture_output=True, text=True, timeout=8)
    out['winhttp'] = r.stdout.replace('\r','').replace('\n','|')[:300]
except Exception:
    pass

try:
    r = subprocess.run(['reg','query',r'HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings','/v','ProxyEnable'], capture_output=True, text=True, timeout=5)
    out['ie_proxy_enable'] = '0x1' in r.stdout
except Exception:
    pass
try:
    r = subprocess.run(['reg','query',r'HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings','/v','ProxyServer'], capture_output=True, text=True, timeout=5)
    m = re.search(r'REG_SZ\s+(.+)', r.stdout)
    if m: out['ie_proxy_server'] = m.group(1).strip()
except Exception:
    pass

for label, url in [("ddg","https://duckduckgo.com"),("bing","https://www.bing.com")]:
    t0=time.time()
    try:
        r=httpx.get(url, timeout=httpx.Timeout(10, connect=6), trust_env=False)
        out[f'{label}'] = f'OK {r.status_code} ({time.time()-t0:.1f}s)'
    except Exception as e:
        out[f'{label}'] = f'{type(e).__name__} ({time.time()-t0:.1f}s)'

out['httpx_default_trust_env'] = 'True - reads system proxy by default'

Path('_proxy_report.txt').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
