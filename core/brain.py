"""智能大脑 - 意图识别、Prompt增强、分镜生成（基于 agnes-2.0-flash + Thinking模式）"""

import json
from typing import Optional

from .client import AgnesClient


# ── 甜点区预设模板 ──────────────────────────────────
# 针对高频场景的预调优提示词，减少穿模/多手等常见问题
SWEET_SPOT_TEMPLATES = {
    "portrait": {
        "name": "人像写真",
        "suffix": "professional portrait photography, studio lighting, soft Rembrandt lighting, shallow depth of field, 85mm lens, sharp focus on eyes, skin detail, photorealistic, 8k, high detail",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, missing fingers, wrong hand anatomy, extra arms, extra limbs, crossed eyes, asymmetric eyes, deformed face, distorted face, ugly, bad anatomy, wrong proportions, clipping, mesh penetration, watermark, text, low quality, blurry",
        "description": "专业人像摄影，避免多手/穿模",
    },
    "full_body": {
        "name": "全身人物",
        "suffix": "full body shot, standing pose, natural proportions, dynamic lighting, photorealistic, high detail, 8k resolution, professional color grading",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, missing fingers, wrong hand anatomy, extra arms, extra limbs, limb cutoff, body out of frame, head out of frame, bad anatomy, wrong proportions, clipping, intersecting bodies, mesh penetration, fused bodies, merged bodies, floating limbs, disconnected limbs, watermark, text, low quality, blurry",
        "description": "全身人物，重点防穿模/断肢",
    },
    "action": {
        "name": "动作场景",
        "suffix": "dynamic action pose, motion blur, dramatic lighting, cinematic composition, photorealistic, high detail, 8k",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, wrong hand anatomy, extra arms, extra limbs, bad anatomy, distorted pose, clipping, intersecting bodies, mesh penetration, fused bodies, floating limbs, disconnected limbs, static, frozen, blurry, low quality, watermark",
        "description": "动作/打斗场景，防穿模+动态",
    },
    "animal": {
        "name": "动物",
        "suffix": "wildlife photography, natural habitat, telephoto lens, golden hour lighting, photorealistic, detailed fur/feathers, 8k, national geographic style",
        "negative": "extra limbs, extra heads, mutated anatomy, deformed body, wrong proportions, clipping, mesh penetration, watermark, text, low quality, blurry, cartoon, anime",
        "description": "动物摄影，防多肢体",
    },
    "landscape": {
        "name": "风景",
        "suffix": "landscape photography, wide angle, golden hour, dramatic sky, deep depth of field, vivid colors, 8k, professional color grading, hdr",
        "negative": "blurry, low quality, watermark, text, signature, overexposed, underexposed, noise, grain, compression artifacts, distorted perspective",
        "description": "风景摄影，注重画质",
    },
    "food": {
        "name": "美食",
        "suffix": "food photography, close-up, studio lighting, shallow depth of field, vibrant colors, steam, fresh ingredients, professional styling, 8k",
        "negative": "blurry, low quality, watermark, text, unappetizing, messy, dirty plate, wrong colors, cartoon, anime",
        "description": "美食摄影，注重色泽",
    },
    "anime": {
        "name": "动漫风格",
        "suffix": "anime style, high quality anime illustration, detailed eyes, clean lineart, vibrant colors, studio lighting, masterpiece, best quality",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, missing fingers, wrong hand anatomy, extra arms, extra limbs, bad anatomy, wrong proportions, low quality, worst quality, blurry, watermark, text, realistic, photorealistic",
        "description": "动漫风格，防多手+风格偏离",
    },
}

# 视频甜点区预设
SWEET_SPOT_VIDEO_TEMPLATES = {
    "portrait_video": {
        "name": "人物视频",
        "suffix": "subtle head movement, gentle expression change, soft lighting, cinematic, 24fps, smooth motion",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, fused fingers, wrong hand anatomy, extra arms, extra limbs, bad anatomy, face morphing, body morphing, clipping, intersecting bodies, mesh penetration, flickering, jittery motion, temporal inconsistency, ghosting, double image, static, frozen, blurry, low quality, watermark",
        "description": "人物微动视频，防面部变形",
    },
    "action_video": {
        "name": "动作视频",
        "suffix": "dynamic action, fast camera movement, motion blur, dramatic lighting, cinematic, 24fps",
        "negative": "extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, extra arms, extra limbs, bad anatomy, distorted pose, face morphing, body morphing, clipping, intersecting bodies, mesh penetration, fused bodies, flickering, jittery motion, temporal inconsistency, ghosting, double image, frozen, static, blurry, low quality, watermark, frame skipping, unnatural movement",
        "description": "动作视频，防穿模+时序问题",
    },
    "camera_pan": {
        "name": "镜头运动",
        "suffix": "slow camera pan, tracking shot, smooth movement, cinematic, 24fps, steady cam",
        "negative": "jittery motion, shaky camera, frame skipping, flickering, temporal inconsistency, ghosting, double image, morphing artifacts, static, frozen, blurry, low quality, watermark",
        "description": "纯镜头运动，防抖动+闪烁",
    },
}


# ── 失败修复映射表 ──────────────────────────────────
# 来源：新烬龙V2 negative-prompt-rules.md —— 常见失败现象 → 精准修复关键词
NEGATIVE_REPAIR_MAP = {
    "text_drift": {
        "symptoms": ["出现文字", "出现图表", "出现infographic", "出现logo", "出现typography"],
        "repair_keywords": "pure environment, no text, no letters, no typography, no logo, no watermark, no infographic, no chart, no labels",
    },
    "cluttered": {
        "symptoms": ["画面太满", "主体太大", "构图拥挤", "裁切关键元素"],
        "repair_keywords": "clean center, negative space, fewer objects, simplified composition, breathing room, well framed",
    },
    "too_dark": {
        "symptoms": ["太暗", "欠曝", "看不清主体", "死黑区域"],
        "repair_keywords": "controlled rim light, readable midtones, balanced exposure, fill light, brighter shadows, lifted blacks",
    },
    "too_bright": {
        "symptoms": ["过曝", "太亮", "高光溢出", "高光丢失细节"],
        "repair_keywords": "highlight control, darker center, reduced exposure, controlled specular highlights, detail in highlights",
    },
    "anatomy_failure": {
        "symptoms": ["多余手指", "多余手臂", "手部畸形", "面部变形", "比例错误"],
        "repair_keywords": "perfect hand anatomy, five fingers each hand, symmetrical face, correct human proportions, natural pose, anatomically correct",
    },
    "penetration": {
        "symptoms": ["穿模", "物体穿透", "身体融合", "身体交叉重叠", "几何变形"],
        "repair_keywords": "solid objects, proper occlusion, no clipping, no mesh penetration, separate bodies, clear boundaries, distinct geometries",
    },
    "identity_drift": {
        "symptoms": ["身份漂移", "面部不一致", "角色变化", "人种变化"],
        "repair_keywords": "consistent face, identity lock, same person, consistent appearance, character continuity, same ethnicity",
    },
    "video_instability": {
        "symptoms": ["闪烁", "抖动", "帧跳跃", "鬼影", "运动不自然", "画面撕裂"],
        "repair_keywords": "stable, smooth motion, no flickering, no jitter, no ghosting, temporal consistency, natural movement, consistent frame pacing",
    },
}

# ── 实体类型推断表 ──────────────────────────────────
# 来源：新烬龙V2 asset-continuity.md + common.js inferPrimaryCharacterEntity()
# 9种非人实体：关键词 → 表面材质策略
ENTITY_TYPE_MAP = {
    "spirit": {
        "name_cn": "灵体",
        "keywords": ["灵体", "幽灵", "鬼魂", "亡灵", "魂魄", "幻影",
                     "spirit", "ghost", "soul", "phantom", "apparition", "wraith", "specter"],
        "surface_policy": "translucent, ethereal, luminous or shadowy body; no solid flesh, no human skin tone",
    },
    "energy_body": {
        "name_cn": "能量体",
        "keywords": ["能量体", "光灵", "火焰灵", "暗影灵", "能量生命",
                     "energy body", "light being", "flame being", "shadow being", "energy entity"],
        "surface_policy": "pure energy form, luminous aura, particle body, no solid mass, no organic texture",
    },
    "anthropomorphic": {
        "name_cn": "拟人化",
        "keywords": ["拟人", "兽人", "兽耳", "福瑞", "毛绒人", "活体傀儡", "活玩偶",
                     "anthro", "anthropomorphic", "humanoid", "furry", "beastman", "living puppet",
                     "animated doll", "kemono", "fursona"],
        "surface_policy": "fur, scales, feathers, or shell surface; lock pelt pattern and species markers; no human skin tone",
    },
    "robot": {
        "name_cn": "机器人",
        "keywords": ["机器人", "机甲", "仿生人", "无人机", "机械体",
                     "robot", "android", "mecha", "machine", "drone", "cyborg", "automaton"],
        "surface_policy": "metal, composite, or synthetic shell; lock panel lines, material finish, and mechanical joints; no organic skin",
    },
    "AI": {
        "name_cn": "AI虚拟体",
        "keywords": ["AI化身", "全息", "虚拟人", "数字人",
                     "ai avatar", "hologram", "digital avatar", "virtual being", "ai entity"],
        "surface_policy": "holographic projection, data particles, interface glow; no physical mass, no solid body",
    },
    "creature": {
        "name_cn": "异兽/生物",
        "keywords": ["怪兽", "怪物", "龙", "异形", "魔兽", "巨兽", "神话生物",
                     "monster", "creature", "beast", "dragon", "alien", "demon", "kaiju", "chimera"],
        "surface_policy": "biological but non-human; lock species anatomy, scale/fur/chitin pattern, and body structure",
    },
    "animal": {
        "name_cn": "动物",
        "keywords": ["猫", "狗", "鸟", "鱼", "虎", "马", "动物",
                     "cat", "dog", "bird", "fish", "tiger", "horse", "animal", "wolf", "bear", "rabbit"],
        "surface_policy": "natural animal anatomy; lock species proportions, coat/feather pattern, and eye structure",
    },
    "vehicle_character": {
        "name_cn": "活体载具",
        "keywords": ["活体载具", "有意识载具", "会说话的车", "船灵",
                     "living vehicle", "sentient vehicle", "talking car", "ship spirit", "locomotive entity"],
        "surface_policy": "functional vehicle form with expressive details; lock vehicle type, markings, and transformation cues",
    },
    "object_character": {
        "name_cn": "物品角色",
        "keywords": ["活物", "附身物品", "会说话的物品",
                     "living object", "talking object", "possessed object", "animated item"],
        "surface_policy": "inanimate object form with expressive features; lock object identity, material, and animation style",
    },
}

# ── 帅哥美女人像通道 ──────────────────────────────────
# 来源：新烬龙V2 character-clothing.md + AI视频生成提示词知识库.md
# 独立于非人实体通道，只服务高颜值人像
BEAUTY_PORTRAIT_MAP = {
    "handsome": {
        "name_cn": "帅哥",
        "keywords": ["帅哥", "帅气", "英俊", "俊朗", "型男", "美男", "高颜值男",
                     "handsome", "cool guy", "good-looking man", "attractive male",
                     "帅哥美女", "高颜值"],
        "aura_options": ["清冷", "贵气", "英气", "少年感", "禁欲感"],
        "focus_points": "眉骨、鼻梁、下颌线、气场、低机位压迫感、侧脸锋利度",
        "angle_rules": {
            "front": "干净端正，身份识别基准",
            "45deg": "最立体，骨相+轮廓+锋利度最强",
            "side": "突出鼻梁、眉骨和下颌线，气质锋利度",
            "low_angle": "气场更强，成熟感，角色控制力",
            "high_angle": "更显克制和少年感",
        },
        "template_suffix": "male high-appeal subject, {aura} aura, clean front, 45-degree most dimensional, side profile highlighting brow bone, nose bridge and jawline, low-angle for commanding presence, expression restrained but sharp, defined bone structure, no template face, {aura}-driven styling",
        "template_negative": "template face, generic male, soft features, feminine jawline, undefined bone structure, exaggerated expression, model catalog pose, same-face syndrome, bland features",
    },
    "beauty": {
        "name_cn": "美女",
        "keywords": ["美女", "漂亮", "美丽", "绝色", "倾国", "国色天香", "貌美", "高颜值女",
                     "俏丽", "仙气", "明艳", "御姐", "萝莉",
                     "beauty", "beautiful woman", "gorgeous female", "attractive woman",
                     "帅哥美女", "高颜值"],
        "aura_options": ["清冷", "明艳", "温柔", "贵气", "氛围感"],
        "focus_points": "面部留白、骨相、唇线、眼神层次、45度立体感、逆光轮廓美",
        "angle_rules": {
            "front": "精致但不死板，身份识别基准",
            "45deg": "最出片，骨相+立体感最强",
            "side": "突出鼻梁、唇线和骨相",
            "low_angle": "增强气场",
            "high_angle": "柔和感、脆弱感、被凝视感",
        },
        "template_suffix": "female high-appeal subject, {aura} aura, refined front, 45-degree most photogenic, side profile highlighting nose bridge, lip line and bone structure, high-angle for vulnerability and gaze, backlit contour beauty, layered gaze, restrained but present expression, facial negative space and bone structure both compelling, no template face, {aura}-driven styling",
        "template_negative": "template face, generic beauty, plain features, hard expression, lifeless eyes, overdone makeup, model catalog pose, same-face syndrome, bland features, masculine jawline",
    },
}

# ── 实体专属甜点区模板 ──────────────────────────────────
# 每种非人实体的正面/负面甜点区（图+视频）
ENTITY_SWEET_SPOT_TEMPLATES = {
    "spirit": {
        "image": {
            "suffix": "ethereal translucent figure, soft inner glow, flowing mist-like edges, floating pose, otherworldly presence, volumetric light, atmospheric, 8k, high detail",
            "negative": "solid body, heavy physical mass, grounded stance, human skin, organic texture, flesh tone, realistic human proportions, extra limbs, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "gentle floating motion, ethereal drift, soft pulsing glow, translucent body phase, atmospheric, 24fps, smooth motion",
            "negative": "solid body, heavy landing, grounded walk, physical impact, flesh deformation, clipping, flickering, jittery motion, temporal inconsistency, ghosting, low quality",
        },
    },
    "energy_body": {
        "image": {
            "suffix": "pure luminous energy form, particle body, radiant aura, no solid mass, floating energy core, prismatic light dispersion, 8k, high detail",
            "negative": "solid body, organic texture, flesh, skin, heavy mass, grounded, physical contact, realistic human proportions, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "energy pulsing motion, particle flow, slow orbit, light fluctuation, atmospheric, 24fps, smooth motion",
            "negative": "solid body collision, physical impact, organic movement, flesh deformation, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "anthropomorphic": {
        "image": {
            "suffix": "anthropomorphic character, species-accurate anatomy, detailed fur/scales/feathers, expressive eyes, natural pose, 8k, high detail",
            "negative": "extra fingers, extra hands, wrong digit count, human skin, bare flesh tone, mutated anatomy, deformed paws, clipping, mesh penetration, watermark, text, low quality",
        },
        "video": {
            "suffix": "natural anthropomorphic movement, species-appropriate motion, fluid animation, 24fps, smooth motion",
            "negative": "extra fingers, wrong digit count, human skin, bare flesh, mutated anatomy, face morphing, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "robot": {
        "image": {
            "suffix": "mechanical body, precise panel lines, synthetic shell, metallic finish, mechanical joints, sensor array, 8k, high detail",
            "negative": "organic skin, flesh, human proportions, soft tissue, body hair, realistic human face, clipping, mesh penetration, watermark, text, low quality",
        },
        "video": {
            "suffix": "mechanical precision movement, servo-driven motion, rigid joint articulation, 24fps, smooth motion",
            "negative": "organic skin, flesh, soft tissue movement, body hair, realistic human face morphing, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "AI": {
        "image": {
            "suffix": "holographic entity, data particle body, interface glow, digital avatar, translucent projection, 8k, high detail",
            "negative": "solid body, physical mass, organic texture, flesh, skin, grounded, realistic human proportions, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "holographic flicker, data stream motion, projection phase shift, digital presence, 24fps, smooth motion",
            "negative": "solid body, physical mass, organic movement, flesh deformation, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "creature": {
        "image": {
            "suffix": "detailed creature anatomy, species-accurate body structure, natural pose, environmental context, 8k, high detail",
            "negative": "extra limbs, wrong anatomy for species, human-like hands, human face on creature, clipping, mesh penetration, watermark, text, low quality",
        },
        "video": {
            "suffix": "natural creature movement, species-appropriate locomotion, fluid animation, 24fps, smooth motion",
            "negative": "extra limbs, wrong anatomy, human-like movement, face morphing, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "vehicle_character": {
        "image": {
            "suffix": "sentient vehicle design, expressive front face, functional vehicle body with personality, anthropomorphic vehicle features, 8k, high detail",
            "negative": "ordinary vehicle, no personality, broken mechanics, wrong proportions, floating parts, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "expressive vehicle movement, personality-driven motion, responsive driving, 24fps, smooth motion",
            "negative": "ordinary vehicle motion, no personality, mechanical failure, parts falling off, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
    "object_character": {
        "image": {
            "suffix": "animated object character, expressive features on inanimate form, clear object identity, personality cues, 8k, high detail",
            "negative": "ordinary object, no personality, broken object, wrong proportions, floating parts, clipping, watermark, text, low quality",
        },
        "video": {
            "suffix": "expressive object animation, personality-driven object motion, bouncing or hopping, 24fps, smooth motion",
            "negative": "ordinary object, static, no animation, broken, wrong proportions, clipping, flickering, jittery motion, temporal inconsistency, low quality",
        },
    },
}

# ── 帅哥美女专属甜点区 ──────────────────────────────────
# 来源：新烬龙V2 character-clothing.md + LTX2.3生产甜点区规格.md
BEAUTY_SWEET_SPOT_TEMPLATES = {
    "handsome": {
        "image": {
            "suffix": "male high-appeal portrait, sharp bone structure, defined jawline, prominent brow bone, straight nose bridge, restrained expression, dimensional lighting, 85mm portrait lens, shallow depth of field, backlit rim light, cinematic, photorealistic, 8k, high detail",
            "negative": "template face, generic male, soft features, feminine jawline, undefined bone structure, exaggerated expression, extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, face distortion, asymmetric eyes, bad anatomy, wrong proportions, watermark, text, low quality, blurry, model catalog pose, same-face syndrome",
        },
        "video": {
            "suffix": "subtle head turn, gentle expression shift, restrained gaze movement, backlit rim light on hair, cinematic portrait video, identity-locked face, 24fps, smooth motion",
            "negative": "template face, face morphing, identity drift, exaggerated expression, extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, body morphing, clipping, flickering, jittery motion, temporal inconsistency, ghosting, double image, static, frozen, blurry, low quality, watermark, same-face syndrome",
        },
    },
    "beauty": {
        "image": {
            "suffix": "female high-appeal portrait, refined bone structure, elegant lip line, layered gaze, facial negative space, 45-degree photogenic angle, backlit contour, soft Rembrandt lighting, 85mm portrait lens, shallow depth of field, cinematic, photorealistic, 8k, high detail",
            "negative": "template face, generic beauty, plain features, hard expression, lifeless eyes, overdone makeup, extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, face distortion, asymmetric eyes, bad anatomy, wrong proportions, watermark, text, low quality, blurry, model catalog pose, same-face syndrome, masculine jawline",
        },
        "video": {
            "suffix": "subtle gaze shift, gentle head tilt, soft hair movement, backlit contour glow, cinematic portrait video, identity-locked face, 24fps, smooth motion",
            "negative": "template face, face morphing, identity drift, hard expression, extra fingers, extra hands, mutated hands, deformed hands, wrong hand anatomy, body morphing, clipping, flickering, jittery motion, temporal inconsistency, ghosting, double image, static, frozen, blurry, low quality, watermark, same-face syndrome, masculine features",
        },
    },
}

# ── 实体专属失败修复映射 ──────────────────────────────────
# 来源：新烬龙V2 asset-continuity.md + business-brain-main-trunk.md
# 每种非人实体的专属失败模式 → 精准修复关键词
ENTITY_NEGATIVE_REPAIR_MAP = {
    "spirit": {
        "solidification": {
            "symptoms": ["灵体变实体", "有皮肤质感", "接地站立", "物理碰撞"],
            "repair_keywords": "ethereal, translucent, phase through matter, floating, no physical mass, intangible, non-corporeal",
        },
        "identity_drift": {
            "symptoms": ["灵体面目模糊", "形态不稳定", "随机变形"],
            "repair_keywords": "consistent ethereal form, stable ghostly silhouette, locked spirit identity, same luminous core",
        },
    },
    "energy_body": {
        "solidification": {
            "symptoms": ["能量体凝固", "出现实体质量", "物理碰撞"],
            "repair_keywords": "pure energy, no solid mass, luminous particles, radiant form, intangible light body",
        },
        "color_drift": {
            "symptoms": ["能量色调漂移", "颜色不稳定", "随机变色"],
            "repair_keywords": "consistent energy hue, locked color signature, stable luminous palette",
        },
    },
    "anthropomorphic": {
        "species_drift": {
            "symptoms": ["物种特征漂移", "兽耳消失", "皮毛变皮肤", "尾巴消失"],
            "repair_keywords": "consistent species features, locked fur pattern, species-accurate ears and tail, no human skin",
        },
        "digit_error": {
            "symptoms": ["手指/爪数量错误", "人类手代替兽爪", "手掌畸形"],
            "repair_keywords": "species-accurate digit count, correct paw anatomy, proper claw structure",
        },
    },
    "robot": {
        "organic_drift": {
            "symptoms": ["机器人出现皮肤", "有机质感", "肌肉线条"],
            "repair_keywords": "purely mechanical, synthetic shell, no organic tissue, no skin, metal and composite materials only",
        },
        "joint_failure": {
            "symptoms": ["关节穿模", "机械结构错误", "部件漂浮"],
            "repair_keywords": "proper mechanical joints, correct articulation, solid panel alignment, no floating parts",
        },
    },
    "AI": {
        "physicalization": {
            "symptoms": ["全息体变实体", "出现物理质量", "实体碰撞"],
            "repair_keywords": "holographic projection only, no physical mass, data particle body, digital entity, translucent",
        },
    },
    "creature": {
        "anatomy_drift": {
            "symptoms": ["肢体数量变化", "物种解剖错误", "人类化"],
            "repair_keywords": "species-accurate anatomy, correct limb count, proper creature body structure, no humanization",
        },
        "scale_proportion": {
            "symptoms": ["比例失衡", "头部过大/过小", "四肢比例错误"],
            "repair_keywords": "correct species proportions, anatomically accurate creature, proper scale relationship",
        },
    },
    "vehicle_character": {
        "loss_of_personality": {
            "symptoms": ["失去表情", "变成普通载具", "人格消失"],
            "repair_keywords": "expressive vehicle face, personality markers, sentient features, character-driven design",
        },
    },
    "object_character": {
        "loss_of_personality": {
            "symptoms": ["失去表情", "变成普通物品", "人格消失"],
            "repair_keywords": "expressive object features, personality markers, animated character cues, living object design",
        },
    },
}

# ── 帅哥美女专属失败修复 ──────────────────────────────────
# 来源：新烬龙V2 character-clothing.md 高概念关键帧规则 + 人像通道规则
BEAUTY_NEGATIVE_REPAIR_MAP = {
    "handsome": {
        "template_face": {
            "symptoms": ["模板脸", "五官无锋利度", "没有骨相差异", "标准AI脸"],
            "repair_keywords": "defined bone structure, sharp jawline, prominent brow bone, individual facial topology, no generic face, character-specific features",
        },
        "lost_sharpness": {
            "symptoms": ["轮廓柔化", "锋利度消失", "下颌线模糊", "眉骨不突出"],
            "repair_keywords": "sharp jawline definition, prominent brow ridge, chiseled cheekbones, clear facial angles, strong bone structure",
        },
        "action_contamination": {
            "symptoms": ["混入战斗动作", "出招姿势", "硬摆拍", "夸张武打体态"],
            "repair_keywords": "portrait pose, natural stance, restrained expression, no combat pose, no exaggerated gesture, human portrait channel",
        },
    },
    "beauty": {
        "template_face": {
            "symptoms": ["模板脸", "五官无特色", "没有骨相留白", "标准AI脸"],
            "repair_keywords": "refined bone structure, elegant facial proportions, proper negative space, individual facial topology, no generic face, character-specific beauty",
        },
        "lost_contour": {
            "symptoms": ["逆光轮廓消失", "骨相平面化", "面部留白不足", "45度不立体"],
            "repair_keywords": "backlit contour definition, dimensional bone structure, proper facial negative space, photogenic 45-degree angle, layered gaze depth",
        },
        "action_contamination": {
            "symptoms": ["混入战斗动作", "出招姿势", "硬摆拍", "夸张武打体态"],
            "repair_keywords": "portrait pose, natural graceful stance, restrained expression, no combat pose, no exaggerated gesture, human portrait channel",
        },
    },
}

# ── 帅哥美女生产路由规则 ──────────────────────────────────
# 来源：新烬龙V2 LTX2.3生产甜点区规格.md + LTX2.3首帧驱动I2V规格.md
BEAUTY_PRODUCTION_RULES = {
    "image": {
        "method": "高概念关键帧 + 甜点区叠加",
        "principles": [
            "先写气质，再写五官；先写世界感，再写服装",
            "角色必须嵌入空间，不是孤立摆拍",
            "帅气或美感通过机位、逆光、轮廓、材质和克制表情完成，不靠空泛形容词",
            "高颜值角色不要模板脸，要写骨相差异、气场方向和气质层级",
        ],
        "high_concept_templates": {
            "cosmic_temple": {
                "name_cn": "宇宙神殿角色版",
                "prompt": "角色不是单独摆拍，而是落在一个垂直神圣秩序里。画面中心要有竖直光核、能量塔或仪式核心，外圈有环形平台、轨道或分层建筑。人物站在平台、台阶、基座或仪式台上，作为进入世界的入口。人物气质要克制、庄严、干净，背影、三分之二侧身、回头或抬头比纯正脸更有世界感。发丝、衣摆、披帛和轮廓光要顺着光流方向走，让人物和空间合成一体。",
            },
            "entering_light_core": {
                "name_cn": "进入光核角色版",
                "prompt": "角色不是站在镜头前摆拍，而是在走向、凝视或接近世界中心。人物最好用背影、侧背、三分之二侧、回头或抬头，动作轻，但方向明确。前景平台、中心光核、环形轨道和层级建筑共同定义人物所处的秩序。女角色用长发、披帛、裙摆或轻纱接住光流；男角色用肩线、长衣和挺直站姿接住气场。最后的感觉应该是：人物被这个世界收纳进去，而不是被单独拿出来展示。",
            },
        },
        "formulas": {
            "standard": "高颜值主体 + 人像气质 + 骨相轮廓 + 空间秩序 + 轻动作 + 情绪克制",
            "high_concept": "世界观锚点 + 主体气质 + 空间层级 + 中心视觉核 + 单一主动作 + 镜头推进/环绕 + 连续性锁定",
        },
    },
    "video": {
        "method": "逐镜 compact",
        "i2v_strength": "0.70-0.72（首选0.72）",
        "i2v_allowed_actions": ["眼神", "呼吸", "轻微转头", "整理衣领"],
        "default_route": "traditional compact + I2V",
        "principles": [
            "帅哥美女不要和非人怪物、复杂蓝图、密集战术、奇观动作混写",
            "动作只给微动作：眼神、呼吸、轻微转头、整理衣领",
            "身份锁定 > 动作表现",
        ],
    },
    "isolation_rules": {
        "description": "帅哥美女是独立人像通道，不和非人主体、战斗结构、怪诞构想、武器动作或载具动作混写",
        "rules": [
            "任务如果是帅哥美女，优先走人像审美，不先套战斗逻辑",
            "可以有世界感，但世界感只做背景秩序，不抢人物主位",
            "可以有轻动作，但不做出招姿势、硬摆拍或夸张武打体态",
            "奇观感优先靠骨相、轮廓光、逆光边缘、空间层级和材质统一",
            "如果同一需求同时出现'高颜值人像'和'非人/怪诞/战斗'，必须拆成两条提示词",
        ],
    },
}

# ── 实体嫁接目标 ──────────────────────────────────
# 来源：新烬龙V2 creative-leap.md + thinking-engine.js
GRAFT_TARGETS = {
    "mechanical_body": {
        "name_cn": "机械体",
        "description": "将人类角色嫁接为机械表演体——金属/复合材料外壳、伺服关节、传感器列阵",
        "target_entity": "robot",
    },
    "energy_form": {
        "name_cn": "能量形态",
        "description": "将人类角色嫁接为能量体——粒子身躯、发光核心、无形质体",
        "target_entity": "energy_body",
    },
    "digital_avatar": {
        "name_cn": "数字分身",
        "description": "将人类角色嫁接为AI虚拟体——全息投影、数据粒子、数字界面",
        "target_entity": "AI",
    },
    "mythical_beast": {
        "name_cn": "神话异兽",
        "description": "将人类角色嫁接为神话生物——非人解剖、鳞/角/翼、超自然形态",
        "target_entity": "creature",
    },
    "symbiotic_organism": {
        "name_cn": "共生有机体",
        "description": "将人类角色嫁接为拟人化共生体——混合生物特征、拟态表面",
        "target_entity": "anthropomorphic",
    },
    "shadow_entity": {
        "name_cn": "暗影实体",
        "description": "将人类角色嫁接为灵体——暗影质体、半透明、非物质化",
        "target_entity": "spirit",
    },
    "liquid_metal": {
        "name_cn": "液态金属",
        "description": "将人类角色嫁接为液态机械体——流动金属表面、可变形关节",
        "target_entity": "robot",
    },
    "crystalline_being": {
        "name_cn": "晶体生命",
        "description": "将人类角色嫁接为晶体能量体——透明棱面、折射光线、几何生长",
        "target_entity": "energy_body",
    },
}

# ── 超越常人思维方法知识库 ──────────────────────────────────
# 来源：新烬龙V2 跨域嫁接创意引擎 / 反模式思维层 / 思维技法层 / AI特化思维层 / 创意飞跃包 / 游戏动作总控知识库

CREATIVE_DOMAIN_MAP = {
    # ── 动作域 (A) ──
    "action": {
        "A-STRIKE": {"name_cn": "打击", "examples": "拳击、掌击、肘击、膝击、头槌"},
        "A-THROW": {"name_cn": "投技", "examples": "过肩摔、背投、旋风投、抓甩"},
        "A-JOINT": {"name_cn": "关节技", "examples": "锁臂、扭腕、反关节、绞技"},
        "A-PROJECTILE": {"name_cn": "飞行道具", "examples": "气弹、箭矢、光束、追踪弹"},
        "A-MOVEMENT": {"name_cn": "位移", "examples": "瞬移、冲刺、闪避、飞行"},
        "A-AOE": {"name_cn": "范围攻击", "examples": "冲击波、领域展开、地裂、风暴"},
        "A-SUMMON": {"name_cn": "召唤/分身", "examples": "影子分身、元素召唤、灵体召唤"},
        "A-CONTROL": {"name_cn": "控制", "examples": "念力、束缚、冰冻、时间停滞"},
        "A-DEFENSE": {"name_cn": "防御", "examples": "护盾、格挡、吸收、反弹"},
        "A-TRANSFORM": {"name_cn": "变身/形态转换", "examples": "觉醒、兽化、机甲合体、元素化"},
    },
    # ── 载体域 (B) ──
    "carrier": {
        "B-HUMAN": {"name_cn": "人体", "visual_traits": "标准人体比例、关节结构、肌肉系统"},
        "B-MACHINE": {"name_cn": "机械体", "visual_traits": "金属外壳、伺服关节、管道线路、面板缝隙"},
        "B-OBJECT": {"name_cn": "日常物品", "visual_traits": "家具、工具、文具、乐器、生活用品"},
        "B-ELEMENT": {"name_cn": "自然元素", "visual_traits": "流体形态、半透明、可塑性、发光/粒子"},
        "B-ARCHITECTURE": {"name_cn": "建筑/地标", "visual_traits": "巨大尺度、几何结构、内外空间"},
        "B-CREATURE": {"name_cn": "生物/怪物", "visual_traits": "非人比例、异形肢体、有机纹理、翅膀/尾巴/角"},
        "B-ABSTRACT": {"name_cn": "抽象概念", "visual_traits": "非实体、象征性表现、影子/镜子/时间/记忆/声音"},
        "B-FOOD": {"name_cn": "食物", "visual_traits": "柔软质感、色泽、蒸汽、分层结构"},
    },
    # ── 物理域 (C) ── "超越常人思维的核心引擎" ──
    "physics": {
        "P-GRAVITY": {"name_cn": "重力", "break_options": ["重力反转(上落)", "重力倍增(压扁)", "零重力(漂浮)", "方向性重力(侧壁行走)"]},
        "P-TIME": {"name_cn": "时间", "break_options": ["时间倒流", "时间加速", "时间冻结", "时间分叉(同时存在多个时间线)"]},
        "P-RIGIDITY": {"name_cn": "刚体", "break_options": ["刚体柔性化(铁管弯曲)", "柔性刚体化(水流变刀)", "半固态(果冻化)"]},
        "P-TRAJECTORY": {"name_cn": "弹道", "break_options": ["直线变螺旋", "追踪弹(转弯)", "分裂弹", "回旋镖(返回)"]},
        "P-SCALE": {"name_cn": "尺度", "break_options": ["微缩(蚂蚁大小)", "超巨大(山岳大小)", "尺度错位(手心宇宙)"]},
        "P-SPACE": {"name_cn": "空间", "break_options": ["空间折叠(瞬移)", "空间镜像(左右互换)", "口袋空间", "3D进2D"]},
        "P-MATERIAL": {"name_cn": "材质", "break_options": ["水变玻璃(碎裂)", "金属变液体", "肉体变数据", "影子变固体"]},
        "P-CAUSALITY": {"name_cn": "因果", "break_options": ["结果先于原因(弹孔先出)", "原因消失(打了没效果)", "因果链(多米诺)"]},
        "P-FRICTION": {"name_cn": "摩擦力", "break_options": ["零摩擦(永动滑行)", "超摩擦(粘住)", "方向摩擦(只滑不退)"]},
        "P-INERTIA": {"name_cn": "惯性", "break_options": ["零惯性(瞬停瞬转)", "超惯性(停不下来)", "惯性存储(蓄力释放)"]},
    },
    # ── 视觉域 (V) ──
    "visual": {
        "V-ANIME": "动漫风格",
        "V-REALISTIC": "写实电影",
        "V-INK": "水墨画",
        "V-PIXEL": "像素风",
        "V-LOWPOLY": "Low-poly",
        "V-CYBERPUNK": "赛博朋克",
        "V-WASTELAND": "废土",
        "V-MINIMAL": "极简",
        "V-SURREAL": "超现实",
        "V-CLAY": "黏土动画",
    },
}

ANTI_PATTERN_MAP = {
    "category_error": {
        "name_cn": "类别错误",
        "core_operation": "A类事物放入B类框架",
        "description": "物理破坏改变世界规则，类别破坏改变你看世界的框架本身",
        "example": "天气预报报道魔法战争、数学公式描述感情、建筑蓝图画人体",
        "visual_impact": 4,
        "prompt_formula": "[concept_from_domain_A] performed as [format_of_domain_B]",
    },
    "scale_singularity": {
        "name_cn": "尺度奇点",
        "core_operation": "尺度推向极端",
        "description": "无限大或无限小的尺度创造认知断裂",
        "example": "一滴汗里的宇宙战争、指尖上的文明、呼吸间的纪元",
        "visual_impact": 5,
        "prompt_formula": "[microscopic element] containing [cosmic scale event]",
    },
    "time_slice": {
        "name_cn": "时间切片",
        "core_operation": "多重时间同时可见",
        "description": "过去/现在/未来同框，打破线性时间叙事",
        "example": "少年与老年并肩站立、建筑从废墟到建成的过程同时可见",
        "visual_impact": 5,
        "prompt_formula": "[subject] at [past_state] and [future_state] visible simultaneously",
    },
    "material_paradox": {
        "name_cn": "物质悖论",
        "core_operation": "材料背叛天性",
        "description": "材料表现与其物理天性完全相反",
        "example": "水像玻璃一样碎裂、火焰像冰一样冻结、钢铁像丝带一样飘动",
        "visual_impact": 3,
        "prompt_formula": "[material] behaving like [opposite_material]",
    },
    "causal_inversion": {
        "name_cn": "因果倒置",
        "core_operation": "结果先于原因",
        "description": "打破因果律，效果出现在原因之前",
        "example": "弹孔先出现子弹后飞出、伤口先流血后刀砍来、建筑先倒塌后地震",
        "visual_impact": 4,
        "prompt_formula": "[effect] appears before [cause]",
    },
    "dimension_fold": {
        "name_cn": "维度折叠",
        "core_operation": "空间吃掉自己",
        "description": "3D进入2D、高维入侵低维、空间自身折叠",
        "example": "3D角色走进2D漫画格子、手伸出画面边框、镜子里的世界是另一个维度",
        "visual_impact": 5,
        "prompt_formula": "[3D_subject] entering [2D_space] or [dimension_breach]",
    },
}

THINKING_METHOD_MAP = {
    "SCAMPER": {
        "name_cn": "SCAMPER创新法",
        "operations": {
            "S": {"name_cn": "替换", "prompt_op": "替换主体/材质/环境的某个核心元素"},
            "C": {"name_cn": "合并", "prompt_op": "将两个不相干的视觉概念合并"},
            "A": {"name_cn": "借用", "prompt_op": "从其他领域借用视觉语言"},
            "M": {"name_cn": "修改", "prompt_op": "修改尺度/速度/方向/质感"},
            "P": {"name_cn": "转用", "prompt_op": "将元素转用于完全不同的场景"},
            "E": {"name_cn": "消除", "prompt_op": "消除一个核心视觉元素，看剩余如何自洽"},
            "R": {"name_cn": "反转", "prompt_op": "反转时间/因果/上下/内外/主客"},
        },
    },
    "TRIZ": {
        "name_cn": "TRIZ发明原理",
        "principles": {
            1: "分割—将整体拆为独立可动部分",
            2: "抽取—只保留最关键的特征",
            3: "合并—将同类或相邻功能合为一体",
            5: "嵌套—一个结构套入另一个",
            10: "预先作用—提前设置效果",
            13: "反向—做相反的事",
            15: "动态性—让静态变动态",
            17: "维度变化—移到另一个维度或层",
            28: "机械替代—用声/光/电磁/气味替代物理接触",
            32: "颜色改变—改变透明度/颜色/发光性",
            35: "参数变化—改变浓度/密度/弹性/温度",
        },
    },
    "FIRST_PRINCIPLES": {
        "name_cn": "第一性原理拆解",
        "decomposition": {
            "combat": "冲突 + 表达 + 反馈 + 结果 → 每个要素都可以被替换/反转",
            "character": "轮廓 + 材质 + 动作逻辑 + 识别标记 → 每个要素都可以被替换/反转",
            "scene": "光源 + 空间 + 时间 + 观者位置 → 每个要素都可以被替换/反转",
        },
    },
    "SIX_HATS": {
        "name_cn": "六顶思考帽审查",
        "hats": {
            "WHITE": "事实—这个概念的技术可实现性如何？",
            "RED": "直觉—这个画面让我兴奋吗？情绪反应？",
            "BLACK": "风险—最可能失败在哪里？模型会误解什么？",
            "YELLOW": "机会—如果成功了，最惊艳的效果是什么？",
            "GREEN": "变体—能否换一种实体类型/载体/物理破坏得到更好的变体？",
            "BLUE": "决策—综合判断，是否采用？需要什么护栏？",
        },
    },
    "DESIGN_THINKING": {
        "name_cn": "生理反应反向设计",
        "reaction_map": {
            "瞳孔放大": "→ 暗→亮的突变（先全黑1秒再爆光）",
            "屏息": "→ 极慢动作（1/10速度）+ 消除环境音",
            "鸡皮疙瘩": "→ 大空间展开+神圣光+从极近到极远的镜头跳跃",
            "心跳加速": "→ 快切+不完整画面+闪帧+残影",
            "落泪冲动": "→ 长镜头+微弱环境变化+静止中的一个小动作",
        },
    },
    "AI_LATENT_NAV": {
        "name_cn": "潜空间导航",
        "distance_types": {
            "near_fusion": "概念距离近→自然融合→加强版创意",
            "mid_jump": "有距离但共享维度→怪但合理的创意",
            "far_collision": "几乎不共享维度→从未存在过的画面",
        },
        "corridor_example": "坦克→机械→金属→人体关节→运动→舞蹈→芭蕾",
    },
    "AI_STYLE_HIJACK": {
        "name_cn": "风格劫持",
        "principle": "把两个互斥视觉风格塞进同一个prompt，利用AI无法完美融合的裂缝作为独特视觉效果",
        "top_pair": "赛博朋克 × 水墨画",
    },
    "AI_GLITCH": {
        "name_cn": "Glitch美学",
        "types": {
            "structure_fault": "结构故障—肢体错位/建筑扭曲/空间折叠",
            "motion_fault": "运动故障—残影/卡帧/时间跳跃",
            "texture_fault": "纹理故障—像素化/数据流/材质替换",
            "color_fault": "色彩故障—色差/通道分离/过饱和",
        },
    },
}

NONHUMAN_COMBAT_MOTIF = {
    "contrast": {
        "name_cn": "反差感母题",
        "formula": "非人主体 + 人类武术结构 = 反差感",
        "description": "非人躯体执行人类格斗逻辑，产生'它真的在打'的可信感",
        "rules": [
            "表达重点放在动作逻辑、力量传递和视觉后果，不要停留在'像人'",
            "非人主体的'会打' ≠ 拟人摆姿势，而是让观众看见它真的遵守一套可读的战斗逻辑",
            "先问：它的发力点在哪、关节逻辑是什么、攻击节奏如何表现、命中后怎么反应",
        ],
        "prompt_template": "Preserve [non-human body type] anatomy. Apply [human martial technique] adapted to [entity joint structure]. Show force transfer through [entity material/energy logic]. Impact reaction: [entity-specific feedback].",
    },
    "absurdity": {
        "name_cn": "荒诞感母题",
        "formula": "非人主体 + 不可思议构想 = 荒诞感",
        "description": "非人躯体执行完全违背自身物理的创意动作，产生'这不可能但好看'的冲击",
        "rules": [
            "荒诞动作仍然需要一条可读的因果链（即使因果是反物理的）",
            "先保留攻防节奏、发力路径、命中反馈，再决定外形和超现实程度",
            "荒诞≠混乱，荒诞=违反预期但内部自洽",
        ],
        "prompt_template": "[Non-human entity] performs [impossible action] through [anti-physics mechanism]. Maintain readable [rhythm/beat] despite [absurd physics]. Impact: [surprising but internally consistent result].",
    },
}

NONHUMAN_VIDEO_RULES = {
    "i2v_first_frame": {
        "name_cn": "I2V首帧驱动规则",
        "max_allowed": "1个非人主体 + 1个清楚轮廓 + 1个动作短语 + 1个简单镜头运动",
        "suitable_actions": [
            "step forward and palm strike",
            "guarded stance shift",
            "one elbow block",
            "one precise dodge",
            "slow energy pulse",
            "ethereal drift forward",
        ],
        "unsuitable_actions": [
            "连招/combo",
            "多次变形/multiple transformations",
            "多个身体同时行动/multiple bodies acting simultaneously",
            "复杂武器/complex weapon manipulation",
        ],
        "design_lock_template": "Preserve the same [non-human body], same silhouette, same material, same head/face rule, same location.",
    },
    "sweet_spot_specs": {
        "name_cn": "甜点区规格",
        "default_method": "逐镜balanced",
        "forbidden": [
            "多连招",
            "额外肢体",
            "额外角色",
            "人脸污染（非人角色出现人脸上）",
        ],
        "prompt_structure": "Design lock: [body material], [head/face rule], [signature seams/light]. One dominant action phrase: [one martial technique] then [recovery stance].",
    },
    "prompt_assembly_pipeline": {
        "name_cn": "提示词组装流水线",
        "steps": [
            "步骤1: 视觉风格前缀（从视觉域V提取）",
            "步骤2: 载体描述（从载体域B提取，含材质/轮廓/尺度）",
            "步骤3: 动作描述（从动作域A提取，参考知识库提示词）",
            "步骤4: 物理特效（从物理域C提取，含反物理参数）",
            "步骤5: VFX参数（从知识库VFX体系提取）",
            "步骤6: 镜头/氛围",
        ],
    },
}

# ── 战斗招式知识库 ──────────────────────────────────
# 来源：新烬龙V2 游戏招数收集-格斗游戏招式知识库.md + 游戏招数收集-热门网游角色技能知识库.md
# 精炼版：每个招式保留索引级摘要（中英提示词+关键帧阶段+特效色系+镜头建议），不含完整JSON轨迹

COMBAT_MOVE_INDEX = {
    # ══ 格斗游戏 ══
    "street_fighter": {
        "ryu": {
            "hadoken": {
                "name_cn": "波动拳", "type": "飞行道具",
                "prompt_cn": "格斗家侧身蓄力，蓝色气功能量在掌心凝聚旋转，双手猛推，蓝色半透明能量球高速飞出，周围白色气流旋涡，拖淡蓝光尾，照亮地面",
                "prompt_en": "Martial artist thrusts both hands forward, launching a translucent blue energy orb at high speed, surrounded by white spiraling air currents and a light blue trailing beam, blue glow on ground",
                "phases": "预备蓄力→出招推出→飞行→命中冲击→收招→残留消散",
                "vfx_palette": "ki_blue", "camera": "侧面跟拍",
            },
            "shoryuken": {
                "name_cn": "升龙拳", "type": "对空技",
                "prompt_cn": "从蹲姿猛然爆发，右拳自下而上弧线跃空，拳锋白色气旋冲击波，升至最高点定格，受重力下落",
                "prompt_en": "Fighter explodes upward from crouch, right fist tracing an arc from low to high, white air-burst shockwave at apex, hangs at peak before gravity pulls back down",
                "phases": "蹲姿蓄力→爆发上升→空中旋转→顶点定格→下落→落地",
                "vfx_palette": "sonic_white", "camera": "低角度仰拍+上摇",
            },
            "tatsumaki": {
                "name_cn": "龙卷旋风脚", "type": "旋转突进",
                "prompt_cn": "单脚支撑，身体像陀螺水平旋转向前突进，白色旋风包裹全身，腿部残影明显",
                "prompt_en": "Fighter spins like a top while advancing forward, white whirlwind envelops the body, leg afterimages from rapid rotation",
                "phases": "侧身蓄力→起旋→全速旋转突进→减速停止→残留",
                "vfx_palette": "sonic_white", "camera": "Top-down俯拍/侧面跟拍",
            },
            "shinku_hadoken": {
                "name_cn": "真空波动拳", "type": "超必杀",
                "prompt_cn": "全身蓝色气焰爆发，双手画圆聚合，巨大蓝色能量球在掌心生成，推出化为粗壮蓝色光束，地面裂缝发光",
                "prompt_en": "Blue ki aura erupts, massive energy sphere generated between palms, released as thick blue beam with spiraling white energy streams, ground cracks and glows beneath",
                "phases": "气焰爆发→能量凝聚→光束发射→光束飞行→命中爆炸→消散",
                "vfx_palette": "ki_blue", "camera": "侧后方over-the-shoulder",
            },
        },
        "ken": {
            "flaming_shoryuken": {
                "name_cn": "火焰升龙拳", "type": "对空技(火焰)",
                "prompt_cn": "升龙拳轨迹但拳锋包裹橙红色火焰，上升火焰拖出长火尾，火花粒子迸射，橙→红→暗红渐变",
                "prompt_en": "Same trajectory as Shoryuken but fist engulfed in orange-red flames, fire trail during ascent, ember particles spray, orange to crimson gradient",
                "phases": "蹲姿→爆发上升(火焰)→顶点→下落→落地",
                "vfx_palette": "fire_orange", "camera": "低角度仰拍",
            },
        },
        "chunli": {
            "hyakuretsukyaku": {
                "name_cn": "百裂脚", "type": "连续打击",
                "prompt_cn": "单脚站立，另一腿极高频率连续踢出，扇形残影阵列，白色冲击波纹和小型气旋，蓝白色气劲环绕",
                "prompt_en": "Stands on one leg, other leg kicking at extreme frequency, fan-shaped afterimage array, white impact rings, blue-white ki aura",
                "phases": "起手→加速踢击→极速残影→减速→收招",
                "vfx_palette": "ki_blue", "camera": "正面/侧面中景",
            },
            "spinning_bird_kick": {
                "name_cn": "旋圆蹴", "type": "旋转上升",
                "prompt_cn": "双手撑地倒立，双腿并拢像钻头旋转上升，脚尖螺旋白色气流，地面圆形尘土扩散",
                "prompt_en": "Handstand, legs together spinning upward like a drill, white spiraling air currents from toes, circular dust spread on ground",
                "phases": "倒立→起旋→旋转上升→落地",
                "vfx_palette": "sonic_white", "camera": "Top-down/侧面仰拍",
            },
        },
        "guile": {
            "sonic_boom": {
                "name_cn": "音速手刀", "type": "飞行道具",
                "prompt_cn": "单手向前挥斩，半月形白色气刃高速旋转飞行，锯齿状白色气流轨迹，颜色白→淡青渐变",
                "prompt_en": "Swings one arm forward launching a crescent-shaped white sonic blade spinning at high speed, serrated white trail, white to pale cyan gradient",
                "phases": "蓄力→挥斩→气刃飞行→命中",
                "vfx_palette": "sonic_white", "camera": "侧面跟拍",
            },
            "flash_kick": {
                "name_cn": "筋斗踢", "type": "对空技",
                "prompt_cn": "从蹲姿猛然后空翻，双腿向上弧线踢出，脚尖白色半月形光刃轨迹",
                "prompt_en": "Backflip from crouch, both legs tracing upward arc with white crescent blade trails from toes",
                "phases": "蹲蓄→后空翻→弧线踢→落地",
                "vfx_palette": "sonic_white", "camera": "侧面固定",
            },
        },
    },
    "king_of_fighters": {
        "kyo": {
            "oniyaki": {
                "name_cn": "鬼烧(火焰升龙)", "type": "对空技(火焰)",
                "prompt_cn": "右拳向上弧线挥出，橙红色火焰包裹前臂延伸1米，大量火星粒子如烟花迸射，亮橙→红→暗红渐变",
                "prompt_en": "Right fist swings upward in arc, orange-red flames extending 1m up forearm, ember particles spraying like fireworks, bright orange to crimson gradient",
                "phases": "蓄力→爆发上升→火焰峰值→下落→收招",
                "vfx_palette": "fire_orange", "camera": "侧面/低角度",
            },
            "aragami_chain": {
                "name_cn": "荒咬→九伤→八锖", "type": "派生连击(火焰)",
                "prompt_cn": "火焰冲拳突进(荒咬)→下向上撩击火焰上窜(九伤)→全力轰出巨大火球(八锖)，火焰一次比一次猛烈",
                "prompt_en": "Fiery charging punch (Aragami) → upward swing with surging flames (Kizu) → explosive full-force blow erupting into massive fireball (Yasakani), each hit more intense",
                "phases": "荒咬突进→九伤上撩→八锖爆发→火球消散→收招",
                "vfx_palette": "fire_orange", "camera": "正面中景→极近特写",
            },
            "orochinagi": {
                "name_cn": "大蛇薙", "type": "超必杀(火柱)",
                "prompt_cn": "全身橙色火焰气焰爆发，右臂后拉火焰柱→猛挥，地面2m直径旋转火柱冲天3m高，如火龙卷",
                "prompt_en": "Massive orange flame aura, right arm pulled back with dragon-like fire pillar, swings forward — colossal swirling fire tornado erupts from ground, 2m diameter 3m tall",
                "phases": "蓄力(火臂)→挥出→火柱爆发→火柱衰减→残留焦痕",
                "vfx_palette": "fire_orange", "camera": "斜侧+震动",
            },
        },
        "iori": {
            "yaotome_claw": {
                "name_cn": "葵花(三段爪击)", "type": "连续打击(紫焰)",
                "prompt_cn": "三段爪击：斜抓→反手横抓(紫色X形残影)→双手合拢下砸紫色能量爆发，紫色火焰闪烁",
                "prompt_en": "Three consecutive claw strikes: diagonal slash → backhand with crossing purple light trails → downward smash with purple energy burst, purple flames flickering between hits",
                "phases": "蓄紫能→第一爪→第二爪→第三爪爆发→收招",
                "vfx_palette": "purple_dark", "camera": "正面中景",
            },
            "orochi_yaotome": {
                "name_cn": "八稚女", "type": "超必杀(狂乱连击)",
                "prompt_cn": "狂笑突进，全身紫色火焰，连续8-12次疯狂爪击，紫色光轨充满画面，最后双手抓头紫色能量全屏爆炸",
                "prompt_en": "Maniacal lunge engulfed in purple flames, 8-12 frenzied claw strikes flooding the frame with purple light trails, final head-grab triggers full-screen purple energy explosion",
                "phases": "暴走→突进→狂乱连击→终结抓取→全屏爆炸→狂笑",
                "vfx_palette": "purple_dark", "camera": "多角度快切+闪光",
            },
            "kuzukaze": {
                "name_cn": "屑风(指令投)", "type": "投技",
                "prompt_cn": "单手掐脖领提起旋转180°重摔地面，手臂紫色气焰，地面龟裂尘土冲击波",
                "prompt_en": "One-hand collar grab, lifts and rotates 180° then slams hard into ground, purple flames on arm, ground cracks and dust shockwave",
                "phases": "抓取→提起旋转→猛砸→甩手",
                "vfx_palette": "purple_dark", "camera": "环绕镜头",
            },
        },
    },
    "tekken": {
        "kazuya": {
            "ewgf": {
                "name_cn": "最速风神拳", "type": "突进上勾拳(雷电)",
                "prompt_cn": "自然站姿瞬间突进，右拳斜上挥出，蓝色雷电爆发电弧呈树枝状扩散，命中蓝白电光爆炸",
                "prompt_en": "Instant dash from neutral stance, right fist swinging diagonally upward, intense blue lightning erupts from knuckles with branching arcs, blue-white electric explosion on hit",
                "phases": "预备→瞬间突进→电光爆发→电弧消散→残留电光",
                "vfx_palette": "lightning_blue", "camera": "微低角度",
            },
            "devil_wings_kick": {
                "name_cn": "恶魔飞翼", "type": "突进飞踢",
                "prompt_cn": "助跑腾空飞踢，身后隐约紫色半透明蝙蝠状恶魔翅膀虚影，命中时翅膀瞬间清晰，紫色能量脉络流动",
                "prompt_en": "Running flying kick, translucent purple bat-like demon wings phantom behind, wings momentarily solidify on impact with purple energy veins pulsing",
                "phases": "助跑→腾空→飞踢(翅膀虚影)→命中→消散",
                "vfx_palette": "purple_dark", "camera": "侧面跟拍",
            },
        },
        "jin": {
            "lightning_screw": {
                "name_cn": "雷闪", "type": "下段拳击(雷电)",
                "prompt_cn": "快速下蹲向前方地面挥拳，蓝色小型雷电效果，击中地面蓝色电弧溅射和尘土飞散",
                "prompt_en": "Quick crouch and punch toward ground, small blue electric sparks, blue arc splash and dust on ground impact",
                "phases": "下蹲→挥拳→电弧溅射→收招",
                "vfx_palette": "lightning_blue", "camera": "侧面近景",
            },
        },
    },
    "mortal_kombat": {
        "scorpion": {
            "spear": {
                "name_cn": "飞矛(Get Over Here!)", "type": "远程抓取",
                "prompt_cn": "从背后抽出带锁链苦无猛力投掷，锁链S形波浪摆动，命中后锁链绷直猛拉，对手被拖拽滑行",
                "prompt_en": "Hurls a chain-linked kunai, chain trailing in S-curve wave, on hit chain snaps taut and yanks opponent sliding across ground",
                "phases": "投掷→飞行(S链)→命中绷直→拖拽→近身",
                "vfx_palette": "fire_orange", "camera": "侧后方",
            },
            "hellfire": {
                "name_cn": "地狱火", "type": "地面火焰",
                "prompt_cn": "单手拍地，地面裂开喷涌橙红色地狱之火2米高，隐约可见骷髅面孔火焰纹理",
                "prompt_en": "Slams hand on ground, ground cracks open erupting orange-red hellfire 2m high, faint skull-face shaped flame patterns visible",
                "phases": "拍地→裂开→火焰喷涌→衰减→残留烟雾",
                "vfx_palette": "fire_orange", "camera": "低角度",
            },
        },
        "subzero": {
            "ice_ball": {
                "name_cn": "冰球", "type": "飞行道具(冻结)",
                "prompt_cn": "双手凝聚寒气，冰晶球体掌心生成(霜花纹理+蓝色能量核心)，推出飞行留冰晶粒子，命中瞬间冻结包裹",
                "prompt_en": "Gathers freezing energy, crystalline ice sphere with frost patterns and blue core, launched leaving ice crystal particles, instant freeze encasement on hit",
                "phases": "聚寒→冰球生成→飞行→命中冻结→残留冰晶",
                "vfx_palette": "ice_cyan", "camera": "侧面跟拍",
            },
            "ice_slide": {
                "name_cn": "冰滑", "type": "滑行铲腿",
                "prompt_cn": "俯身向前滑行，脚下生成冰道，冰晶从无到有快速生长，镜面光滑",
                "prompt_en": "Leans forward and slides, ice track forming beneath feet, ice crystals rapidly growing from nothing into mirror-smooth surface",
                "phases": "俯身→滑行(冰道生成)→铲腿命中→残留冰道",
                "vfx_palette": "ice_cyan", "camera": "侧面跟拍",
            },
        },
    },
    # ══ 热门网游 ══
    "honor_of_kings": {
        "libai": {
            "qinglian_sword_song": {
                "name_cn": "青莲剑歌", "type": "终极技(多段AOE)",
                "prompt_cn": "化身五道青色幻影交错穿梭切割，剑痕交汇绽放巨大青莲花(花瓣由剑气构成)，花心白色光柱冲天",
                "prompt_en": "Transforms into five cyan phantoms crisscross slashing, sword trails intersect blooming into a massive green lotus with razor-sharp petal blades, white beam erupting from flower center",
                "phases": "剑气汇聚→一分为五→穿梭切割→莲花绽放→光柱冲天→归一收剑",
                "vfx_palette": "dragon_green", "camera": "俯瞰环绕",
            },
            "jiangjinjiu": {
                "name_cn": "将进酒", "type": "三段位移",
                "prompt_cn": "三段突进(前→锐角转向→瞬移回原点)，青色水墨残影轨迹，酒杯雾化，地面三个墨晕圈",
                "prompt_en": "Three dashes (forward → sharp angle → recall to origin), cyan ink-wash afterimage trails, wine mist, three ink bloom circles on ground",
                "phases": "一段突进→二段转向→三段回原点→举杯收招",
                "vfx_palette": "dragon_green", "camera": "45°斜侧",
            },
        },
        "diaochan": {
            "zhanfenghua": {
                "name_cn": "绽风华", "type": "终极技(领域展开)",
                "prompt_cn": "优雅起舞，粉紫花瓣螺旋飘散形成20m圆形领域，花瓣屏障，地面盛唐牡丹花纹发光，每转一圈花瓣冲击波扩散",
                "prompt_en": "Graceful dance, pink-purple petals spiral outward forming 20m circular domain, petal barrier, Tang Dynasty peony ground patterns, petal shockwave per rotation",
                "phases": "起舞→领域展开→连续旋转→终极绽放→花瓣雨→残留",
                "vfx_palette": "nature_petal_pink", "camera": "俯瞰广角→轨道环绕",
            },
        },
        "wukong": {
            "dashengshenwei": {
                "name_cn": "大圣神威", "type": "终极技(AOE击飞)",
                "prompt_cn": "金箍棒急速变大至10m擎天巨柱，篆文点亮金色箍环旋转，跃起猛砸地面，金色冲击波海啸般扩散，碎石飞溅",
                "prompt_en": "Ruyi Jingu Bang rapidly grows to 10m sky-piercing pillar, golden seal script ignites, leaps and slams down with earth-shattering force, golden tsunami shockwave, debris flying",
                "phases": "召唤→变大→跃起→砸下→冲击波→收棒",
                "vfx_palette": "divine_gold", "camera": "低角度仰拍+侧面跟拍",
            },
        },
        "angela": {
            "chireguanghui": {
                "name_cn": "炽热光辉", "type": "终极技(火焰激光)",
                "prompt_cn": "魔法书悬浮翻页燃烧，喷出1m直径火焰光束(白核→橙焰→红黑热浪)，地面烧出焦黑沟壑，小萝莉后坐力滑行",
                "prompt_en": "Floating burning tome erupts 1m diameter fire beam (white plasma core → orange flames → red-black heat distortion), charred trench in ground, petite girl pushed back by recoil",
                "phases": "蓄力→喷射→持续输出→衰减→收招→地面冒烟",
                "vfx_palette": "magma_orange", "camera": "侧后方跟拍",
            },
        },
        "hanxin": {
            "guoshiwushuang": {
                "name_cn": "国士无双", "type": "终极技(枪舞)",
                "prompt_cn": "长枪四圈横扫：一圈尘土→二圈上挑银光→三圈满环银色光环→四圈猛挑银龙气劲冲天，击飞一切",
                "prompt_en": "Silver spear four sweeps: dust → upward silver blade-light → complete silver ring → upward thrust launches silver-white dragon-shaped energy skyward",
                "phases": "蓄力→一圈→二圈→三圈满环→四圈冲天→收枪",
                "vfx_palette": "sonic_white", "camera": "轨道环绕",
            },
        },
    },
    "league_of_legends": {
        "yasuo": {
            "last_breath": {
                "name_cn": "狂风绝息斩", "type": "终极技(空中连斩)",
                "prompt_cn": "瞬间闪烁到空中敌人旁，慢动作悬浮三连斩(横斩音锥→竖斩月牙风刃→全力劈下砸地)，青色旋风扩散",
                "prompt_en": "Blinks to airborne enemy, slow-motion three slashes (horizontal sonic cone → vertical crescent wind slash → overhead slam), cyan whirlwind blast on landing",
                "phases": "闪烁→慢动作悬浮→横斩→竖斩→劈下砸地→归鞘",
                "vfx_palette": "sonic_white", "camera": "轨道环绕+慢动作",
            },
        },
        "lux": {
            "final_spark": {
                "name_cn": "终极闪光", "type": "终极技(全图激光)",
                "prompt_cn": "法杖水晶变纯白，金色符文法阵3层旋转展开，喷射2m直径纯白光束(金粉光晕+彩虹折射)，空气电离闪电，地面金色沟壑",
                "prompt_en": "Staff crystal turns blinding white, 3-layer golden rune array, 2m diameter pure white beam with golden-pink halos and rainbow refraction, ionizing air lightning, golden ground trench",
                "phases": "蓄能→光束喷射→持续输出→衰减→收招→沟壑发光",
                "vfx_palette": "divine_gold", "camera": "侧后方→缓慢滑到正面",
            },
        },
        "zed": {
            "death_mark": {
                "name_cn": "瞬狱影杀阵", "type": "终极技(暗影刺杀)",
                "prompt_cn": "化为三道黑色暗影聚拢目标，掠过留红色X斩痕，真身身后现身单手结印，死亡印记(血红色手里剑)旋转脉冲后暗红爆炸",
                "prompt_en": "Body disperses into three dark shadows converging on target, X-shaped blood-red slash marks, real form materializes behind forming ninja seal, death mark (shuriken) pulses then detonates in dark red explosion",
                "phases": "化影→掠过斩痕→印记旋转→印记爆炸→终结→残留",
                "vfx_palette": "shadow_crimson", "camera": "侧面跟拍+慢动作",
            },
        },
        "jinx": {
            "super_mega_death_rocket": {
                "name_cn": "超究极死神飞弹", "type": "终极技(全图火箭)",
                "prompt_cn": "扛起鱼骨头火箭炮疯狂发射，鲨鱼涂装火箭歪歪扭扭飞越全图，尾焰从橙红变炽白，命中巨大蘑菇云+卡通星星飞出+涂鸦笑脸印记",
                "prompt_en": "Hoists Fishbones launcher, maniacal launch, shark-painted rocket wobbles across entire map, exhaust shifts orange-red to blazing white, massive mushroom cloud + cartoon stars + graffiti grin mark on explosion site",
                "phases": "装弹→发射→飞越全图→迫近→命中爆炸→狂笑",
                "vfx_palette": "shadow_crimson", "camera": "俯瞰全程+POV终点",
            },
        },
    },
    "world_of_warcraft": {
        "mage": {
            "pyroblast": {
                "name_cn": "炎爆术", "type": "核心输出(大型火球)",
                "prompt_cn": "三层橙色符文法阵旋转展开，4秒蓄力凝聚2m直径熔岩火球(半固态岩浆+黑色碎片漂浮+白金核心)，缓慢但不可阻挡飞行，命中'融化'而非爆炸",
                "prompt_en": "3-layer orange runic arrays, 4s channel凝聚 2m molten fireball (semi-liquid magma surface + floating rock fragments + platinum-white core), slow unstoppable advance, 'melting' not explosion on hit",
                "phases": "施法→法阵展开→火球成形→缓慢飞行→吞没目标→岩浆池冷却",
                "vfx_palette": "magma_orange", "camera": "侧面跟拍+慢动作",
            },
            "blink": {
                "name_cn": "闪现术", "type": "位移",
                "prompt_cn": "身体瞬间'折叠'为蓝色光点，20码外展开重组，蓝色奥术符文轨迹连接，起点碎裂消散，终点奥术新星",
                "prompt_en": "Body instantly 'folds' into blue light particles, unfolds and reassembles 20 yards away, blue arcane rune trail connecting points, origin shatters like broken mirror, arcane nova at destination",
                "phases": "折叠→传送→展开→消散",
                "vfx_palette": "ki_blue", "camera": "侧面同时拍起点终点",
            },
        },
        "warrior": {
            "bladestorm": {
                "name_cn": "剑刃风暴", "type": "AOE终结(旋风)",
                "prompt_cn": "怒吼后疯狂旋转，人剑合一5m直径灰色金属旋风，地面环形沟槽，被卷入一切切碎抛飞，人形绞肉机",
                "prompt_en": "Battle roar then frenzied spin, warrior and blade fuse into 5m diameter gray-metallic whirlwind, ground carved into circular grooves, everything caught shredded and flung outward",
                "phases": "蓄力怒吼→起转→全速风暴→衰减→停转插地→沉降",
                "vfx_palette": "fire_orange", "camera": "环绕+俯拍切换",
            },
        },
        "druid": {
            "starfall": {
                "name_cn": "星落", "type": "AOE终极(星雨)",
                "prompt_cn": "枭兽呼唤夜空，天空变暗切换星空模式，成百上千星辰碎片暴雨坠落(蓝白→紫罗兰彗星尾)，地面千疮百孔毁灭美感",
                "prompt_en": "Moonkin calls the night sky, sky darkens to starry mode, hundreds of star fragments rain down with blue-white to violet comet tails, ground pockmarked with destructive beauty",
                "phases": "召唤→初星→密集星雨→渐稀→收束→残余星光",
                "vfx_palette": "celestial_bluepurple", "camera": "广角俯瞰→缓慢推进",
            },
        },
    },
    "overwatch": {
        "genji": {
            "dragonblade": {
                "name_cn": "龙刃", "type": "终极技(近战爆发)",
                "prompt_cn": "绿龙从背后盘绕出缠绕手臂凝聚为翡翠能量长刃(龙鳞纹理+流动绿光粒子)，每次斩击龙啸+翠绿弧形刀光+龙形残影，斩杀后绿龙灵魂升天",
                "prompt_en": "Emerald dragon coils from behind condensing into jade energy blade with dragon scale texture and flowing green particles, each slash with dragon roar and lingering emerald arc with dragon afterimage, green dragon souls rise from fallen",
                "phases": "跪地拔刀→龙缠绕成刃→连续斩击→龙魂升天→收刀→绿光飘散",
                "vfx_palette": "dragon_green", "camera": "低角度环绕+慢动作",
            },
        },
        "dva": {
            "self_destruct": {
                "name_cn": "自毁", "type": "终极技(AOE毁灭)",
                "prompt_cn": "机甲警报核心变红裂纹蔓延→D.Va弹射离开→蓄爆颤抖→白屏0.2s→巨大蘑菇云+球形冲击波→粉色橙色光芒→D.Va落地持小手枪",
                "prompt_en": "Mech alarm, core turns red with spreading cracks → D.Va ejects → shuddering buildup → 0.2s white flash → massive mushroom cloud + spherical shockwave in pink/orange → D.Va lands with tiny pistol",
                "phases": "警报→弹射→蓄爆→白屏→爆炸→落地→残留",
                "vfx_palette": "mecha_blue", "camera": "环绕机甲→急剧拉远",
            },
        },
        "hanzo": {
            "dragonstrike": {
                "name_cn": "龙撃波", "type": "终极技(贯穿双龙)",
                "prompt_cn": "龙纹箭矢超音速飞出10m后'融化'化为两条3m直径深蓝东方巨龙DNA双螺旋飞驰，穿透一切留龙形空洞，双龙冲天消散",
                "prompt_en": "Dragon-marked arrow flies supersonic, after 10m 'melts' into two 3m diameter deep blue Eastern dragons racing in DNA double-helix, piercing everything leaving dragon-shaped holes, dragons soar skyward and vanish",
                "phases": "搭箭→箭矢飞行→融化变形→双龙飞驰→贯穿→冲天消散",
                "vfx_palette": "celestial_bluepurple", "camera": "侧面跟拍双龙",
            },
        },
    },
    "genshin_impact": {
        "zhongli": {
            "planet_befall": {
                "name_cn": "天星", "type": "元素爆发(陨石)",
                "prompt_cn": "单手挥令天空撕裂，金色岩陨石(远古璃月符文+几何多面体)加速下降砸地，环形岩刺放射+金色冲击波，范围内石化成灰色雕像",
                "prompt_en": "One hand sweeps forward, sky tears open, golden Geo meteorite with ancient Liyue runes and geometric polyhedron shape crashes down, radial Geo spikes + golden shockwave, enemies petrified into gray statues",
                "phases": "号令→天裂→陨落→命中→石化→收手威压",
                "vfx_palette": "divine_gold", "camera": "仰拍→侧面跟拍→地面冲击",
            },
        },
        "raiden_shogun": {
            "musou_no_hitotachi": {
                "name_cn": "无想的一刀", "type": "元素爆发(空间撕裂斩)",
                "prompt_cn": "胸口空间裂开紫色裂缝拔出纯雷等离子太刀，环境失色化(只剩紫灰)，一刀劈下撕裂空间30m紫色裂缝，无尽雷光扇形涌出",
                "prompt_en": "Chest spatial rift opens, draws pure lightning plasma tachi, environment desaturates to purple-gray, one slash tears space itself leaving 30m purple rift, endless lightning pours out in fan shape",
                "phases": "拔刀→聚势(失色化)→斩击(慢放)→雷暴→裂缝愈合→余电",
                "vfx_palette": "electro_purple", "camera": "环绕+侧面跟拍刀锋",
            },
        },
        "hutao": {
            "spirit_soother": {
                "name_cn": "安神秘法", "type": "元素爆发(火焰幽灵)",
                "prompt_cn": "护摩杖指前，巨大可爱白色幽灵浮现→瞬间橙红恶魔化膨胀5倍→巨口喷射扇形地狱烈焰+红色蝴蝶飞舞→胡桃蹦跳",
                "prompt_en": "Staff points forward, huge cute white spirit appears → instantly transforms into orange-red demon form expanding 5x → massive jaw unleashes fan-shaped hellfire + red butterflies → Hu Tao bounces happily",
                "phases": "召唤→可爱幽灵→恶魔化→烈焰喷射→消退",
                "vfx_palette": "fire_orange", "camera": "正面中景",
            },
        },
    },
}

# ── 战斗招式通用模板 ──────────────────────────────────
# 来源：V2 知识库第六章/第八章 —— 按招式/技能类型分类
COMBAT_MOVE_TEMPLATES = {
    "projectile": {
        "name_cn": "飞行道具类",
        "formula_cn": "[角色]蓄力→[能量特效]在[手/武器]凝聚→[发射动作]→[飞行道具]以[速度]飞行→[轨迹特效]→命中[命中特效]",
        "formula_en": "[Character] charges → [energy VFX] gathers at [hands/weapon] → [launch action] → [projectile] flies at [speed] → [trail VFX] → impact [impact VFX]",
        "phases": "蓄力→出招→飞行→命中→收招→残留",
        "camera_default": "侧面跟拍",
    },
    "anti_air": {
        "name_cn": "升龙/对空类",
        "formula_cn": "[角色]从蹲姿爆发→[拳/脚]自下而上弧线上升→[特效]沿[部位]延伸→顶点定格→受重力下落→落地[落地特效]",
        "formula_en": "[Character] explodes from crouch → [fist/foot] arcs upward → [VFX] extends along [limb] → apex freeze-frame → gravity pulls down → landing [impact VFX]",
        "phases": "蹲蓄→爆发→上升→顶点定格→下落→落地",
        "camera_default": "低角度仰拍+上摇",
    },
    "spinning": {
        "name_cn": "旋转/旋风类",
        "formula_cn": "[角色]身体开始旋转→速度加到峰值→[部位]向外伸展残影→[特效]包裹全身漩涡→旋转[N]圈→减速停止",
        "formula_en": "[Character] begins spinning → speed peaks → [limbs] extend with afterimages → [VFX] envelops body as vortex → [N] rotations → decelerates to stop",
        "phases": "起旋→加速→全速旋转→减速→停止",
        "camera_default": "Top-down俯拍/侧面跟拍",
    },
    "rapid_strikes": {
        "name_cn": "连续打击类",
        "formula_cn": "[角色]对目标连续[N]段攻击→每段[动作+特效]→节奏由慢到快→最后一段[最大爆发]→残影[数量/样式]",
        "formula_en": "[Character] unleashes [N]-hit combo → each hit [action + VFX] → rhythm accelerates → final hit [maximum burst] → afterimages [count/style]",
        "phases": "起手→加速→极速→爆发→收招",
        "camera_default": "正面中景→极近特写(最后一段)",
    },
    "grapple": {
        "name_cn": "投技/抓取类",
        "formula_cn": "[角色]快速接近→[抓取动作]→抓取瞬间[特效爆发]→将目标[提起/旋转/压制]→最终[摔/砸/击飞]→地面[冲击效果]",
        "formula_en": "[Character] closes in → [grab action] → [VFX burst] on grab → [lifts/rotates/pins] target → final [slam/smash/launch] → ground [impact effect]",
        "phases": "接近→抓取→操作→终结→甩开",
        "camera_default": "环绕镜头(dolly-around)",
    },
    "super_move": {
        "name_cn": "超必杀技类",
        "formula_cn": "[角色]进入[聚气/变身]→全身[气焰/光环]爆发→[特效粒子]汇聚→[核心招式]释放→屏幕[震动/闪烁]→命中[大规模爆炸]→[定格/拉远]收尾",
        "formula_en": "[Character] enters [power-up/transform] → [aura/halo] erupts → [particles] converge → [signature move] releases → screen [shake/flash] → impact [massive explosion] → [freeze/wide shot] ending",
        "phases": "聚气→气焰爆发→核心释放→命中大爆发→消散→定格",
        "camera_default": "慢动作关键帧+多角度切换",
    },
}

# ── 战斗特效色系 ──────────────────────────────────
# 来源：V2 知识库第七章/第九章 —— 特效色彩参考表
COMBAT_VFX_PALETTES = {
    "fire_orange": {
        "name_cn": "火焰橙",
        "gradient": ["#FFFFFF", "#FFFF00", "#FF8800", "#FF4400", "#CC2200", "#661100"],
        "glow": "#FF6600",
        "light_cast": "#FF8844",
        "smoke": "#444444",
        "used_by": ["荒咬", "鬼烧", "大蛇薙", "火焰升龙拳", "地狱火", "炎爆术", "炽热光辉", "安神秘法"],
    },
    "ki_blue": {
        "name_cn": "气功蓝",
        "gradient": ["#FFFFFF", "#CCEEFF", "#4488FF", "#0044CC"],
        "glow": "#88CCFF",
        "light_cast": "#AACCDD",
        "used_by": ["波动拳", "真空波动拳", "气功拳", "百裂脚"],
    },
    "sonic_white": {
        "name_cn": "音速白",
        "gradient": ["#FFFFFF", "#EEEEFF", "#CCDDEE", "#AABBCC"],
        "glow": "#DDEEFF",
        "used_by": ["音速手刀", "筋斗踢", "龙卷旋风脚", "狂风绝息斩", "国士无双"],
    },
    "purple_dark": {
        "name_cn": "暗紫",
        "gradient": ["#FFFFFF", "#CC88FF", "#9933FF", "#6600CC", "#330066"],
        "glow": "#BB55FF",
        "light_cast": "#9933CC",
        "used_by": ["葵花", "八稚女", "恶魔飞翼", "屑风"],
    },
    "lightning_blue": {
        "name_cn": "雷电蓝",
        "gradient": ["#FFFFFF", "#CCEEFF", "#88CCFF", "#4488CC"],
        "glow": "#AAEEFF",
        "light_cast": "#AACCEE",
        "used_by": ["最速风神拳", "雷闪", "雷光拳"],
    },
    "ice_cyan": {
        "name_cn": "冰霜青",
        "gradient": ["#FFFFFF", "#CCEEFF", "#88CCDD", "#4488AA"],
        "glow": "#BBEEFF",
        "light_cast": "#AADDDD",
        "used_by": ["冰球", "冰滑", "冰墙"],
    },
    "divine_gold": {
        "name_cn": "神圣金",
        "gradient": ["#FFFFFF", "#FFFFDD", "#FFDD44", "#FFAA00"],
        "glow": "#FFEE88",
        "light_cast": "#FFD700",
        "used_by": ["终极闪光", "天星", "大圣神威"],
    },
    "shadow_crimson": {
        "name_cn": "暗影血红",
        "gradient": ["#FFFFFF", "#FFCCCC", "#FF2200", "#CC0000", "#440000"],
        "glow": "#FF6644",
        "light_cast": "#CC0000",
        "used_by": ["瞬狱影杀阵", "死神飞弹"],
    },
    "nature_petal_pink": {
        "name_cn": "花瓣粉",
        "gradient": ["#FFFFFF", "#FFEEF5", "#FF88CC", "#CC4488"],
        "glow": "#FFCCEE",
        "light_cast": "#FF99CC",
        "used_by": ["绽风华"],
    },
    "dragon_green": {
        "name_cn": "翠龙绿",
        "gradient": ["#FFFFFF", "#CCFFDD", "#44FF88", "#22CC66"],
        "glow": "#88FFBB",
        "light_cast": "#44EEAA",
        "used_by": ["龙刃", "青莲剑歌"],
    },
    "electro_purple": {
        "name_cn": "雷元素紫",
        "gradient": ["#FFFFFF", "#DDCCFF", "#9944FF", "#7722CC"],
        "glow": "#BB77FF",
        "light_cast": "#9933CC",
        "used_by": ["无想的一刀"],
    },
    "magma_orange": {
        "name_cn": "岩浆橙",
        "gradient": ["#FFFFFF", "#FFEEAA", "#FF6600", "#FF4400", "#CC2200"],
        "glow": "#FF8800",
        "light_cast": "#FF8844",
        "used_by": ["炎爆术", "炽热光辉"],
    },
    "celestial_bluepurple": {
        "name_cn": "星夜蓝紫",
        "gradient": ["#FFFFFF", "#CCDDFF", "#6688EE", "#4422AA"],
        "glow": "#AACCFF",
        "light_cast": "#6688EE",
        "used_by": ["星落", "龙撃波"],
    },
    "mecha_blue": {
        "name_cn": "机甲蓝",
        "gradient": ["#FFFFFF", "#CCEEFF", "#4488EE", "#0044AA"],
        "glow": "#66AAFF",
        "light_cast": "#4488EE",
        "used_by": ["雷霆坦克", "D.Va自毁"],
    },
}

# ── 战斗甜点区模板 ──────────────────────────────────
# 战斗场景专属的正面/负面标签，远比通用 action 模板精准
COMBAT_SWEET_SPOT_TEMPLATES = {
    "image": {
        "projectile": {
            "name": "战斗-飞行道具(图片)",
            "suffix": "dynamic charging pose, glowing energy gathering at hands, projectile launch with trailing light, impact explosion with debris, cinematic composition, dramatic lighting, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, static pose, no energy effect, flat lighting, missing impact, weak VFX, low quality, blurry, watermark",
        },
        "anti_air": {
            "name": "战斗-升龙对空(图片)",
            "suffix": "upward leap with trailing energy arc, fist at apex with shockwave burst, freeze-frame at peak height, dramatic low-angle perspective, intense upward motion, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, grounded pose, no upward motion, no energy trail, flat angle, low quality, blurry, watermark",
        },
        "spinning": {
            "name": "战斗-旋转旋风(图片)",
            "suffix": "rapid spinning motion with afterimage trails, vortex energy enveloping body, limbs extending with motion blur, top-down or dynamic angle, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, extra arms, bad anatomy, static pose, no rotation blur, no afterimage, no energy vortex, low quality, blurry, watermark",
        },
        "rapid_strikes": {
            "name": "战斗-连续打击(图片)",
            "suffix": "rapid multi-hit combo, fan-shaped afterimage array, impact shockwave rings per hit, accelerating rhythm, extreme close-up on final blow, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, single pose no combo, no impact effect, no afterimage, low quality, blurry, watermark",
        },
        "grapple": {
            "name": "战斗-投技抓取(图片)",
            "suffix": "dramatic grab and lift, rotating slam motion, ground impact with crack and dust shockwave, encircling camera angle, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, no grab contact, no ground impact, flat composition, low quality, blurry, watermark",
        },
        "super_move": {
            "name": "战斗-超必杀技(图片)",
            "suffix": "massive aura explosion, energy particles converging, signature ultimate move release, screen-shaking impact, massive explosion with color gradient VFX, slow-motion keyframe, photorealistic, 8k",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, weak VFX, no aura, no explosion, no energy effect, flat lighting, anti-climactic, low quality, blurry, watermark",
        },
    },
    "video": {
        "projectile": {
            "name": "战斗-飞行道具(视频)",
            "suffix": "energy charging at hands, projectile launch with glowing trail, impact explosion with debris and screen flash, side-tracking camera, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, missing VFX, no energy trail, weak impact, low quality, watermark",
        },
        "anti_air": {
            "name": "战斗-升龙对空(视频)",
            "suffix": "crouch-to-leap upward arc, energy trail along limb, apex freeze-frame moment, gravity pull-down landing, low-angle camera tilting up, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, no upward motion, no energy trail, low quality, watermark",
        },
        "spinning": {
            "name": "战斗-旋转旋风(视频)",
            "suffix": "spinning acceleration with afterimage trails, vortex energy envelope, deceleration to stop, top-down or side-tracking camera, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, no rotation blur, low quality, watermark",
        },
        "rapid_strikes": {
            "name": "战斗-连续打击(视频)",
            "suffix": "accelerating multi-hit combo with impact frames, afterimage fan array, final blow extreme close-up with shockwave, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, no impact frames, low quality, watermark",
        },
        "grapple": {
            "name": "战斗-投技抓取(视频)",
            "suffix": "quick approach grab, rotating lift and slam, ground impact with crack and dust wave, encircling dolly camera, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, no grab contact, low quality, watermark",
        },
        "super_move": {
            "name": "战斗-超必杀技(视频)",
            "suffix": "aura eruption and energy convergence, signature ultimate release, massive explosion with gradient VFX, slow-motion keyframe into wide shot, camera shake, cinematic, smooth motion, 24fps",
            "negative": "extra fingers, extra hands, mutated hands, wrong hand anatomy, extra arms, bad anatomy, flickering, jittery motion, ghosting, double image, temporal inconsistency, frame skipping, weak VFX, no aura, anti-climactic, low quality, watermark",
        },
    },
}

# ── 战斗专属风险修复映射 ──────────────────────────────────
# 战斗场景特有的失败模式和修复关键词，与通用 NEGATIVE_REPAIR_MAP 互补
COMBAT_NEGATIVE_REPAIR_MAP = {
    "wrong_pose_sequence": {
        "symptoms": ["姿态不符合招式阶段", "蓄力姿势变成收招姿势", "出招动作跳过中间帧", "动作无因果链"],
        "repair_keywords": "correct martial arts pose sequence, proper charging stance before strike, visible energy preparation, logical motion arc from start to finish",
    },
    "missing_vfx": {
        "symptoms": ["没有能量特效", "飞行道具无光效", "招式无特效包裹", "能量体无发光"],
        "repair_keywords": "glowing energy effect, luminous aura, particle trail, energy VFX on impact, visible force manifestation, bright glow and light cast",
    },
    "wrong_energy_color": {
        "symptoms": ["能量颜色不对", "火焰变蓝色", "雷电变红色", "气功变绿色"],
        "repair_keywords": "color-accurate energy VFX, consistent energy palette, matching element color (fire=orange/red, ice=cyan/blue, lightning=blue/white, ki=blue, shadow=purple)",
    },
    "missing_impact": {
        "symptoms": ["命中无反馈", "打击无冲击感", "招式命中像没打中", "缺乏命中帧"],
        "repair_keywords": "visible impact frame, hit spark burst, shockwave on contact, screen shake on hit, debris and dust from impact, force transmission visible",
    },
    "floaty_action": {
        "symptoms": ["动作没有重量感", "打击像打棉花", "角色飘忽无惯性", "缺乏力度感"],
        "repair_keywords": "weight and momentum in strikes, grounded stance with force transmission, impact with physical recoil, heavy hit feel, proper body weight shift",
    },
    "broken_timing": {
        "symptoms": ["招式节奏错乱", "蓄力太短或太长", "连招没有加速感", "超必杀缺乏爆发瞬间"],
        "repair_keywords": "proper timing rhythm, accelerating combo tempo, dramatic pause before ultimate, slow-motion on key hit, visible charge-up duration",
    },
}

INTENT_PROMPT = """你是一个AI助手，分析用户的创意需求，判断意图类型。

返回JSON（不要markdown代码块，直接输出JSON）：
{
    "intent": "text_to_image" | "image_to_image" | "text_to_video" | "image_to_video" | "storyboard_to_video" | "image_understanding",
    "confidence": 0.0-1.0,
    "plan": "任务执行计划描述",
    "has_image_input": true/false,
    "wants_video": true/false,
    "wants_editing": true/false
}

意图判断规则：
- 想从文字生成图片 → text_to_image
- 想编辑/修改/变换已有图片 → image_to_image
- 想从文字生成视频 → text_to_video
- 想让图片动起来 → image_to_video
- 想做多场景视频（分镜）→ storyboard_to_video
- 想理解/分析图片内容 → image_understanding
"""

ENHANCE_IMAGE_PROMPT = """你是专业AI绘画提示词工程师。将用户的描述优化为生产级生图提示词包。

输出JSON（不要markdown代码块，直接输出JSON）：
{
    "optimized_prompt": "优化后的英文提示词（50-100词，10段结构完整）",
    "style_keywords": ["风格关键词"],
    "negative_prompt": "负面约束（英文逗号分隔）",
    "quality_tags": "质量标签",
    "acceptance_criteria": ["通过标准1", "通过标准2", "通过标准3", "通过标准4"]
}

优化规则（严格遵守）：
1. 翻译为英文（模型对英文理解更好）
2. 必须按以下10段结构组织 optimized_prompt，每段不能缺失：
   [主体描述（外貌/材质/姿态/数量/身份）] +
   [场景环境（地点/时间/天气/氛围/深度层次）] +
   [构图方案（景别/角度/焦点/前景中景背景/负空间/注意力路径）] +
   [镜头语言（焦段/光圈/景深/画幅比/畸变控制）] +
   [光照方案（光源方向/色温/强度/阴影方向/高光控制/填充光）] +
   [配色方案（主色调/辅助色/对比度/饱和度/情绪色彩）] +
   [材质纹理（皮肤/布料/金属/玻璃/环境材质细节）] +
   [风格锚点（写实摄影/3D渲染/概念艺术/插画等，明确而不可模棱两可）] +
   [技术质量（分辨率/细节层次/渲染品质/后处理/抗锯齿）] +
   [一致性约束（身份锁/服装锁/场景连续性/比例一致性）]
3. 使用具体而非抽象的词汇（如"golden hour 45° backlight, warm 3200K"而非"nice light"）
4. 构图必须明确前景/中景/背景的层次关系和视觉注意力引导
5. 保持用户原始创意核心不变
6. acceptance_criteria 至少包含4条：
   - 主体清晰可辨，无畸形/穿模/多余肢体/异常比例
   - 画面无文字/Logo/水印/图表/infographic/typography
   - 构图适配目标比例，无裁切关键元素，负空间合理
   - 光照合理，无明显过曝/欠曝/颜色溢出/异常色偏
7. negative_prompt 必须包含以下常见缺陷（按场景选取相关项）：
   - 人物缺陷：extra fingers, extra hands, extra limbs, mutated hands, deformed hands, fused fingers, missing fingers, wrong hand anatomy, extra arms, crossed eyes, asymmetric eyes, deformed face, distorted face, ugly face, bad anatomy, wrong proportions, body out of frame, head out of frame, limb cutoff, floating limbs, disconnected limbs
   - 穿模/物体穿透：clipping, intersecting bodies, penetrating objects, mesh penetration, overlapping bodies, fused bodies, merged bodies, body merge, object penetration, geometry distortion
   - 画质问题：blurry, low quality, low resolution, watermark, text, signature, logo, typography, jpeg artifacts, compression artifacts, cropped, out of frame, duplicate, morbid, grain, noise, pixelation
   - 光照问题：overexposed, underexposed, harsh lighting, flat lighting, washed out, oversaturated, color bleeding
   - 构图问题：cluttered, busy background, distorted perspective, wrong aspect ratio, tilted horizon, awkward framing
   - 风格偏离：3d render, cartoon, anime, sketch, painting（除非用户明确要求该风格）
8. optimized_prompt 必须以 quality_tags 结尾
9. 如果描述包含人物，negative_prompt 必须优先包含所有手部、面部和穿模相关词
10. 如果描述包含场景/背景，negative_prompt 必须额外包含 infographic, chart, text, typography, logo, watermark
11. 如果输入标注了实体类型（非人实体），optimized_prompt 必须尊重该实体的表面材质逻辑：
    - 灵体(spirit)：不生成皮肤质感/实体质量/接地姿态，用ethereal/translucent/floating描述
    - 能量体(energy_body)：不生成有机纹理/实体质量，用luminous particles/pure energy描述
    - 拟人化(anthropomorphic)：不生成人类肤色/裸肉，用species-accurate fur/scales/feathers描述
    - 机器人(robot)：不生成有机皮肤/软组织，用mechanical shell/synthetic panels描述
    - AI虚拟体(AI)：不生成物理实体质量，用holographic/data particles描述
    - 异兽(creature)：不生成人类手/人类面孔，用species-accurate anatomy描述
12. 如果实体类型是非人，negative_prompt 必须包含该实体类型的"禁止人类化"关键词：
    - 灵体加：solid body, human skin, flesh, grounded stance
    - 能量体加：solid body, organic texture, flesh, physical mass
    - 拟人化加：human skin, bare flesh tone, wrong digit count
    - 机器人加：organic skin, flesh, soft tissue, body hair
    - AI虚拟体加：solid body, physical mass, organic texture, flesh
    - 异兽加：human-like hands, human face on creature, humanization
13. acceptance_criteria 增加一条：主体保持实体类型的表面/材质/能量逻辑一致性，无物种/材质漂移
14. 如果输入标注了人像通道（帅哥/美女），optimized_prompt 必须遵循：
    - 不使用空泛形容词（帅/美/精致），改用骨相、轮廓、机位、逆光、材质和克制表情来表达
    - 不混入非人战斗逻辑、怪诞构想、武器动作或载具动作
    - 先写气质，再写五官；先写世界感，再写服装
    - 多角度必须写出差异（正面/45度/侧面/低机位/高机位），不写通用描写
    - 帅哥重点写：眉骨、鼻梁、下颌线、气场、侧脸锋利度
    - 美女重点写：面部留白、骨相、唇线、眼神层次、逆光轮廓美
    - 高颜值角色不要模板脸，要写骨相差异、气场方向和气质层级
15. 帅哥美女人像通道的 negative_prompt 必须包含：template face, generic beauty/generic male, same-face syndrome, model catalog pose, bland features
16. 帅哥美女的 acceptance_criteria 必须增加：
    - 面部骨相有差异，非模板脸，每个角度呈现不同魅力
    - 未混入战斗/怪诞/非人逻辑，保持独立人像通道
17. 如果输入标注了[创意模式]，除了常规优化外，还必须：
    - 从物理域中至少选择1个反物理参数注入optimized_prompt（如重力反转/时间倒流/刚体柔性化/尺度错位等）
    - 在negative_prompt中追加 ordinary, expected, conventional, mundane 抑制平庸
    - 在acceptance_criteria中增加：画面包含至少1个前所未见的视觉元素
18. 非人实体的创意优化必须同时遵守：
    - 实体表面材质/能量逻辑不可被创意方法破坏（灵体不生成皮肤，机甲不生成肉体）
    - 但动作表现方式可以反物理（灵体可以时间倒流般攻击，机甲可以零惯性瞬停瞬转）
19. 非人战斗创意母题：
    - 反差感：保留人类格斗的攻防节奏和发力路径，用非人材质/能量逻辑传递力量
    - 荒诞感：反物理动作仍需可读的因果链，荒诞≠混乱，荒诞=违反预期但内部自洽
"""

ENHANCE_VIDEO_PROMPT = """你是专业AI视频提示词工程师。将用户的描述优化为生产级视频生成提示词包。

输出JSON（不要markdown代码块，直接输出JSON）：
{
    "optimized_prompt": "优化后的英文视频提示词（40-80词）",
    "negative_prompt": "负面约束（英文逗号分隔）",
    "camera_movement": "唯一的镜头运动描述（必须只有一种）",
    "subject_action": "主体动作描述（必须只有一种主要动作）",
    "environment_motion": "环境运动描述（速度必须慢于主体）",
    "recommended_duration": "推荐时长(秒)",
    "recommended_fps": 推荐帧率,
    "continuity_locks": ["身份连续性约束1", "场景连续性约束2"],
    "risk_controls": ["视频特有的风险点1", "风险点2"]
}

视频Prompt三一律（必须严格遵守）：
1. 一个镜头 = 一个主体 + 一个主要动作 + 一个相机运动
2. 环境运动速度必须慢于主体运动，避免喧宾夺主
3. 保持源帧的身份、光照、场景地理、服装/道具连续性

结构规则：
1. [主体+身份锁] + [主要动作（方向/速度/幅度）] + [相机运动（类型/方向/速度）] + [场景环境] + [光照方案] + [风格锚点] + [质量标签]
2. 明确描述运动方向、速度、幅度（如"slow clockwise pan, 15° per second, gentle acceleration"）
3. 明确描述相机运动类型：pan/tilt/dolly/zoom/tracking/handheld/static，只能选一种
4. 禁止描述多镜头切换、场景跳转、时间跳跃、新角色入场、新事件发生
5. 如果基于图片生成，必须描述"保持源图构图和身份不变，仅增加指定运动"
6. continuity_locks 至少包含：身份连续性（consistent face/same person）、场景连续性（same environment/consistent lighting）
7. risk_controls 至少包含：时序一致性、运动平滑性、无鬼影/无身份漂移
8. 非人实体的运动必须符合其类型逻辑：
    - 灵体(spirit)：漂浮/飘移，不落地/不物理碰撞，用ethereal drift/floating描述
    - 能量体(energy_body)：脉动/粒子流动，不软体运动，用energy pulsing/particle flow描述
    - 拟人化(anthropomorphic)：物种适用运动，不人类化步态，用species-appropriate motion描述
    - 机器人(robot)：伺服驱动/刚性关节，不软体运动，用servo-driven/rigid articulation描述
    - AI虚拟体(AI)：全息闪烁/数据流，不物理碰撞，用holographic flicker/data stream描述
    - 异兽(creature)：物种适用运动，不人类化步态，用species-appropriate locomotion描述
9. 非人实体的 continuity_locks 必须包含实体类型特有的连续性约束：
    - 灵体：透明度一致性/发光强度/非物质形态
    - 能量体：能量色调/粒子密度/核心亮度
    - 拟人化：皮毛图案/爪指数量/物种标记
    - 机器人：板件对齐/关节类型/材料质感
    - AI虚拟体：全息稳定性/投影边界/界面元素
    - 异兽：肢体数量/物种解剖/体表纹理
10. 非人实体的 risk_controls 必须包含该实体类型的专属风险：
    - 灵体：固化风险（变实体）/形态不稳定
    - 能量体：凝固风险/色调漂移
    - 拟人化：物种漂移/爪指数量错误
    - 机器人：有机化风险/关节穿模
    - AI虚拟体：实体化风险/全息闪烁
    - 异兽：人类化风险/解剖漂移/比例失衡
11. 帅哥美女视频必须遵循生产路由规则：
    - 默认方法：逐镜 compact
    - 动作限制：只允许眼神、呼吸、轻微转头、整理衣领
    - 不混入非人怪物、复杂蓝图、密集战术、奇观动作
12. 帅哥美女 I2V 首帧驱动规则：
    - 推荐 strength：0.70-0.72（首选 0.72）
    - 动作只给微变化，不给复杂表演
    - identity lock > 动作表现
13. 帅哥美女视频的 continuity_locks 必须包含：
    - 面部骨相连续性（consistent bone structure）
    - 轮廓光/逆光连续性（consistent backlit rim light）
    - 气质连续性（consistent aura/mood）

negative_prompt 必须包含视频特有缺陷（按场景选取）：
- 人物（视频加强版）：extra fingers, extra hands, extra limbs, mutated hands, deformed hands, fused fingers, wrong hand anatomy, extra arms, bad anatomy, distorted face, morphing face, face morphing, body morphing, identity drift, face collapse, limb distortion, torso warping
- 穿模/变形（视频加强版）：clipping, intersecting bodies, penetrating objects, mesh penetration, overlapping bodies, fused bodies, merged bodies, body merge, object penetration, geometry distortion, vertex explosion, topology error
- 视频特有缺陷：static, frozen, blurry, low quality, watermark, flickering, frame skipping, jittery motion, shaky camera, unnatural movement, morphing artifacts, temporal inconsistency, ghosting, double image, sudden scene change, unsupported camera jump, motion blur artifacts, strobing, oscillation
- 画质：low resolution, compression artifacts, pixelation, banding, color shift, exposure flicker
- 环境：new characters, extra objects, logo, readable text, watermark, infographic, chart
- 环境运动：fast background movement, background faster than subject, desync motion
14. 非人角色视频的I2V首帧驱动规则：
    - 最多允许：1个非人主体 + 1个清楚轮廓 + 1个动作短语 + 1个简单镜头运动
    - 不适合：连招、多次变形、多个身体同时行动、复杂武器
    - 设计锁模板：Preserve the same [non-human body], same silhouette, same material, same head/face rule, same location.
15. 非人角色视频的甜点区规格：
    - 默认用逐镜balanced
    - 禁止多连招、额外肢体、额外角色、人脸污染
    - 提示词结构：Design lock: [body material], [head/face rule], [signature seams/light]. One dominant action phrase: [one martial technique] then [recovery stance].
16. 提示词组装流水线（按序）：
    步骤1: 视觉风格前缀 → 步骤2: 载体描述 → 步骤3: 动作描述 → 步骤4: 物理特效 → 步骤5: VFX参数 → 步骤6: 镜头/氛围
"""

CREATIVE_LEAP_PROMPT = """你是超越常人的创意Prompt工程师。你不仅仅优化用户的描述——你主动运用跨域嫁接、反模式破坏、经典思维技法来创造前所未有的视觉概念。

输出JSON（不要markdown代码块，直接输出JSON）：
{
    "original_concept": "用户原始概念提取",
    "creative_leaps": [
        {
            "method": "使用的方法名（如：跨域嫁接/反模式-类别错误/SCAMPER-替换/TRIZ-分割/潜空间远距对撞/风格劫持）",
            "leap_description": "创意飞跃的中文描述（2-3句话）",
            "optimized_prompt": "飞跃后的英文提示词（50-100词）",
            "key_visual_elements": ["前所未见的视觉元素1", "元素2"],
            "anti_physics_used": ["使用的反物理参数（如有）"],
            "negative_prompt": "负面约束（英文逗号分隔，含创意特有的失败风险）"
        }
    ],
    "recommended_leap_index": 0,
    "guardrail_check": {
        "story_function_readable": true,
        "conflict_visible": true,
        "emotional_turn_clear": true,
        "visual_payoff_worth": true
    }
}

创意方法库（按需选用1-3种）：

【跨域嫁接】
- 公式：创意概念 = 动作域(A) × 载体域(B) × 物理域(C) × 视觉域(V)
- 从四个域中各选一个元素组合，优先选择跨域距离远的组合
- 物理域是超越常人思维的核心引擎——大部分人的想象力卡在物理域
- 5大信条：先有画面再找方法 / 荒谬是入场券 / 视觉元素是可拆卸原子 / 跨域嫁接最快 / 失败是养料

【6大反模式】
- 类别错误：A类事物放入B类框架（天气预报报道魔法战争）
- 尺度奇点：尺度推向极端（一滴汗里的宇宙战争）
- 时间切片：多重时间同时可见（少年与老年并肩站立）
- 物质悖论：材料背叛天性（水像玻璃一样碎裂）
- 因果倒置：结果先于原因（弹孔先出子弹后飞）
- 维度折叠：空间吃掉自己（3D角色走进2D漫画格子）
- 互乘规则：同一概念 × 不同反模式 = 不同视觉变体

【SCAMPER】S替换/C合并/A借用/M修改/P转用/E消除/R反转
【TRIZ】分割/抽取/合并/嵌套/预先作用/反向/动态性/维度变化/机械替代/颜色改变/参数变化
【第一性原理】拆到最底层再重构：战斗=冲突+表达+反馈+结果，每要素可替换/反转
【潜空间导航】远距对撞产生"从未存在过"的画面
【风格劫持】互斥风格碰撞产生裂缝视觉（最高冲击对：赛博朋克 × 水墨画）
【Glitch美学】结构故障/运动故障/纹理故障/色彩故障

【非人创意母题】
- 反差感：非人主体+人类武术结构=反差感，重点在动作逻辑和力量传递
- 荒诞感：非人主体+不可思议构想=荒诞感，荒诞≠混乱，荒诞=违反预期但内部自洽

【战斗招式参考】
- 当用户需求涉及战斗/招式/打斗/技能/必杀技时，优先从COMBAT_MOVE_INDEX和COMBAT_MOVE_TEMPLATES中提取参考
- 6类通用招式模板：飞行道具(projectile)/对空(anti_air)/旋转(spinning)/连续打击(rapid_strikes)/投技(grapple)/超必杀(super_move)
- 14种特效色系：火焰橙/气功蓝/音速白/暗紫/雷电蓝/冰霜青/神圣金/暗影血红/花瓣粉/翠龙绿/雷元素紫/岩浆橙/星夜蓝紫/机甲蓝
- 每种色系包含gradient渐变、glow发光、light_cast光照色值，直接用于VFX参数化
- 招式6阶段模型：预备(P1)→出招(P2)→飞行/展开(P3)→命中(P4)→收招(P5)→残留(P6)，超必杀增加气焰爆发和定格阶段
- 镜头建议遵循招式类型：飞行道具→侧面跟拍，对空→低角度仰拍，旋转→Top-down，连打→正面中景→极近特写，超必杀→慢动作+多角度切换

护栏规则（必须遵守）：
1. 创意飞跃是候选方案，不是自动真理
2. 天马行空有用当且仅当：目标、冲突、压力、情绪转折和回报仍然清晰可读
3. 如果guardrail_check任何一项为false，必须标注风险并给出修复建议
4. 每个创意飞跃必须通过三问筛选：Q1画面让我兴奋吗？Q2有至少2个前所未见的视觉元素？Q3 7个以内分镜讲得清吗？
5. 非人实体的表面材质/能量逻辑不可被创意方法随意破坏——创意改变的是"如何表现"，不是"是什么"
"""

STORYBOARD_PROMPT = """你是一个视频分镜师。将用户的创意分解为分镜脚本。

输出JSON（不要markdown代码块，直接输出JSON）：
{
    "title": "视频标题",
    "total_duration": "总时长描述",
    "scenes": [
        {
            "scene": 1,
            "description": "画面描述",
            "duration_sec": 3,
            "image_prompt": "生成关键帧的图片提示词",
            "camera": "镜头运动",
            "transition": "转场方式"
        }
    ]
}

分镜规则：
1. 每个场景3-5秒
2. 图片提示词要详细，可独立生成画面
3. 场景间要有连贯性
4. 总场景数3-8个
"""

IMAGE_EDIT_PROMPT = """你是一个图像编辑专家。根据用户对图片的编辑需求，生成专业的编辑指令。

输出JSON（不要markdown代码块，直接输出JSON）：
{
    "edit_prompt": "编辑提示词（描述要改变什么）",
    "preserve_prompt": "保持不变的部分",
    "combined_prompt": "组合后的完整提示词",
    "edit_type": "style_transfer|background_change|object_edit|composition"
}

编辑Prompt规则：
1. 明确区分"改什么"和"保什么"
2. 使用 "Transform ... while preserving ..." 结构
3. 根据编辑类型调整措辞
"""


class SmartBrain:
    """智能大脑：意图识别 + Prompt增强 + 分镜生成"""

    def __init__(self, client: AgnesClient):
        self.client = client

    def _ask_brain(self, system_prompt: str, user_input: str, temperature: float = 0.7) -> str:
        """调用 2.0-flash Thinking模式"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        result = self.client.chat(
            model="agnes-2.0-flash",
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
            enable_thinking=True,
        )
        try:
            msg = result["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content")
        except (KeyError, IndexError):
            raise RuntimeError(f"Brain API返回格式异常: {str(result)[:200]}")
        if not content:
            raise RuntimeError(f"Brain 返回内容为空: {str(result)[:300]}")
        # 尝试提取JSON（可能被包裹在```json中）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return content

    def _parse_json(self, text: str) -> dict:
        """安全解析JSON"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试找到JSON部分
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {"raw_text": text}

    def recognize_intent(self, user_input: str) -> dict:
        """识别用户意图"""
        text = self._ask_brain(INTENT_PROMPT, user_input, temperature=0.3)
        result = self._parse_json(text)
        # 确保必要字段存在
        result.setdefault("intent", "text_to_image")
        result.setdefault("confidence", 0.5)
        result.setdefault("plan", user_input)
        result.setdefault("has_image_input", False)
        result.setdefault("wants_video", False)
        result.setdefault("wants_editing", False)
        return result

    def enhance_image_prompt(self, user_prompt: str, style: str | None = None) -> dict:
        """增强图片生成Prompt，自动匹配甜点区模板 + 实体感知 + 帅哥美女通道 + 战斗知识 + 风险预判"""
        # 推断实体类型
        entity_type, surface_policy = self._infer_entity_type(user_prompt)

        # 推断帅哥美女类型
        beauty_type = self._infer_beauty_type(user_prompt)

        # 检测战斗场景
        combat_ctx = self._detect_combat_scene(user_prompt, "image")

        # 构建LLM输入
        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                         f"表面策略：{surface_policy}]\n原始描述：{user_prompt}")
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            angle_rules_str = "\n".join(
                f"  {angle}: {rule}"
                for angle, rule in beauty_info["angle_rules"].items()
            )
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[多角度规则：\n{angle_rules_str}]\n"
                f"[可用气质：{', '.join(beauty_info['aura_options'])}]\n"
                f"[禁止：模板脸、空泛形容词、出招姿势、硬摆拍、夸张武打体态]\n"
                f"原始描述：{user_prompt}"
            )
        # 战斗场景注入（优先级低于实体/美女，高于通用）
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['image_prompt_hints']}\n原始描述：{user_prompt}"

        # 创意知识注入（CREATIVE_DOMAIN_MAP/ANTI_PATTERN_MAP/THINKING_METHOD_MAP 激活）
        # 仅对通用场景（非战斗、非美女）注入跨域参考元素，为LLM提供更多灵感
        if not combat_ctx and not beauty_type:
            creative_ctx = self._resolve_creative_knowledge(user_prompt, "image")
            if creative_ctx and creative_ctx.get("image_prompt_hints"):
                input_text = f"{creative_ctx['image_prompt_hints']}\n原始描述：{input_text}"

        if style:
            input_text = f"风格要求：{style}\n{input_text}"

        # 注入历史成功案例，让增强器持续进化
        try:
            from utils.memory import build_evolution_context
            evo_ctx = build_evolution_context("image")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except Exception:
            pass

        text = self._ask_brain(ENHANCE_IMAGE_PROMPT, input_text)
        result = self._parse_json(text)
        result.setdefault("optimized_prompt", user_prompt)
        result.setdefault("negative_prompt", "")

        # 自动匹配甜点区（优先：实体专属 > 战斗专属 > 帅哥美女 > 场景模板）
        template = self._match_sweet_spot(user_prompt, "image", entity_type)
        if template:
            # 叠加模板的负面提示词（去重合并）
            base_neg = result.get("negative_prompt", "")
            template_neg = template["negative"]
            result["negative_prompt"] = self._merge_negative(base_neg, template_neg)

            # 始终检查并追加模板 suffix 中缺失的质量关键词
            existing = result["optimized_prompt"].lower()
            suffix_terms = template["suffix"].split(", ")
            missing = [t for t in suffix_terms if t.lower() not in existing]
            if missing:
                result["optimized_prompt"] = result["optimized_prompt"] + ", " + ", ".join(missing[:5])

            result["sweet_spot"] = template["name"]

        # 战斗甜点区叠加（战斗场景时，覆盖通用场景模板的不足）
        if combat_ctx and combat_ctx.get("sweet_spot"):
            combat_tpl = combat_ctx["sweet_spot"]
            base_neg = result.get("negative_prompt", "")
            result["negative_prompt"] = self._merge_negative(base_neg, combat_tpl["negative"])
            existing = result["optimized_prompt"].lower()
            suffix_terms = combat_tpl["suffix"].split(", ")
            missing = [t for t in suffix_terms if t.lower() not in existing]
            if missing:
                result["optimized_prompt"] += ", " + ", ".join(missing[:5])
            result["combat_sweet_spot"] = combat_tpl["name"]
            result["combat_type"] = combat_ctx["combat_type"]
            # 注入VFX色系信息
            if combat_ctx.get("vfx_colors"):
                result["vfx_palette"] = combat_ctx["vfx_colors"]

        # 帅哥美女甜点区叠加（实体未匹配时）
        if beauty_type and not entity_type:
            beauty_tpl = self._match_beauty_sweet_spot(beauty_type, "image")
            if beauty_tpl:
                base_neg = result.get("negative_prompt", "")
                result["negative_prompt"] = self._merge_negative(base_neg, beauty_tpl["negative"])
                existing = result["optimized_prompt"].lower()
                suffix_terms = beauty_tpl["suffix"].split(", ")
                missing = [t for t in suffix_terms if t.lower() not in existing]
                if missing:
                    result["optimized_prompt"] += ", " + ", ".join(missing[:5])
                if "sweet_spot" not in result:
                    result["sweet_spot"] = beauty_tpl["name"]

        # 注入实体类型和表面策略信息
        if entity_type:
            result["entity_type"] = entity_type
            result["surface_policy"] = surface_policy

            # 形态演化控制（非人实体）
            has_transform = any(kw in user_prompt.lower() for kw in
                               ["变身", "觉醒", "进化", "变形", "转化",
                                "transform", "evolve", "awakening", "mutate", "shift"])
            result["form_evolution"] = {
                "base_form": "基础可读轮廓，保持实体类型核心身份信号",
                "transformed_form": "变身/觉醒形态" if has_transform else "无变身需求",
                "continuity_locks": ["身份核心", "轮廓关系", "材质/能量逻辑", "识别标记"],
                "forbidden_changes": ["随机物种/材质替换", "无动机形态变化", "丢失身份核心", "装饰性突变"],
            }

        # 注入帅哥美女通道信息
        if beauty_type and not entity_type:
            result["beauty_type"] = beauty_type
            result["beauty_name_cn"] = BEAUTY_PORTRAIT_MAP[beauty_type]["name_cn"]
            result["beauty_aura_options"] = BEAUTY_PORTRAIT_MAP[beauty_type]["aura_options"]
            result["beauty_focus_points"] = BEAUTY_PORTRAIT_MAP[beauty_type]["focus_points"]

        # 风险预判（传入实体类型）
        risk_warnings = self._predict_risks(user_prompt, entity_type)
        # 帅哥美女专属风险
        if beauty_type:
            beauty_risks = self._predict_beauty_risks(beauty_type)
            risk_warnings.extend(beauty_risks)
        # 战斗专属风险
        if combat_ctx and combat_ctx.get("combat_risks"):
            risk_warnings.extend(combat_ctx["combat_risks"])
        if risk_warnings:
            result["risk_warnings"] = risk_warnings
            # 将风险修复关键词合并到负面提示词中
            all_repair = []
            for rw in risk_warnings:
                all_repair.append(rw["advice"])
            repair_neg = ", ".join(all_repair)
            result["negative_prompt"] = self._merge_negative(
                result.get("negative_prompt", ""), repair_neg
            )

        return result

    def enhance_video_prompt(self, user_prompt: str) -> dict:
        """增强视频生成Prompt，自动匹配甜点区模板 + 实体感知 + 帅哥美女通道 + 战斗知识 + 风险预判"""
        # 推断实体类型
        entity_type, surface_policy = self._infer_entity_type(user_prompt)

        # 推断帅哥美女类型
        beauty_type = self._infer_beauty_type(user_prompt)

        # 检测战斗场景
        combat_ctx = self._detect_combat_scene(user_prompt, "video")

        # 构建LLM输入
        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                         f"表面策略：{surface_policy}]\n原始描述：{user_prompt}")
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[视频生产路由：逐镜 compact，I2V strength 0.70-0.72]\n"
                f"[允许动作：眼神、呼吸、轻微转头、整理衣领]\n"
                f"[禁止：出招姿势、硬摆拍、夸张武打体态、多镜头切换]\n"
                f"原始描述：{user_prompt}"
            )
        # 战斗场景注入（优先级低于实体/美女，高于通用）
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['video_prompt_hints']}\n原始描述：{user_prompt}"

        # 非人实体视频规则注入（NONHUMAN_VIDEO_RULES 知识激活）
        if entity_type and not beauty_type:
            creative_ctx = self._resolve_creative_knowledge(user_prompt, "video")
            if creative_ctx and creative_ctx.get("nonhuman_video_ctx"):
                i2v = creative_ctx["nonhuman_video_ctx"]["i2v_first_frame"]
                specs = creative_ctx["nonhuman_video_ctx"]["sweet_spot_specs"]
                pipeline = creative_ctx["nonhuman_video_ctx"]["prompt_assembly_pipeline"]
                nonhuman_video_hints = (
                    f"[非人实体视频规则]\n"
                    f"I2V首帧限制：{i2v['max_allowed']}\n"
                    f"适合动作：{', '.join(i2v['suitable_actions'][:4])}\n"
                    f"不适合动作：{', '.join(i2v['unsuitable_actions'][:4])}\n"
                    f"设计锁定：{i2v['design_lock_template']}\n"
                    f"甜点区方法：{specs['default_method']}，禁止：{', '.join(specs['forbidden'])}\n"
                    f"组装流水线：{' → '.join(pipeline['steps'])}"
                )
                input_text = f"{nonhuman_video_hints}\n原始描述：{input_text}"

        # 注入历史成功案例，让视频增强也持续进化
        try:
            from utils.memory import build_evolution_context
            evo_ctx = build_evolution_context("video")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except Exception:
            pass

        text = self._ask_brain(ENHANCE_VIDEO_PROMPT, input_text)
        result = self._parse_json(text)
        result.setdefault("optimized_prompt", user_prompt)
        result.setdefault("negative_prompt", "")
        result.setdefault("recommended_duration", "5")
        result.setdefault("recommended_fps", 24)

        # 自动匹配视频甜点区（优先：实体专属 > 战斗专属 > 帅哥美女 > 场景模板）
        template = self._match_sweet_spot(user_prompt, "video", entity_type)
        if template:
            base_neg = result.get("negative_prompt", "")
            template_neg = template["negative"]
            result["negative_prompt"] = self._merge_negative(base_neg, template_neg)

            # 始终检查并追加模板 suffix 中缺失的质量关键词
            existing = result["optimized_prompt"].lower()
            suffix_terms = template["suffix"].split(", ")
            missing = [t for t in suffix_terms if t.lower() not in existing]
            if missing:
                result["optimized_prompt"] = result["optimized_prompt"] + ", " + ", ".join(missing[:5])

            result["sweet_spot"] = template["name"]

        # 战斗甜点区叠加
        if combat_ctx and combat_ctx.get("sweet_spot"):
            combat_tpl = combat_ctx["sweet_spot"]
            base_neg = result.get("negative_prompt", "")
            result["negative_prompt"] = self._merge_negative(base_neg, combat_tpl["negative"])
            existing = result["optimized_prompt"].lower()
            suffix_terms = combat_tpl["suffix"].split(", ")
            missing = [t for t in suffix_terms if t.lower() not in existing]
            if missing:
                result["optimized_prompt"] += ", " + ", ".join(missing[:5])
            result["combat_sweet_spot"] = combat_tpl["name"]
            result["combat_type"] = combat_ctx["combat_type"]
            if combat_ctx.get("vfx_colors"):
                result["vfx_palette"] = combat_ctx["vfx_colors"]

        # 帅哥美女视频甜点区叠加（实体未匹配时）
        if beauty_type and not entity_type:
            beauty_tpl = self._match_beauty_sweet_spot(beauty_type, "video")
            if beauty_tpl:
                base_neg = result.get("negative_prompt", "")
                result["negative_prompt"] = self._merge_negative(base_neg, beauty_tpl["negative"])
                existing = result["optimized_prompt"].lower()
                suffix_terms = beauty_tpl["suffix"].split(", ")
                missing = [t for t in suffix_terms if t.lower() not in existing]
                if missing:
                    result["optimized_prompt"] += ", " + ", ".join(missing[:5])
                if "sweet_spot" not in result:
                    result["sweet_spot"] = beauty_tpl["name"]

        # 注入实体类型和表面策略信息
        if entity_type:
            result["entity_type"] = entity_type
            result["surface_policy"] = surface_policy

            # 形态演化控制（非人实体）
            has_transform = any(kw in user_prompt.lower() for kw in
                               ["变身", "觉醒", "进化", "变形", "转化",
                                "transform", "evolve", "awakening", "mutate", "shift"])
            result["form_evolution"] = {
                "base_form": "基础可读轮廓，保持实体类型核心身份信号",
                "transformed_form": "变身/觉醒形态" if has_transform else "无变身需求",
                "continuity_locks": ["身份核心", "轮廓关系", "材质/能量逻辑", "识别标记"],
                "forbidden_changes": ["随机物种/材质替换", "无动机形态变化", "丢失身份核心", "装饰性突变"],
            }

        # 注入帅哥美女视频通道信息
        if beauty_type and not entity_type:
            result["beauty_type"] = beauty_type
            result["beauty_name_cn"] = BEAUTY_PORTRAIT_MAP[beauty_type]["name_cn"]
            result["production_route"] = BEAUTY_PRODUCTION_RULES["video"]["default_route"]
            result["i2v_strength_recommendation"] = BEAUTY_PRODUCTION_RULES["video"]["i2v_strength"]

        # 风险预判（传入实体类型）
        risk_warnings = self._predict_risks(user_prompt, entity_type)
        # 帅哥美女专属风险
        if beauty_type:
            beauty_risks = self._predict_beauty_risks(beauty_type)
            risk_warnings.extend(beauty_risks)
        # 战斗专属风险
        if combat_ctx and combat_ctx.get("combat_risks"):
            risk_warnings.extend(combat_ctx["combat_risks"])
        if risk_warnings:
            result["risk_warnings"] = risk_warnings
            all_repair = []
            for rw in risk_warnings:
                all_repair.append(rw["advice"])
            repair_neg = ", ".join(all_repair)
            result["negative_prompt"] = self._merge_negative(
                result.get("negative_prompt", ""), repair_neg
            )

        return result

    def generate_storyboard(self, creative_brief: str) -> dict:
        """生成分镜脚本"""
        text = self._ask_brain(STORYBOARD_PROMPT, creative_brief, temperature=0.8)
        result = self._parse_json(text)
        result.setdefault("scenes", [{"scene": 1, "description": creative_brief, "duration_sec": 5}])
        return result

    def generate_edit_prompt(self, user_request: str, image_description: str = "") -> dict:
        """生成图片编辑Prompt"""
        input_text = f"用户编辑需求：{user_request}"
        if image_description:
            input_text += f"\n图片内容描述：{image_description}"
        text = self._ask_brain(IMAGE_EDIT_PROMPT, input_text)
        result = self._parse_json(text)
        result.setdefault("combined_prompt", user_request)
        result.setdefault("edit_type", "style_transfer")
        return result

    def _match_combat_moves(self, prompt: str) -> list[dict]:
        """根据提示词匹配战斗招式参考

        当用户需求涉及战斗/招式/打斗时，从COMBAT_MOVE_INDEX中查找最相关的招式

        Args:
            prompt: 用户原始提示词
        Returns:
            匹配到的招式摘要列表（最多5条）
        """
        p = prompt.lower()

        # 战斗/动作关键词检测
        combat_keywords = [
            "战斗", "招式", "打斗", "格斗", "连招", "必杀", "技能", "combo", "ultimate",
            "fight", "combat", "battle", "martial", "strike", "punch", "kick", "attack",
            "波动拳", "升龙", "fireball", "hadoken", "shoryuken",
            "剑", "刀", "枪", "斧", "弓", "箭", "魔法", "法术",
            "火焰", "雷电", "冰", "暗影", "能量", "气功", "飞行道具",
            "龙", "忍者", "武士", "战士", "法师", "刺客",
            "斩", "劈", "刺", "砸", "旋风", "冲击波",
            # 扩展：更多动作/招式关键词
            "爪", "抓", "投", "摔", "踢", "拳", "掌", "指",
            "连击", "打击", "上勾", "冲拳", "飞踢", "铲腿",
            "变身", "觉醒", "超必杀", "终极技", "元素爆发",
            "升龙拳", "波动拳", "葵花", "荒咬", "大蛇薙", "鬼烧",
            "天星", "龙刃", "瞬狱", "狂风", "剑刃",
            # 扩展：角色名（确保含角色名的描述也能触发）
            "八神", "草薙", "隆", "肯", "春丽", "盖尔",
            "蝎子", "零度", "源氏", "半藏",
            "李白", "貂蝉", "孙悟空", "安琪拉", "韩信",
            "亚索", "拉克丝", "劫", "金克丝",
            "钟离", "雷电将军", "胡桃",
            "法师", "战士", "德鲁伊",
            # 扩展：网游/MOBA类
            "大招", "一技能", "二技能", "三技能",
        ]
        if not any(kw in p for kw in combat_keywords):
            return []

        results = []
        # 遍历所有游戏系列、角色、招式
        for series_key, series in COMBAT_MOVE_INDEX.items():
            for char_key, char_moves in series.items():
                for move_key, move in char_moves.items():
                    score = 0
                    # 招式名匹配
                    if move["name_cn"].lower() in p:
                        score += 10
                    # 类型匹配
                    move_type = move.get("type", "").lower()
                    type_keywords = {
                        "飞行道具": ["飞行", "弹道", "projectile", "fireball", "波"],
                        "对空": ["升龙", "对空", "上升", "anti-air", "uppercut"],
                        "旋转": ["旋转", "旋风", "spin", "whirlwind", "tornado"],
                        "连续打击": ["连", "连续", "rapid", "combo", "multi-hit"],
                        "投技": ["投", "抓", "摔", "throw", "grapple", "grab"],
                        "超必杀": ["超必杀", "终极", "ultimate", "super"],
                    }
                    for type_kw_cn, kws in type_keywords.items():
                        if type_kw_cn in move_type and any(w in p for w in kws):
                            score += 3
                    # 特效色系匹配
                    palette = move.get("vfx_palette", "")
                    palette_keywords = {
                        "fire_orange": ["火", "flame", "fire", "燃烧"],
                        "ki_blue": ["气功", "蓝", "blue", "ki", "能量球"],
                        "lightning_blue": ["雷", "lightning", "electric", "电"],
                        "ice_cyan": ["冰", "ice", "frost", "冻"],
                        "purple_dark": ["紫", "暗影", "purple", "shadow", "dark"],
                        "divine_gold": ["金", "神圣", "gold", "divine", "holy"],
                        "dragon_green": ["龙", "翠", "green", "dragon"],
                    }
                    if palette in palette_keywords:
                        if any(w in p for w in palette_keywords[palette]):
                            score += 4
                    # 角色名匹配
                    char_name_map = {
                        "ryu": "隆", "ken": "肯", "chunli": "春丽", "guile": "盖尔",
                        "kyo": "草薙京", "iori": "八神", "kazuya": "一八", "jin": "风间仁",
                        "scorpion": "蝎子", "subzero": "绝对零度",
                        "libai": "李白", "diaochan": "貂蝉", "wukong": "孙悟空",
                        "angela": "安琪拉", "hanxin": "韩信",
                        "yasuo": "亚索", "lux": "拉克丝", "zed": "劫", "jinx": "金克丝",
                        "mage": "法师", "warrior": "战士", "druid": "德鲁伊",
                        "genji": "源氏", "dva": "D.Va", "hanzo": "半蔵",
                        "zhongli": "钟离", "raiden_shogun": "雷电将军", "hutao": "胡桃",
                    }
                    if char_key in char_name_map and char_name_map[char_key] in p:
                        score += 5

                    if score >= 3:
                        results.append({
                            "move_id": f"{series_key}.{char_key}.{move_key}",
                            "name_cn": move["name_cn"],
                            "type": move.get("type", ""),
                            "prompt_cn": move["prompt_cn"],
                            "prompt_en": move["prompt_en"],
                            "phases": move["phases"],
                            "vfx_palette": move.get("vfx_palette", ""),
                            "camera": move.get("camera", ""),
                            "score": score,
                        })

        # 按匹配分数排序，取top 5
        results.sort(key=lambda x: x["score"], reverse=True)
        for r in results:
            r.pop("score", None)
        return results[:5]

    def _detect_combat_scene(self, prompt: str, mode: str = "image") -> dict | None:
        """战斗知识路由器 — 统一入口，一次性解析所有战斗知识为结构化上下文

        整合 COMBAT_MOVE_INDEX / COMBAT_MOVE_TEMPLATES / COMBAT_VFX_PALETTES /
        COMBAT_SWEET_SPOT_TEMPLATES / COMBAT_NEGATIVE_REPAIR_MAP，
        供 enhance_image_prompt / enhance_video_prompt / creative_leap 共用。

        Args:
            prompt: 用户原始提示词
            mode: "image" 或 "video"
        Returns:
            战斗上下文 dict，若非战斗场景返回 None
            {
                "is_combat": True,
                "combat_type": "projectile",        # 主招式类型
                "matched_moves": [...],             # 匹配到的招式列表
                "vfx_palette_name": "fire_orange",  # 主色系名
                "vfx_colors": {...},                 # 解析后的hex色值
                "template_formula": {...},           # 对应类型的模板公式
                "phase_structure": "...",            # 阶段节奏
                "camera_suggestion": "...",          # 镜头建议
                "sweet_spot": {...},                 # 战斗甜点区
                "combat_risks": [...],              # 战斗专属风险
                "image_prompt_hints": "...",        # 图片增强专用注入文本
                "video_prompt_hints": "...",        # 视频增强专用注入文本
            }
        """
        # 1. 匹配招式
        matched_moves = self._match_combat_moves(prompt)
        if not matched_moves:
            return None

        # 2. 推断主招式类型（取匹配度最高的招式的类型映射到模板key）
        best_move = matched_moves[0]
        move_type = best_move.get("type", "")
        type_to_template = {
            "飞行道具": "projectile", "飞行道具(冻结)": "projectile",
            "对空技": "anti_air", "对空技(火焰)": "anti_air",
            "旋转突进": "spinning", "旋转上升": "spinning",
            "连续打击": "rapid_strikes", "连续打击(紫焰)": "rapid_strikes",
            "投技": "grapple", "远程抓取": "grapple", "指令投": "grapple",
            "超必杀": "super_move", "超必杀(火柱)": "super_move",
            "超必杀(狂乱连击)": "super_move", "超必杀(AOE毁灭)": "super_move",
            "终极技(AOE击飞)": "super_move", "终极技(多段AOE)": "super_move",
            "终极技(领域展开)": "super_move", "终极技(火焰激光)": "super_move",
            "终极技(枪舞)": "super_move", "终极技(空中连斩)": "super_move",
            "终极技(全图激光)": "super_move", "终极技(暗影刺杀)": "super_move",
            "终极技(全图火箭)": "super_move", "终极技(近战爆发)": "super_move",
            "终极技(贯穿双龙)": "super_move",
            "元素爆发(陨石)": "super_move", "元素爆发(空间撕裂斩)": "super_move",
            "元素爆发(火焰幽灵)": "super_move",
            "突进上勾拳(雷电)": "rapid_strikes",
            "突进飞踢": "spinning", "滑行铲腿": "spinning",
            "三段位移": "rapid_strikes", "派生连击(火焰)": "rapid_strikes",
            "核心输出(大型火球)": "projectile", "位移": "spinning",
            "AOE终结(旋风)": "spinning", "AOE终极(星雨)": "super_move",
            "下段拳击(雷电)": "rapid_strikes", "地面火焰": "super_move",
        }
        combat_type = type_to_template.get(move_type, "super_move")

        # 3. 解析VFX色系为实际hex色值
        palette_name = best_move.get("vfx_palette", "")
        vfx_colors = {}
        if palette_name and palette_name in COMBAT_VFX_PALETTES:
            palette = COMBAT_VFX_PALETTES[palette_name]
            vfx_colors = {
                "name_cn": palette["name_cn"],
                "gradient": palette.get("gradient", []),
                "glow": palette.get("glow", ""),
                "light_cast": palette.get("light_cast", ""),
            }
            if "smoke" in palette:
                vfx_colors["smoke"] = palette["smoke"]

        # 4. 获取模板公式
        template_formula = COMBAT_MOVE_TEMPLATES.get(combat_type, {})

        # 5. 获取战斗甜点区
        mode_templates = COMBAT_SWEET_SPOT_TEMPLATES.get(mode, {})
        sweet_spot = mode_templates.get(combat_type)

        # 6. 战斗专属风险预判
        p = prompt.lower()
        combat_risks = []
        # 所有战斗场景都有 missing_vfx 和 floaty_action 风险
        combat_risks.append({
            "risk": "missing_vfx",
            **COMBAT_NEGATIVE_REPAIR_MAP["missing_vfx"],
        })
        combat_risks.append({
            "risk": "floaty_action",
            **COMBAT_NEGATIVE_REPAIR_MAP["floaty_action"],
        })
        # 飞行道具 → 额外：wrong_energy_color
        if combat_type == "projectile":
            combat_risks.append({
                "risk": "wrong_energy_color",
                **COMBAT_NEGATIVE_REPAIR_MAP["wrong_energy_color"],
            })
        # 连续打击/旋转 → wrong_pose_sequence + broken_timing
        if combat_type in ("rapid_strikes", "spinning"):
            combat_risks.append({
                "risk": "wrong_pose_sequence",
                **COMBAT_NEGATIVE_REPAIR_MAP["wrong_pose_sequence"],
            })
            combat_risks.append({
                "risk": "broken_timing",
                **COMBAT_NEGATIVE_REPAIR_MAP["broken_timing"],
            })
        # 超必杀 → missing_impact + broken_timing
        if combat_type == "super_move":
            combat_risks.append({
                "risk": "missing_impact",
                **COMBAT_NEGATIVE_REPAIR_MAP["missing_impact"],
            })
            combat_risks.append({
                "risk": "broken_timing",
                **COMBAT_NEGATIVE_REPAIR_MAP["broken_timing"],
            })
        # 投技 → missing_impact
        if combat_type == "grapple":
            combat_risks.append({
                "risk": "missing_impact",
                **COMBAT_NEGATIVE_REPAIR_MAP["missing_impact"],
            })

        # 7. 构建各场景专用注入文本
        # — 图片增强用 —
        color_hint = ""
        if vfx_colors:
            grad_str = " → ".join(vfx_colors.get("gradient", []))
            color_hint = (
                f"特效色系：{vfx_colors.get('name_cn', '')}\n"
                f"渐变色阶：{grad_str}\n"
                f"发光色：{vfx_colors.get('glow', '')}，光照色：{vfx_colors.get('light_cast', '')}\n"
            )
        formula_hint = ""
        if template_formula:
            formula_hint = (
                f"招式公式(中文)：{template_formula.get('formula_cn', '')}\n"
                f"招式公式(英文)：{template_formula.get('formula_en', '')}\n"
                f"阶段节奏：{template_formula.get('phases', '')}\n"
            )
        move_hints = []
        for ref in matched_moves[:3]:
            move_hints.append(
                f"  · {ref['name_cn']}({ref['move_id']}): {ref['prompt_en']}"
            )
        image_prompt_hints = (
            f"[战斗场景检测]\n"
            f"主招式类型：{template_formula.get('name_cn', combat_type)}({combat_type})\n"
            f"{formula_hint}"
            f"{color_hint}"
            f"镜头建议：{best_move.get('camera', template_formula.get('camera_default', ''))}\n"
            f"参考招式：\n" + "\n".join(move_hints) + "\n"
            f"请在optimized_prompt中：1)按阶段公式组织动作描述 2)使用指定VFX色系的准确颜色 3)采用推荐镜头角度 4)在negative_prompt中加入战斗缺陷防护"
        )

        # — 视频增强用（在图片基础上增加时序约束） —
        video_extra = (
            f"\n[视频战斗时序约束]\n"
            f"阶段分配：预备(P1)0.5s → 出招(P2)0.3s → 飞行/展开(P3)0.5s → 命中(P4)0.2s → 收招(P5)0.3s → 残留(P6)0.2s\n"
            f"camera_movement必须与招式类型匹配：{best_move.get('camera', template_formula.get('camera_default', ''))}\n"
            f"subject_action必须遵循阶段公式，不可跳过中间阶段\n"
            f"超必杀技必须在命中帧加0.3s慢动作\n"
        )
        video_prompt_hints = image_prompt_hints + video_extra

        # — 创意飞跃用（增加跨域嫁接引导 + 非人战斗母题） —
        creative_hint = ""
        if vfx_colors:
            creative_hint = (
                f"\n[创意嫁接引导]\n"
                f"可将'{vfx_colors.get('name_cn', '')}'色系嫁接到不同载体："
                f"如用{vfx_colors.get('glow', '')}发光色做水波纹/烟雾/粒子雨\n"
            )
        # NONHUMAN_COMBAT_MOTIF 知识激活：非人实体+战斗场景时注入母题
        entity_type_detected, _ = self._infer_entity_type(prompt)
        if entity_type_detected:
            motif_hints = []
            for motif_key, motif_info in NONHUMAN_COMBAT_MOTIF.items():
                motif_hints.append(
                    f"  {motif_info['name_cn']} — 公式：{motif_info['formula']}\n"
                    f"    规则：{'；'.join(motif_info['rules'])}\n"
                    f"    提示词模板：{motif_info['prompt_template']}"
                )
            creative_hint += "\n[非人战斗母题]\n" + "\n".join(motif_hints)
        creative_prompt_hints = image_prompt_hints + creative_hint

        return {
            "is_combat": True,
            "combat_type": combat_type,
            "matched_moves": matched_moves,
            "vfx_palette_name": palette_name,
            "vfx_colors": vfx_colors,
            "template_formula": template_formula,
            "phase_structure": best_move.get("phases", ""),
            "camera_suggestion": best_move.get("camera", template_formula.get("camera_default", "")),
            "sweet_spot": sweet_spot,
            "combat_risks": combat_risks,
            "image_prompt_hints": image_prompt_hints,
            "video_prompt_hints": video_prompt_hints,
            "creative_prompt_hints": creative_prompt_hints,
        }

    def _infer_entity_type(self, prompt: str) -> tuple[str | None, str | None]:
        """根据提示词推断非人实体类型

        来源：新烬龙V2 common.js inferPrimaryCharacterEntity()

        Args:
            prompt: 用户原始提示词
        Returns:
            (entity_type, surface_policy) — entity_type为None表示human_or_humanoid
        """
        p = prompt.lower()
        # 按优先级遍历ENTITY_TYPE_MAP
        for entity_type, info in ENTITY_TYPE_MAP.items():
            for kw in info["keywords"]:
                if kw in p:
                    return entity_type, info["surface_policy"]
        return None, None

    def _infer_beauty_type(self, prompt: str) -> str | None:
        """根据提示词推断帅哥/美女类型

        来源：新烬龙V2 character-clothing.md 帅哥美女独立通道

        Args:
            prompt: 用户原始提示词
        Returns:
            "handsome" | "beauty" | None
        """
        p = prompt.lower()
        handsome_score = 0
        beauty_score = 0

        for kw in BEAUTY_PORTRAIT_MAP["handsome"]["keywords"]:
            if kw in p:
                if kw in ("帅哥美女", "高颜值"):
                    handsome_score += 1
                    beauty_score += 1
                else:
                    handsome_score += 2

        for kw in BEAUTY_PORTRAIT_MAP["beauty"]["keywords"]:
            if kw in p:
                if kw in ("帅哥美女", "高颜值"):
                    continue
                beauty_score += 2

        if handsome_score >= 2 and handsome_score > beauty_score:
            return "handsome"
        if beauty_score >= 2 and beauty_score > handsome_score:
            return "beauty"
        if handsome_score >= 2 and beauty_score >= 2:
            gender_hints_male = ["男", "他", "boy", "man", "male", "guy", "先生", "少年"]
            gender_hints_female = ["女", "她", "girl", "woman", "female", "lady", "小姐", "少女"]
            if any(h in p for h in gender_hints_male) and not any(h in p for h in gender_hints_female):
                return "handsome"
            if any(h in p for h in gender_hints_female) and not any(h in p for h in gender_hints_male):
                return "beauty"
        return None

    def _match_sweet_spot(self, prompt: str, mode: str = "image", entity_type: str | None = None) -> dict | None:
        """根据提示词关键词自动匹配甜点区模板

        优先匹配实体专属甜点区，再回退到场景甜点区

        Args:
            prompt: 用户原始提示词
            mode: "image" 或 "video"
            entity_type: 已推断的非人实体类型（可选，若提供则优先使用）
        Returns:
            匹配到的模板 dict 或 None
        """
        p = prompt.lower()

        # 1. 优先匹配实体专属甜点区
        if entity_type and entity_type in ENTITY_SWEET_SPOT_TEMPLATES:
            entity_tpl = ENTITY_SWEET_SPOT_TEMPLATES[entity_type]
            mode_tpl = entity_tpl.get(mode)
            if mode_tpl:
                return {
                    "name": f"{ENTITY_TYPE_MAP[entity_type]['name_cn']}({entity_type})",
                    "suffix": mode_tpl["suffix"],
                    "negative": mode_tpl["negative"],
                    "entity_type": entity_type,
                    "surface_policy": ENTITY_TYPE_MAP[entity_type]["surface_policy"],
                }

        # 2. 自动推断实体类型（如果未提供）
        if not entity_type:
            entity_type, _ = self._infer_entity_type(prompt)
            if entity_type and entity_type in ENTITY_SWEET_SPOT_TEMPLATES:
                entity_tpl = ENTITY_SWEET_SPOT_TEMPLATES[entity_type]
                mode_tpl = entity_tpl.get(mode)
                if mode_tpl:
                    return {
                        "name": f"{ENTITY_TYPE_MAP[entity_type]['name_cn']}({entity_type})",
                        "suffix": mode_tpl["suffix"],
                        "negative": mode_tpl["negative"],
                        "entity_type": entity_type,
                        "surface_policy": ENTITY_TYPE_MAP[entity_type]["surface_policy"],
                    }

        # 2.5 帅哥美女甜点区（实体未匹配时）
        if not entity_type:
            beauty_type = self._infer_beauty_type(prompt)
            if beauty_type:
                beauty_tpl = self._match_beauty_sweet_spot(beauty_type, mode)
                if beauty_tpl:
                    return beauty_tpl

        # 3. 回退到原有场景甜点区匹配
        # 关键词匹配规则
        person_keywords = ["人", "女", "男", "girl", "boy", "woman", "man", "lady",
                           "美女", "帅哥", "portrait", "face", "人物", "少女", "少年",
                           "lady", "miss", "mr", "角色", "character"]
        full_body_keywords = ["全身", "站", "走", "跑", "跳", "standing", "walking",
                              "running", "full body", "跳舞", "dancing", "姿势", "pose"]
        action_keywords = ["打", "战", "打斗", "fight", "battle", "action", "追逐",
                           "chase", "武术", "martial", "鞭", "whip", "sword", "挥",
                           "attack", "kick", "punch"]
        animal_keywords = ["猫", "狗", "鸟", "鱼", "虎", "龙", "马", "动物",
                           "cat", "dog", "bird", "fish", "tiger", "dragon", "horse",
                           "animal", "lion", "wolf", "bear", "rabbit", "snake"]
        landscape_keywords = ["山", "海", "湖", "天空", "日落", "城市", "风景",
                              "mountain", "ocean", "sea", "lake", "sky", "sunset",
                              "city", "landscape", "forest", "沙漠", "desert"]
        food_keywords = ["美食", "蛋糕", "甜品", "食物", "菜", "汤", "咖啡",
                         "food", "cake", "dessert", "soup", "coffee", "tea", "meal"]
        anime_keywords = ["动漫", "二次元", "anime", "manga", "2.5d", "赛璐",
                          "日系", "卡通人物"]

        # 按优先级匹配
        if mode == "video":
            templates = SWEET_SPOT_VIDEO_TEMPLATES
            if any(k in p for k in action_keywords):
                result = templates["action_video"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in person_keywords):
                if any(k in p for k in full_body_keywords):
                    result = templates["action_video"]
                    return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
                result = templates["portrait_video"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            result = templates["camera_pan"]
            return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
        else:
            if any(k in p for k in anime_keywords):
                result = SWEET_SPOT_TEMPLATES["anime"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in action_keywords):
                result = SWEET_SPOT_TEMPLATES["action"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in full_body_keywords):
                result = SWEET_SPOT_TEMPLATES["full_body"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in person_keywords):
                result = SWEET_SPOT_TEMPLATES["portrait"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in animal_keywords):
                result = SWEET_SPOT_TEMPLATES["animal"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in food_keywords):
                result = SWEET_SPOT_TEMPLATES["food"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}
            if any(k in p for k in landscape_keywords):
                result = SWEET_SPOT_TEMPLATES["landscape"]
                return {"name": result["name"], "suffix": result["suffix"], "negative": result["negative"], "entity_type": None, "surface_policy": None}

        return None

    def _predict_risks(self, prompt: str, entity_type: str | None = None) -> list[dict]:
        """根据提示词预判可能的失败风险，返回预防性修复建议

        Args:
            prompt: 用户原始提示词
            entity_type: 已推断的非人实体类型（可选）
        Returns:
            [{"risk": "风险类型", "symptoms": ["可能现象"], "advice": "修复关键词"}, ...]
        """
        p = prompt.lower()
        risks = []

        # ── 实体专属风险（优先） ──
        if entity_type and entity_type in ENTITY_NEGATIVE_REPAIR_MAP:
            for risk_id, risk_info in ENTITY_NEGATIVE_REPAIR_MAP[entity_type].items():
                risks.append({"risk": f"{entity_type}_{risk_id}",
                              "symptoms": risk_info["symptoms"],
                              "advice": risk_info["repair_keywords"]})

        # ── 通用风险 ──
        # 人物相关 → 解剖失败 + 穿模风险
        person_kw = ["人", "女", "男", "girl", "boy", "woman", "man", "face",
                      "portrait", "人物", "少女", "少年", "角色", "character",
                      "美女", "帅哥", "模特", "model"]
        if any(k in p for k in person_kw):
            risks.append({"risk": "anatomy_failure",
                          "symptoms": NEGATIVE_REPAIR_MAP["anatomy_failure"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["anatomy_failure"]["repair_keywords"]})
            risks.append({"risk": "penetration",
                          "symptoms": NEGATIVE_REPAIR_MAP["penetration"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["penetration"]["repair_keywords"]})
        # 动作/打斗 → 穿模风险 + 视频不稳定
        action_kw = ["动作", "fight", "battle", "action", "attack", "打", "战",
                      "打斗", "追逐", "chase", "武术", "martial", "kick", "punch",
                      "跑", "跳", "挥", "舞", "dancing"]
        if any(k in p for k in action_kw):
            if not any(r["risk"] == "penetration" for r in risks):
                risks.append({"risk": "penetration",
                              "symptoms": NEGATIVE_REPAIR_MAP["penetration"]["symptoms"],
                              "advice": NEGATIVE_REPAIR_MAP["penetration"]["repair_keywords"]})
            risks.append({"risk": "video_instability",
                          "symptoms": NEGATIVE_REPAIR_MAP["video_instability"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["video_instability"]["repair_keywords"]})
        # 背景/场景 → 文字漂移风险
        scene_kw = ["背景", "场景", "landscape", "background", "城市", "风景",
                     "city", "mountain", "ocean", "sea", "forest", "天空", "街",
                     "street", "building", "室内", "indoor", "room"]
        if any(k in p for k in scene_kw):
            risks.append({"risk": "text_drift",
                          "symptoms": NEGATIVE_REPAIR_MAP["text_drift"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["text_drift"]["repair_keywords"]})
        # 光照关键词 → 过曝/欠曝风险
        light_kw = ["light", "光照", "阳光", "sun", "影", "shadow", "亮",
                     "暗", "dark", "bright", "闪光", "flash"]
        if any(k in p for k in light_kw):
            risks.append({"risk": "too_bright",
                          "symptoms": NEGATIVE_REPAIR_MAP["too_bright"]["symptoms"],
                          "advice": NEGATIVE_REPAIR_MAP["too_bright"]["repair_keywords"]})
        return risks

    def _match_beauty_sweet_spot(self, beauty_type: str, mode: str = "image") -> dict | None:
        """匹配帅哥/美女专属甜点区模板

        Args:
            beauty_type: "handsome" 或 "beauty"
            mode: "image" 或 "video"
        Returns:
            匹配到的模板 dict 或 None
        """
        if beauty_type in BEAUTY_SWEET_SPOT_TEMPLATES:
            mode_tpl = BEAUTY_SWEET_SPOT_TEMPLATES[beauty_type].get(mode)
            if mode_tpl:
                return {
                    "name": f"{BEAUTY_PORTRAIT_MAP[beauty_type]['name_cn']}({beauty_type})",
                    "suffix": mode_tpl["suffix"],
                    "negative": mode_tpl["negative"],
                }
        return None

    def _predict_beauty_risks(self, beauty_type: str) -> list[dict]:
        """帅哥美女专属风险预判

        Args:
            beauty_type: "handsome" 或 "beauty"
        Returns:
            [{"risk": "风险类型", "symptoms": [...], "advice": "修复关键词"}, ...]
        """
        risks = []
        if beauty_type in BEAUTY_NEGATIVE_REPAIR_MAP:
            for risk_id, risk_info in BEAUTY_NEGATIVE_REPAIR_MAP[beauty_type].items():
                risks.append({
                    "risk": f"{beauty_type}_{risk_id}",
                    "symptoms": risk_info["symptoms"],
                    "advice": risk_info["repair_keywords"],
                })
        return risks

    @staticmethod
    def _merge_negative(*negative_strings: str) -> str:
        """合并多个负面提示词字符串，去重"""
        all_terms = set()
        for ns in negative_strings:
            if not ns:
                continue
            for term in ns.split(","):
                term = term.strip().lower()
                if term:
                    all_terms.add(term)
        return ", ".join(sorted(all_terms))

    def understand_image(self, question: str, image_url: str) -> str:
        """利用 1.5-flash 多模态能力理解图片"""
        result = self.client.chat_multimodal(
            text=question,
            image_url=image_url,
            model="agnes-1.5-flash",
            temperature=0.3,
            max_tokens=1024,
        )
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"多模态API返回格式异常: {str(result)[:200]}")

    def entity_graft(self, user_prompt: str, target_entity: str = "auto") -> dict:
        """实体嫁接：将人类角色描述转化为非人实体

        来源：新烬龙V2 creative-leap.md Entity Grafting + thinking-engine.js

        护栏：嫁接不能是装饰性的——新形态必须改善钩子、主题、动作可读性或视觉回报

        Args:
            user_prompt: 用户原始描述
            target_entity: 嫁接目标类型，可选：
                mechanical_body/energy_form/digital_avatar/mythical_beast/
                symbiotic_organism/shadow_entity/liquid_metal/crystalline_being/auto
                "auto" 时由系统根据内容自动选择最匹配的嫁接目标
        Returns:
            嫁接结果 dict，包含新实体描述、连续性锁、护栏检查
        """
        # 自动选择嫁接目标
        if target_entity == "auto":
            p = user_prompt.lower()
            if any(kw in p for kw in ["机械", "机器", "metal", "mech", "cyborg"]):
                target_entity = "mechanical_body"
            elif any(kw in p for kw in ["能量", "光", "energy", "light", "flame"]):
                target_entity = "energy_form"
            elif any(kw in p for kw in ["全息", "数字", "虚拟", "hologram", "digital", "virtual"]):
                target_entity = "digital_avatar"
            elif any(kw in p for kw in ["神话", "龙", "兽", "beast", "dragon", "myth"]):
                target_entity = "mythical_beast"
            elif any(kw in p for kw in ["共生", "拟人", "symbiotic", "anthro"]):
                target_entity = "symbiotic_organism"
            elif any(kw in p for kw in ["暗影", "影", "shadow", "dark"]):
                target_entity = "shadow_entity"
            elif any(kw in p for kw in ["液态", "流体", "liquid", "flow"]):
                target_entity = "liquid_metal"
            elif any(kw in p for kw in ["晶体", "水晶", "crystal", "crystalline"]):
                target_entity = "crystalline_being"
            else:
                target_entity = "shadow_entity"  # 默认嫁接为暗影实体（最通用的非人化）

        graft_info = GRAFT_TARGETS.get(target_entity, GRAFT_TARGETS["shadow_entity"])
        resolved_entity_type = graft_info["target_entity"]

        # 构建嫁接提示词
        graft_prompt = f"""你是一个创意实体嫁接专家。将以下人类角色描述转化为{graft_info['name_cn']}实体。

嫁接目标：{graft_info['name_cn']}({target_entity})
嫁接描述：{graft_info['description']}
表面材质策略：{ENTITY_TYPE_MAP[resolved_entity_type]['surface_policy']}

原始描述：{user_prompt}

输出JSON（不要markdown代码块，直接输出JSON）：
{{
    "grafted_prompt": "嫁接后的英文提示词描述（50-100词，保持故事功能可读）",
    "entity_type": "{resolved_entity_type}",
    "surface_material": "表面材质描述（皮毛/金属/能量/全息等）",
    "identity_core": "保留的身份核心特征（至少3个）",
    "continuity_locks": ["连续性约束1", "连续性约束2", "连续性约束3"],
    "forbidden_changes": ["禁止变异1", "禁止变异2"],
    "story_function": "嫁接后的故事功能说明",
    "visual_payoff": "视觉回报说明",
    "graft_safety": "safe|risky|decorative（仅safe可自动使用）"
}}

嫁接规则：
1. 保持故事功能可读性——目标、冲突、压力、转折、回报必须保持清晰
2. 新形态必须改善钩子、主题、动作可读性或视觉回报
3. 禁止装饰性嫁接（仅改变外观但不改善故事表达）
4. 保留原始角色的身份核心信号（如眼神语言、轮廓节奏、核心符号）
5. 新表面材质必须与实体类型逻辑一致
"""

        text = self._ask_brain(graft_prompt, user_prompt, temperature=0.7)
        result = self._parse_json(text)
        result.setdefault("grafted_prompt", user_prompt)
        result.setdefault("entity_type", resolved_entity_type)
        result.setdefault("graft_target", target_entity)
        result.setdefault("graft_name_cn", graft_info["name_cn"])
        result.setdefault("surface_policy", ENTITY_TYPE_MAP[resolved_entity_type]["surface_policy"])
        result.setdefault("story_function", "")
        result.setdefault("visual_payoff", "")
        result.setdefault("graft_safety", "safe")

        # 护栏检查：如果嫁接安全性为decorative，添加警告
        if result.get("graft_safety") == "decorative":
            result["graft_warning"] = "⚠ 嫁接被判为装饰性（不影响故事表达），建议回退到原形态"
        elif result.get("graft_safety") == "risky":
            result["graft_warning"] = "⚠ 嫁接有连续性风险，需人工确认"

        # 使用实体专属甜点区增强嫁接结果
        template = self._match_sweet_spot(result["grafted_prompt"], "image", resolved_entity_type)
        if template:
            result["sweet_spot"] = template["name"]
            result.setdefault("negative_prompt", "")
            result["negative_prompt"] = self._merge_negative(
                result.get("negative_prompt", ""), template["negative"]
            )

        return result

    def _resolve_creative_knowledge(self, prompt: str, mode: str = "image") -> dict:
        """创意知识路由器 — 一次性解析所有V2创意知识常量为结构化上下文

        激活5个曾经死掉的知识常量：
        - CREATIVE_DOMAIN_MAP  → 跨域嫁接候选元素
        - ANTI_PATTERN_MAP     → 可施加的反模式 + prompt_formula
        - THINKING_METHOD_MAP  → 匹配的思维技法详情
        - NONHUMAN_COMBAT_MOTIF → 非人战斗母题（反差感/荒诞感）
        - NONHUMAN_VIDEO_RULES  → 非人视频生产规则

        供 creative_leap / enhance_video_prompt / _detect_combat_scene 共用。

        Args:
            prompt: 用户原始提示词
            mode: "image" 或 "video"
        Returns:
            创意知识上下文 dict
        """
        p = prompt.lower()
        entity_type, _ = self._infer_entity_type(prompt)
        is_nonhuman = entity_type is not None

        # ── 1. 从 CREATIVE_DOMAIN_MAP 解析跨域嫁接候选 ──
        domain_candidates = {}
        for domain_key, domain_items in CREATIVE_DOMAIN_MAP.items():
            candidates = []
            if isinstance(domain_items, dict):
                for item_key, item_val in domain_items.items():
                    if isinstance(item_val, dict):
                        name = item_val.get("name_cn", item_key)
                        examples = item_val.get("examples", item_val.get("visual_traits", ""))
                        candidates.append(f"{name}({item_key}): {examples}")
                    else:
                        candidates.append(f"{item_val}({item_key})")
            domain_candidates[domain_key] = candidates

        # 根据提示词匹配各域最相关的元素
        matched_domain_elements = {}
        for domain_key, items in CREATIVE_DOMAIN_MAP.items():
            hits = []
            if isinstance(items, dict):
                for item_key, item_val in items.items():
                    if isinstance(item_val, dict):
                        name = item_val.get("name_cn", item_key)
                        examples = item_val.get("examples", item_val.get("visual_traits", ""))
                        # 检查关键词匹配
                        check_text = f"{name} {examples} {item_key}".lower()
                        prompt_words = [w for w in p.split() if len(w) > 1]
                        if any(w in check_text for w in prompt_words):
                            hits.append({"key": item_key, "name_cn": name, "examples": examples})
            if hits:
                matched_domain_elements[domain_key] = hits

        # ── 2. 从 ANTI_PATTERN_MAP 解析反模式 ──
        matched_anti_patterns = []
        anti_pattern_keywords = {
            "category_error": ["类别", "错误", "框架", "category", "framework"],
            "scale_singularity": ["尺度", "极端", "无限", "微观", "宏大", "scale", "extreme", "infinite"],
            "time_slice": ["时间", "同时", "过去", "未来", "time", "simultaneous", "past", "future"],
            "material_paradox": ["材料", "悖论", "背叛", "material", "paradox", "opposite"],
            "causal_inversion": ["因果", "倒置", "结果先于", "causal", "inversion", "reverse"],
            "dimension_fold": ["维度", "折叠", "2D", "3D", "dimension", "fold"],
        }
        for ap_key, ap_info in ANTI_PATTERN_MAP.items():
            # 始终包含所有反模式供LLM选用
            matched_anti_patterns.append({
                "key": ap_key,
                "name_cn": ap_info["name_cn"],
                "core_operation": ap_info["core_operation"],
                "example": ap_info["example"],
                "visual_impact": ap_info["visual_impact"],
                "prompt_formula": ap_info["prompt_formula"],
                "relevance": 2 if any(kw in p for kw in anti_pattern_keywords.get(ap_key, [])) else 0,
            })
        matched_anti_patterns.sort(key=lambda x: x["relevance"], reverse=True)

        # ── 3. 从 THINKING_METHOD_MAP 解析思维技法 ──
        matched_methods = self._select_creative_methods(prompt)
        resolved_methods = []
        for method_id in matched_methods:
            if method_id == "cross_domain_graft" and "action" in CREATIVE_DOMAIN_MAP:
                # 跨域嫁接 — 从 CREATIVE_DOMAIN_MAP 取四域
                resolved_methods.append({
                    "id": "cross_domain_graft",
                    "name_cn": "跨域嫁接",
                    "domains": {
                        "action": [f"{v.get('name_cn', k)}" for k, v in CREATIVE_DOMAIN_MAP["action"].items() if isinstance(v, dict)],
                        "carrier": [f"{v.get('name_cn', k)}" for k, v in CREATIVE_DOMAIN_MAP["carrier"].items() if isinstance(v, dict)],
                        "physics": [f"{v.get('name_cn', k)}: {', '.join(v.get('break_options', []))}" for k, v in CREATIVE_DOMAIN_MAP["physics"].items() if isinstance(v, dict)],
                        "visual": [v if isinstance(v, str) else v.get("name_cn", "") for v in CREATIVE_DOMAIN_MAP["visual"].values()],
                    },
                    "formula": "创意概念 = 动作域(A) × 载体域(B) × 物理域(C) × 视觉域(V)",
                })
            elif method_id == "anti_pattern":
                resolved_methods.append({
                    "id": "anti_pattern",
                    "name_cn": "反模式破坏",
                    "available_patterns": [
                        {"key": ap["key"], "name_cn": ap["name_cn"], "formula": ap["prompt_formula"], "impact": ap["visual_impact"]}
                        for ap in matched_anti_patterns[:3]
                    ],
                })
            elif method_id == "SCAMPER" and "SCAMPER" in THINKING_METHOD_MAP:
                ops = THINKING_METHOD_MAP["SCAMPER"]["operations"]
                resolved_methods.append({
                    "id": "SCAMPER",
                    "name_cn": THINKING_METHOD_MAP["SCAMPER"]["name_cn"],
                    "operations": {k: {"name_cn": v["name_cn"], "prompt_op": v["prompt_op"]} for k, v in ops.items()},
                })
            elif method_id == "TRIZ" and "TRIZ" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "TRIZ",
                    "name_cn": THINKING_METHOD_MAP["TRIZ"]["name_cn"],
                    "principles": THINKING_METHOD_MAP["TRIZ"]["principles"],
                })
            elif method_id == "first_principles" and "FIRST_PRINCIPLES" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "first_principles",
                    "name_cn": THINKING_METHOD_MAP["FIRST_PRINCIPLES"]["name_cn"],
                    "decomposition": THINKING_METHOD_MAP["FIRST_PRINCIPLES"]["decomposition"],
                })
            elif method_id == "latent_nav" and "AI_LATENT_NAV" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "latent_nav",
                    "name_cn": THINKING_METHOD_MAP["AI_LATENT_NAV"]["name_cn"],
                    "distance_types": THINKING_METHOD_MAP["AI_LATENT_NAV"]["distance_types"],
                    "corridor_example": THINKING_METHOD_MAP["AI_LATENT_NAV"]["corridor_example"],
                })
            elif method_id == "style_hijack" and "AI_STYLE_HIJACK" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "style_hijack",
                    "name_cn": THINKING_METHOD_MAP["AI_STYLE_HIJACK"]["name_cn"],
                    "principle": THINKING_METHOD_MAP["AI_STYLE_HIJACK"]["principle"],
                    "top_pair": THINKING_METHOD_MAP["AI_STYLE_HIJACK"]["top_pair"],
                })
            elif method_id == "glitch" and "AI_GLITCH" in THINKING_METHOD_MAP:
                resolved_methods.append({
                    "id": "glitch",
                    "name_cn": THINKING_METHOD_MAP["AI_GLITCH"]["name_cn"],
                    "types": THINKING_METHOD_MAP["AI_GLITCH"]["types"],
                })

        # ── 4. 从 NONHUMAN_COMBAT_MOTIF 解析非人战斗母题 ──
        nonhuman_motif_ctx = None
        if is_nonhuman:
            combat_moves = self._match_combat_moves(prompt)
            if combat_moves:
                nonhuman_motif_ctx = {}
                for motif_key, motif_info in NONHUMAN_COMBAT_MOTIF.items():
                    nonhuman_motif_ctx[motif_key] = {
                        "name_cn": motif_info["name_cn"],
                        "formula": motif_info["formula"],
                        "rules": motif_info["rules"],
                        "prompt_template": motif_info["prompt_template"],
                    }

        # ── 5. 从 NONHUMAN_VIDEO_RULES 解析非人视频规则 ──
        nonhuman_video_ctx = None
        if is_nonhuman and mode == "video":
            nonhuman_video_ctx = {
                "i2v_first_frame": NONHUMAN_VIDEO_RULES["i2v_first_frame"],
                "sweet_spot_specs": NONHUMAN_VIDEO_RULES["sweet_spot_specs"],
                "prompt_assembly_pipeline": NONHUMAN_VIDEO_RULES["prompt_assembly_pipeline"],
            }

        # ── 6. 构建各场景专用注入文本 ──
        # — 创意飞跃用 —
        method_hints = []
        for m in resolved_methods:
            mid = m["id"]
            if mid == "cross_domain_graft":
                domain_lines = []
                for dname, items in m["domains"].items():
                    domain_lines.append(f"  {dname}: {'; '.join(items[:5])}")
                method_hints.append(
                    f"【跨域嫁接】公式：{m['formula']}\n可用域元素：\n" + "\n".join(domain_lines)
                )
            elif mid == "anti_pattern":
                pattern_lines = []
                for pat in m["available_patterns"]:
                    pattern_lines.append(f"  {pat['name_cn']}: 公式\"{pat['formula']}\" 冲击度{pat['impact']}")
                method_hints.append("【反模式破坏】可选反模式：\n" + "\n".join(pattern_lines))
            elif mid == "SCAMPER":
                op_lines = [f"  {k}-{v['name_cn']}: {v['prompt_op']}" for k, v in m["operations"].items()]
                method_hints.append(f"【{m['name_cn']}】选择2-3种操作：\n" + "\n".join(op_lines))
            elif mid == "TRIZ":
                prin_lines = [f"  原理{n}: {desc}" for n, desc in m["principles"].items()]
                method_hints.append(f"【{m['name_cn']}】可选原理：\n" + "\n".join(prin_lines))
            elif mid == "first_principles":
                decomp_lines = [f"  {k}: {v}" for k, v in m["decomposition"].items()]
                method_hints.append(f"【{m['name_cn']}】拆解维度：\n" + "\n".join(decomp_lines))
            elif mid == "latent_nav":
                dt_lines = [f"  {k}: {v}" for k, v in m["distance_types"].items()]
                method_hints.append(f"【{m['name_cn']}】距离类型：\n" + "\n".join(dt_lines) + f"\n  走廊示例: {m['corridor_example']}")
            elif mid == "style_hijack":
                method_hints.append(f"【{m['name_cn']}】{m['principle']}\n  最高冲击对: {m['top_pair']}")
            elif mid == "glitch":
                type_lines = [f"  {k}: {v}" for k, v in m["types"].items()]
                method_hints.append(f"【{m['name_cn']}】故障类型：\n" + "\n".join(type_lines))

        creative_prompt_hints = "[创意知识注入]\n" + "\n".join(method_hints)

        # 非人战斗母题附加
        if nonhuman_motif_ctx:
            motif_lines = []
            for mk, mv in nonhuman_motif_ctx.items():
                motif_lines.append(
                    f"  {mv['name_cn']} — 公式：{mv['formula']}\n"
                    f"    规则：{'；'.join(mv['rules'])}\n"
                    f"    提示词模板：{mv['prompt_template']}"
                )
            creative_prompt_hints += "\n[非人战斗母题]\n" + "\n".join(motif_lines)

        # — 视频增强用（在创意基础上增加非人视频规则） —
        video_prompt_hints = creative_prompt_hints
        if nonhuman_video_ctx:
            i2v = nonhuman_video_ctx["i2v_first_frame"]
            specs = nonhuman_video_ctx["sweet_spot_specs"]
            pipeline = nonhuman_video_ctx["prompt_assembly_pipeline"]
            video_prompt_hints += (
                f"\n[非人实体视频规则]\n"
                f"I2V首帧限制：{i2v['max_allowed']}\n"
                f"适合动作：{', '.join(i2v['suitable_actions'])}\n"
                f"不适合动作：{', '.join(i2v['unsuitable_actions'])}\n"
                f"设计锁定模板：{i2v['design_lock_template']}\n"
                f"甜点区规格：方法={specs['default_method']}，禁止={', '.join(specs['forbidden'])}\n"
                f"组装流水线：{' → '.join(pipeline['steps'])}"
            )

        # — 图片增强用（精简版，只注入跨域和反模式供参考） —
        image_prompt_hints = ""
        if matched_domain_elements:
            domain_hint_lines = []
            for dk, dv in matched_domain_elements.items():
                domain_hint_lines.append(f"  {dk}: {'; '.join(h['name_cn'] for h in dv[:3])}")
            image_prompt_hints = "[跨域参考元素]\n" + "\n".join(domain_hint_lines)

        return {
            "matched_methods": matched_methods,
            "resolved_methods": resolved_methods,
            "domain_candidates": domain_candidates,
            "matched_domain_elements": matched_domain_elements,
            "anti_patterns": matched_anti_patterns,
            "nonhuman_motif_ctx": nonhuman_motif_ctx,
            "nonhuman_video_ctx": nonhuman_video_ctx,
            "image_prompt_hints": image_prompt_hints,
            "video_prompt_hints": video_prompt_hints,
            "creative_prompt_hints": creative_prompt_hints,
        }

    def _select_creative_methods(self, prompt: str) -> list[str]:
        """根据用户描述自动选择最匹配的创意方法

        来源：V2 跨域嫁接创意引擎 + 反模式思维层 + 思维技法层 + AI特化思维层

        Args:
            prompt: 用户原始提示词
        Returns:
            2-3种最匹配的创意方法标识列表
        """
        p = prompt.lower()

        method_keywords = {
            "cross_domain_graft": ["嫁接", "跨域", "组合", "混搭", "graft", "cross-domain", "mix"],
            "anti_pattern": ["反模式", "颠覆", "破坏", "反转", "悖论", "反常", "paradox", "invert"],
            "SCAMPER": ["替换", "合并", "修改", "消除", "substitute", "combine", "modify", "eliminate"],
            "TRIZ": ["发明", "原理", "分割", "嵌套", "invent", "principle", "segment", "nest"],
            "first_principles": ["拆解", "本质", "底层", "基本", "principle", "fundamental", "decompose"],
            "latent_nav": ["前所未有", "从未见过", "novel", "unprecedented", "从未存在"],
            "style_hijack": ["风格碰撞", "混搭风格", "风格冲突", "style clash", "style fusion"],
            "glitch": ["故障", "glitch", "bug", "错误", "崩溃", "故障艺术", "corrupt"],
        }

        scores = {}
        for method, keywords in method_keywords.items():
            score = sum(1 for kw in keywords if kw in p)
            if score > 0:
                scores[method] = score

        sorted_methods = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        methods = [m for m, s in sorted_methods[:3]] if sorted_methods else []

        # 兜底：默认使用跨域嫁接+反模式（最通用的创造性组合）
        if not methods:
            methods = ["cross_domain_graft", "anti_pattern"]

        return methods

    def creative_leap(self, user_prompt: str, methods: list[str] | None = None) -> dict:
        """创意飞跃：运用超越常人的思维方法主动生成突破性创意

        来源：V2 跨域嫁接创意引擎 + 反模式思维层 + 思维技法层 + AI特化思维层 + 创意飞跃包

        Args:
            user_prompt: 用户原始描述
            methods: 指定使用的创意方法列表，可选值：
                cross_domain_graft / anti_pattern / SCAMPER / TRIZ
                first_principles / latent_nav / style_hijack / glitch
                None 时由系统自动选择2-3种最匹配的方法
        Returns:
            创意飞跃结果 dict，包含多个候选方案+护栏检查
        """
        # 自动选择方法
        if not methods:
            methods = self._select_creative_methods(user_prompt)

        # 注入实体信息
        entity_type, surface_policy = self._infer_entity_type(user_prompt)
        context = f"原始描述：{user_prompt}\n\n"
        if entity_type:
            context += f"[实体类型：{ENTITY_TYPE_MAP[entity_type]['name_cn']}({entity_type})]\n"
            context += f"[表面策略：{surface_policy}]\n"
            context += "[创意规则：非人实体的表面材质/能量逻辑不可被创意方法随意破坏]\n\n"

        # 注入战斗知识（通过路由器一次性解析所有战斗常量）
        combat_ctx = self._detect_combat_scene(user_prompt, "image")
        if combat_ctx:
            context += combat_ctx["creative_prompt_hints"] + "\n"

        # 注入创意知识（通过路由器一次性解析5大创意常量，替换硬编码方法描述）
        creative_ctx = self._resolve_creative_knowledge(user_prompt, "image")
        if creative_ctx and creative_ctx.get("creative_prompt_hints"):
            context += creative_ctx["creative_prompt_hints"] + "\n"

        text = self._ask_brain(CREATIVE_LEAP_PROMPT, context, temperature=0.8)
        result = self._parse_json(text)
        result.setdefault("original_concept", user_prompt)
        result.setdefault("creative_leaps", [])
        result.setdefault("guardrail_check", {
            "story_function_readable": True,
            "conflict_visible": True,
            "emotional_turn_clear": True,
            "visual_payoff_worth": True,
        })

        # 对每个飞跃结果叠加甜点区和风险预判
        for leap in result.get("creative_leaps", []):
            if "optimized_prompt" in leap:
                template = self._match_sweet_spot(leap["optimized_prompt"], "image", entity_type)
                if template:
                    leap["sweet_spot"] = template["name"]
                    leap["negative_prompt"] = self._merge_negative(
                        leap.get("negative_prompt", ""), template["negative"]
                    )

        # 推荐方案的安全检查
        idx = result.get("recommended_leap_index", 0)
        leaps = result.get("creative_leaps", [])
        if leaps and idx < len(leaps):
            guard = result.get("guardrail_check", {})
            if not all(guard.values() if isinstance(guard, dict) else [guard]):
                result["guardrail_warning"] = "推荐方案未通过护栏检查，建议选择更保守的方案或降低创意强度"

        # 记录使用的方法
        result["methods_used"] = methods

        return result
