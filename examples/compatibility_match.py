#!/usr/bin/env python3
"""示例 1: 探测 ComfyUI 环境 + 匹配兼容蓝图"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comfyflow_compiler.capability.snapshot import probe_comfyui
from comfyflow_compiler.capability.compatibility import BlueprintCompatibilityMatcher
from comfyflow_compiler.blueprint.loader import BlueprintLoader

# 1. 探测
print("🔍 探测 ComfyUI...")
snap = probe_comfyui()
s = snap.summary
print(f"   在线: {s['comfyui_online']} | 版本: {s['version']}")
print(f"   节点: {s['nodes']} | 模型: {s['models']}")

if not snap.comfyui_online:
    print("   ⚠️ ComfyUI 离线，跳过兼容性匹配")
    sys.exit(0)

# 2. 加载蓝图
loader = BlueprintLoader()
all_bp = loader.load_all()
print(f"\n📋 共 {len(all_bp)} 个蓝图")

# 3. 匹配兼容性
matcher = BlueprintCompatibilityMatcher(snap)
scored = matcher.rank(all_bp)

print("\n🏆 兼容性 Top 5:")
for s in scored[:5]:
    flag = "✅" if s.compatible else "⚠️"
    print(f"   {flag} {s.blueprint_id:40s} score={s.overall:.2f}")
    if s.missing_nodes:
        print(f"       缺失节点: {', '.join(s.missing_nodes)}")
    if s.missing_models:
        print(f"       缺失模型: {', '.join(s.missing_models)}")

print("\n✨ 完成")
