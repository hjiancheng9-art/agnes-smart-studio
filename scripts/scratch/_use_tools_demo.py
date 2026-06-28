"""实际使用 marketplace + codex 工具 - 输出到文件"""
import sys

sys.path.insert(0, '.')

lines = []

# 1. CodeBuddy 市场
from core.marketplace import CodeBuddyAdapter, LocalRegistry

cb = CodeBuddyAdapter()
local = LocalRegistry()

lines.append("=" * 60)
lines.append(f"CodeBuddy 市场: {'在线' if cb.enabled else '未找到'}")
lines.append("=" * 60)

if cb.enabled:
    all_cb = cb._load_all()
    lines.append(f"发现 {len(all_cb)} 个技能包")
    for name, raw in sorted(all_cb.items())[:25]:
        desc = (raw.get('description_zh') or raw.get('description',''))[:60]
        cat = raw.get('category','?')
        lines.append(f"  [{cat:12s}] {name:30s} {desc}")

# 2. 本地技能
local_skills = list(local.list_available())
lines.append(f"\n本地已安装: {len(local_skills)} 个")
by_cat = {}
for s in local_skills:
    by_cat.setdefault(s.category, []).append(s.name)
for cat, names in sorted(by_cat.items()):
    lines.append(f"  [{cat}] {len(names)} skills: {', '.join(names[:6])}...")

# 3. Codex 工具演示
from datetime import datetime

from core.codex_tools import create_html

skills_html = "\n".join(f"<li><b>{s.name}</b> [{s.category}] — {s.description[:80]}</li>" for s in sorted(local_skills, key=lambda s: s.name)[:20])
body = f"<h2>Agnes 技能市场报告</h2><p>{datetime.now().isoformat()[:19]}</p><h3>{len(local_skills)} 个已安装</h3><ul>{skills_html}</ul>"
path = create_html("Agnes Skill Market Report", body)
lines.append(f"\nHTML 报告: {path}")

# 4. 环境检查
from core.file_tools import env_check

lines.append(f"\n{env_check()}")

with open('_demo_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('done')
