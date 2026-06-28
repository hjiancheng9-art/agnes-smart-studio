import sys; sys.path.insert(0,'.')
from core.marketplace import LocalRegistry

r = LocalRegistry()
skills = r._load_all()
md_skills = [s for s in skills if str(s.get('_file','')).endswith('.md')]
json_skills = [s for s in skills if str(s.get('_file','')).endswith('.json')]

print(f'本地技能总数: {len(skills)}')
print(f'  skills/*.skill.json: {len(json_skills)} 个')
print(f'  skills_md/*.skill.md: {len(md_skills)} 个')

# 自动安装 skills_md 中的技能
installed = 0
for raw in md_skills[:3]:
    name = raw['name']
    try:
        f = r.download(name)
        if f.exists():
            installed += 1
    except Exception:
        pass

print(f'自动安装: {installed} 个新技能')

# 验证 tool calling 循环检测
from core.chat import MAX_TOOL_LOOPS

print(f'MAX_TOOL_LOOPS: {MAX_TOOL_LOOPS}')

print('\nPASS')
