import json
import os

d = r"C:\Users\huangjiancheng\Desktop\生图生视频方法论"

# 平台列表
platforms = [f.replace(".md", "") for f in os.listdir(d) if f.endswith('.md')]

# 构建知识包: 给 knowledge-runtime 用的生图生视频方法论
knowledge_packs = {
    "img_video_methodology_master": {
        "domain": "image_video_generation",
        "title": "16平台生图生视频方法论总纲",
        "tags": ["image", "video", "prompt-engineering", "style-anchor", "multimodal"],
        "stages": ["3-keyframes", "5-character", "6-environment", "7-prop", "9-animation", "11-cinematic", "17-vfx"],
        "content": {
            "core_principles": [
                "图像控制空间，视频控制时间 — prompt 必须区分空间描述和时间描述",
                "负向 prompt 和正向 prompt 同等重要，缺一不可",
                "风格锚定必须具体到艺术家/作品/技术参数，不可以用虚词",
                "分层描述: 主体→环境→灯光→色调→细节→渲染→后处理",
                "视频额外: 运动方式→镜头运动→主体运动→环境变化→时间节奏"
            ],
            "platforms": platforms,
            "universal_negative_prompt": "ugly, deformed, blurry, low quality, distorted, bad anatomy, extra limbs, watermark, text, signature, oversaturated, flat lighting, poorly drawn, cartoon, amateur, grain, noise, lowres, bad proportions, disfigured, mutation, extra fingers, fused limbs",
        }
    }
}

# 注入 knowledge-runtime
v2 = r"C:\Users\huangjiancheng\CodeBuddy\新烬龙V2"
knowledge_dir = os.path.join(v2, "knowledge")
os.makedirs(knowledge_dir, exist_ok=True)

# 复制所有16个方法论文件到 V2 knowledge/ 目录
import shutil

target_dir = os.path.join(knowledge_dir, "methodologies")
os.makedirs(target_dir, exist_ok=True)
for fname in os.listdir(d):
    if fname.endswith('.md'):
        src = os.path.join(d, fname)
        dst = os.path.join(target_dir, fname)
        shutil.copy2(src, dst)
        print(f"  ✅ {fname}")

# 更新 prompts/registry.json
reg_path = os.path.join(v2, "prompts", "registry.json")
with open(reg_path, encoding='utf-8') as f:
    reg = json.load(f)

# 升级3-keyframes模板，吸取方法论精华
reg["stage_templates"]["3-keyframes"] = {
    "version": "3.0.0",
    "methodology": "16-platform-master-methodology",
    "role": "Cinematic Keyframe Artist",
    "core_principle": "图像控制空间 — 分层描述: 主体→环境→灯光→色调→细节→渲染→后处理",
    "instruction": """分两步生成:
Step 1 中文需求: 分析分镜 → 提取创作意图 → 选择视觉风格
Step 2 EN Image Prompt: 按7层结构描述 → 添加风格锚定 → 追加负向约束

7层结构: Subject(主体) / Environment(环境) / Lighting(灯光) / Color Palette(色调) / Details(细节) / Render(渲染质量) / Post-processing(后处理)
""",
    "format": """Shot X: 
ZH: [中文需求描述]
EN: [7层英文提示词], style anchor: [具体风格关键词], negative: [负向约束]""",
    "Negative Prompt (通用)": "ugly, deformed, blurry, low quality, distorted, bad anatomy, extra limbs, watermark, text, signature, oversaturated, flat lighting, poorly drawn, cartoon, amateur, grain, noise, lowres, bad proportions, disfigured, mutation, extra fingers, fused limbs",
    "min_length": 400,
    "quality_checks": ["has_7_layers", "has_negative_prompt", "style_specific_not_vague", "no_placeholder", "bilingual_format"],
    "knowledge_refs": ["knowledge/methodologies/生图方法论 全本.md", "knowledge/methodologies/GPT 生图生视频方法论 全本.md", "knowledge/methodologies/Gemini 生图生视频方法论 全本.md"]
}

# 更新系统提示，融入方法论总纲
reg["system"]["content"] += """

## 生图生视频方法论总纲 (16平台)

核心原则:
1. 图像控制空间，视频控制时间
2. 负向提示词和正向同等重要
3. 风格锚定必须具体(艺术家/作品/技术参数)，禁用虚词
4. 分层描述: 主体→环境→灯光→色调→细节→渲染→后处理
5. 视频额外: 运动方式→镜头运动→主体运动→环境变化→时间节奏
6. 每个提示词必须包含: 知识引用(引用方法论来源)

可用平台知识: """ + ", ".join(platforms)

reg["version"] = "4.0.0"
reg["methodologySources"] = [f"knowledge/methodologies/{f}" for f in os.listdir(target_dir)]

with open(reg_path, 'w', encoding='utf-8') as f:
    json.dump(reg, f, indent=2, ensure_ascii=False)

print(f"\n✅ prompts/registry.json v4.0.0")
print(f"   16套方法论 → knowledge/methodologies/")
print(f"   system.content 融入6条核心原则")
print(f"   3-keyframes 模板: 7层结构 + 双语格式")
print(f"{'='*60}")
