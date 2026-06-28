import os
import re
import subprocess

report = {}

# env proxy vars
for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']:
    v = os.environ.get(k)
    if v: report[k] = v

# netsh
try:
    r = subprocess.run(['netsh','winhttp','show','proxy'], capture_output=True, text=True, timeout=6)
    report['winhttp'] = r.stdout.strip()[:400]
except Exception as e:
    report['winhttp'] = str(e)

# reg
try:
    r = subprocess.run(['reg','query',r'HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings','/v','ProxyServer'], capture_output=True, text=True, timeout=6)
    m = re.search(r'REG_SZ\s+(.+)', r.stdout)
    if m: report['ie_proxy'] = m.group(1).strip()
except Exception as e:
    report['ie_reg_error'] = str(e)

with open('proxy_info.txt', 'w', encoding='utf-8') as f:
    for k,v in report.items():
        f.write(f'{k}: {v}\n')
