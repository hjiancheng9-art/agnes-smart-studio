"""Brain data: creative knowledge base."""
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

