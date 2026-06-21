"""Brain data: entities knowledge base."""
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
