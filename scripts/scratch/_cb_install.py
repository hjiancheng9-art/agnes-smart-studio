import sys; sys.path.insert(0,'.')
from core.marketplace import get_marketplace

lines = []
mp = get_marketplace()

lines.append(f"remote online: {mp.remote.enabled}")
lines.append(f"registry: {mp.remote._registry_url}")
lines.append(f"local codebuddy: {mp.codebuddy.enabled}")

plugins = mp.remote._fetch_registry()
lines.append(f"remote plugins: {len(plugins)}")

for p in plugins[:5]:
    lines.append(f"  {p.get('name','?')}")

if plugins:
    target = plugins[0].get('name','')
    lines.append(f"installing: {target}")
    try:
        ok = mp.install(target, source="remote")
        lines.append(f"result: {'ok' if ok else 'fail'}")
    except Exception as e:
        lines.append(f"error: {e}")

lines.append(f"total available: {len(mp.list_all())}")
lines.append(f"total installed: {len(mp.list_installed())}")

with open('_cb_out.txt','w',encoding='utf-8') as f:
    f.write('\n'.join(lines))
