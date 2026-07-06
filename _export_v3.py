#!/usr/bin/env python3
"""Aggressive V2 template export — scans ALL JSON files"""
import os, json, sys

root = os.getcwd()
print(f"Scanning: {root}")

files = []
for r, ds, fs in os.walk(root):
    ds[:] = [d for d in ds if d not in ('node_modules', '__pycache__', '.git', '.codebuddy')]
    for f in fs:
        if f.endswith('.json'):
            files.append(os.path.join(r, f))

print(f"Total JSON files: {len(files)}")

templates = []
seen = set()

# Pattern 1: structured template
for fp in files:
    try:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
            c = fh.read(50000)
        data = json.loads(c)
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict): continue
            wf = item.get('workflow_id') or item.get('id', '')
            if not wf: continue
            if wf in seen: continue
            seen.add(wf)
            t = {
                'workflow_id': wf,
                'name': item.get('name', wf),
                'task_type': item.get('task_type', 'txt2img'),
                'category': item.get('category', 'image'),
                'inputs': [], 'models': [], 'tags': [],
            }
            rec = item.get('recommendation') or {}
            t['tags'] = rec.get('tags', []) if isinstance(rec, dict) else (rec if isinstance(rec, list) else [])
            for inp in item.get('inputs') or []:
                b = inp.get('binding') or {}
                if b.get('node_id') and b.get('class_type'):
                    t['inputs'].append({
                        'id': inp.get('id',''), 'type': inp.get('type','string'),
                        'default': inp.get('default'),
                        'min': inp.get('min'), 'max': inp.get('max'),
                        'binding': {'node_id': str(b['node_id']), 'class_type': b['class_type'], 'input': b.get('input','')}
                    })
            for m in item.get('models') or []:
                if isinstance(m, dict) and m.get('name'): t['models'].append(m['name'])
                elif isinstance(m, str): t['models'].append(m)
            templates.append(t)
            if len(templates) % 100 == 0: print(f"  {len(templates)}...")
    except: pass

# Pattern 2: raw ComfyUI workflow
if len(templates) < 20:
    print(f"\nPattern 1: {len(templates)} templates. Trying raw workflow scan...")
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                c = fh.read(50000)
            data = json.loads(c)
            if not isinstance(data, dict): continue
            has_ct = any(isinstance(v, dict) and 'class_type' in v for v in data.values())
            if not has_ct: continue
            nodes = {}
            for nid, node in data.items():
                if isinstance(node, dict) and 'class_type' in node:
                    ct = node['class_type']; nodes[ct] = nodes.get(ct, 0) + 1
            if len(nodes) < 3: continue
            wf = f"wf_{os.path.splitext(os.path.basename(fp))[0]}"
            if wf in seen: continue
            seen.add(wf)
            t = {
                'workflow_id': wf, 'name': ' + '.join(list(nodes.keys())[:5]),
                'task_type': 'txt2img' if 'KSampler' in nodes else 'other',
                'category': 'image', 'inputs': [], 'models': [], 'tags': list(nodes.keys()),
            }
            for nid, node in data.items():
                if not isinstance(node, dict) or 'class_type' not in node: continue
                inp, ct = node.get('inputs', {}), node['class_type']
                if ct == 'CLIPTextEncode' and 'text' in inp:
                    t['inputs'].append({'id':'prompt','type':'string','default':str(inp['text']) if isinstance(inp['text'],str) else '','binding':{'node_id':str(nid),'class_type':ct,'input':'text'}})
                elif ct == 'KSampler':
                    for k in ('seed','steps','cfg','denoise'):
                        if k in inp: t['inputs'].append({'id':k,'type':'float' if k in('cfg','denoise') else 'integer','default':inp[k] if isinstance(inp[k],(int,float)) else None,'binding':{'node_id':str(nid),'class_type':ct,'input':k}})
                elif ct == 'EmptyLatentImage':
                    for k in ('width','height'):
                        if k in inp: t['inputs'].append({'id':k,'type':'integer','default':inp[k] if isinstance(inp[k],(int,float)) else None,'binding':{'node_id':str(nid),'class_type':ct,'input':k}})
            if t['inputs']:
                templates.append(t)
        except: pass

final = list({t['workflow_id']: t for t in templates}.values())
with open('clean_templates.json', 'w', encoding='utf-8') as f:
    json.dump(final, f, ensure_ascii=False, indent=2)
print(f"\nDone: {len(final)} templates -> clean_templates.json")
cats = {}
for t in final:
    c = t.get('category', '?'); cats[c] = cats.get(c, 0) + 1
for c, n in sorted(cats.items(), key=lambda x: -x[1]):
    print(f"  {c}: {n}")
