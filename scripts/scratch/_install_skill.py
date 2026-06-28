import json
import sys
from pathlib import Path

sys.path.insert(0, '.')

import contextlib

from core.marketplace import CodeBuddyAdapter

cb = CodeBuddyAdapter()

if not cb.enabled:
    print("CodeBuddy 市场未检测到")
    print("提示: 安装 CodeBuddy 插件后，市场目录位于 ~/.codebuddy/skills-marketplace/skills/")
else:
    all_skills = cb._load_all()
    print(f"CodeBuddy 市场: {len(all_skills)} 个技能")

    # 列出前 10 个可安装的
    installed_names = set()
    for s in Path('skills').glob('*.skill.json'):
        try:
            d = json.loads(s.read_text(encoding='utf-8'))
            installed_names.add(d.get('name',''))
        except Exception:
            pass

    new_skills = {k:v for k,v in all_skills.items() if k not in installed_names}
    print(f"可安装: {len(new_skills)} 个新技能")

    for i, (name, raw) in enumerate(sorted(new_skills.items())[:10]):
        desc = (raw.get('description_zh') or raw.get('description',''))[:60]
        print(f"  {i+1}. {name} - {desc}")

    # 安装第一个新技能
    if new_skills:
        first = sorted(new_skills.keys())[0]
        print(f"\n正在安装: {first}...")
        try:
            result = cb.download(first)
            print(f"已安装到: {result}")
        except Exception as e:
            print(f"安装失败: {e}")

# 清理临时文件
for f in Path('.').glob('_*.py'):
    with contextlib.suppress(Exception):
        f.unlink()
for f in Path('.').glob('_*.txt'):
    with contextlib.suppress(Exception):
        f.unlink()
print("\n临时文件已清理")
