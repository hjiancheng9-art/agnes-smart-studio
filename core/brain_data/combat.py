"""Brain data: combat knowledge base."""

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
                "name_cn": "波动拳",
                "type": "飞行道具",
                "prompt_cn": "格斗家侧身蓄力，蓝色气功能量在掌心凝聚旋转，双手猛推，蓝色半透明能量球高速飞出，周围白色气流旋涡，拖淡蓝光尾，照亮地面",
                "prompt_en": "Martial artist thrusts both hands forward, launching a translucent blue energy orb at high speed, surrounded by white spiraling air currents and a light blue trailing beam, blue glow on ground",
                "phases": "预备蓄力→出招推出→飞行→命中冲击→收招→残留消散",
                "vfx_palette": "ki_blue",
                "camera": "侧面跟拍",
            },
            "shoryuken": {
                "name_cn": "升龙拳",
                "type": "对空技",
                "prompt_cn": "从蹲姿猛然爆发，右拳自下而上弧线跃空，拳锋白色气旋冲击波，升至最高点定格，受重力下落",
                "prompt_en": "Fighter explodes upward from crouch, right fist tracing an arc from low to high, white air-burst shockwave at apex, hangs at peak before gravity pulls back down",
                "phases": "蹲姿蓄力→爆发上升→空中旋转→顶点定格→下落→落地",
                "vfx_palette": "sonic_white",
                "camera": "低角度仰拍+上摇",
            },
            "tatsumaki": {
                "name_cn": "龙卷旋风脚",
                "type": "旋转突进",
                "prompt_cn": "单脚支撑，身体像陀螺水平旋转向前突进，白色旋风包裹全身，腿部残影明显",
                "prompt_en": "Fighter spins like a top while advancing forward, white whirlwind envelops the body, leg afterimages from rapid rotation",
                "phases": "侧身蓄力→起旋→全速旋转突进→减速停止→残留",
                "vfx_palette": "sonic_white",
                "camera": "Top-down俯拍/侧面跟拍",
            },
            "shinku_hadoken": {
                "name_cn": "真空波动拳",
                "type": "超必杀",
                "prompt_cn": "全身蓝色气焰爆发，双手画圆聚合，巨大蓝色能量球在掌心生成，推出化为粗壮蓝色光束，地面裂缝发光",
                "prompt_en": "Blue ki aura erupts, massive energy sphere generated between palms, released as thick blue beam with spiraling white energy streams, ground cracks and glows beneath",
                "phases": "气焰爆发→能量凝聚→光束发射→光束飞行→命中爆炸→消散",
                "vfx_palette": "ki_blue",
                "camera": "侧后方over-the-shoulder",
            },
        },
        "ken": {
            "flaming_shoryuken": {
                "name_cn": "火焰升龙拳",
                "type": "对空技(火焰)",
                "prompt_cn": "升龙拳轨迹但拳锋包裹橙红色火焰，上升火焰拖出长火尾，火花粒子迸射，橙→红→暗红渐变",
                "prompt_en": "Same trajectory as Shoryuken but fist engulfed in orange-red flames, fire trail during ascent, ember particles spray, orange to crimson gradient",
                "phases": "蹲姿→爆发上升(火焰)→顶点→下落→落地",
                "vfx_palette": "fire_orange",
                "camera": "低角度仰拍",
            },
        },
        "chunli": {
            "hyakuretsukyaku": {
                "name_cn": "百裂脚",
                "type": "连续打击",
                "prompt_cn": "单脚站立，另一腿极高频率连续踢出，扇形残影阵列，白色冲击波纹和小型气旋，蓝白色气劲环绕",
                "prompt_en": "Stands on one leg, other leg kicking at extreme frequency, fan-shaped afterimage array, white impact rings, blue-white ki aura",
                "phases": "起手→加速踢击→极速残影→减速→收招",
                "vfx_palette": "ki_blue",
                "camera": "正面/侧面中景",
            },
            "spinning_bird_kick": {
                "name_cn": "旋圆蹴",
                "type": "旋转上升",
                "prompt_cn": "双手撑地倒立，双腿并拢像钻头旋转上升，脚尖螺旋白色气流，地面圆形尘土扩散",
                "prompt_en": "Handstand, legs together spinning upward like a drill, white spiraling air currents from toes, circular dust spread on ground",
                "phases": "倒立→起旋→旋转上升→落地",
                "vfx_palette": "sonic_white",
                "camera": "Top-down/侧面仰拍",
            },
        },
        "guile": {
            "sonic_boom": {
                "name_cn": "音速手刀",
                "type": "飞行道具",
                "prompt_cn": "单手向前挥斩，半月形白色气刃高速旋转飞行，锯齿状白色气流轨迹，颜色白→淡青渐变",
                "prompt_en": "Swings one arm forward launching a crescent-shaped white sonic blade spinning at high speed, serrated white trail, white to pale cyan gradient",
                "phases": "蓄力→挥斩→气刃飞行→命中",
                "vfx_palette": "sonic_white",
                "camera": "侧面跟拍",
            },
            "flash_kick": {
                "name_cn": "筋斗踢",
                "type": "对空技",
                "prompt_cn": "从蹲姿猛然后空翻，双腿向上弧线踢出，脚尖白色半月形光刃轨迹",
                "prompt_en": "Backflip from crouch, both legs tracing upward arc with white crescent blade trails from toes",
                "phases": "蹲蓄→后空翻→弧线踢→落地",
                "vfx_palette": "sonic_white",
                "camera": "侧面固定",
            },
        },
    },
    "king_of_fighters": {
        "kyo": {
            "oniyaki": {
                "name_cn": "鬼烧(火焰升龙)",
                "type": "对空技(火焰)",
                "prompt_cn": "右拳向上弧线挥出，橙红色火焰包裹前臂延伸1米，大量火星粒子如烟花迸射，亮橙→红→暗红渐变",
                "prompt_en": "Right fist swings upward in arc, orange-red flames extending 1m up forearm, ember particles spraying like fireworks, bright orange to crimson gradient",
                "phases": "蓄力→爆发上升→火焰峰值→下落→收招",
                "vfx_palette": "fire_orange",
                "camera": "侧面/低角度",
            },
            "aragami_chain": {
                "name_cn": "荒咬→九伤→八锖",
                "type": "派生连击(火焰)",
                "prompt_cn": "火焰冲拳突进(荒咬)→下向上撩击火焰上窜(九伤)→全力轰出巨大火球(八锖)，火焰一次比一次猛烈",
                "prompt_en": "Fiery charging punch (Aragami) → upward swing with surging flames (Kizu) → explosive full-force blow erupting into massive fireball (Yasakani), each hit more intense",
                "phases": "荒咬突进→九伤上撩→八锖爆发→火球消散→收招",
                "vfx_palette": "fire_orange",
                "camera": "正面中景→极近特写",
            },
            "orochinagi": {
                "name_cn": "大蛇薙",
                "type": "超必杀(火柱)",
                "prompt_cn": "全身橙色火焰气焰爆发，右臂后拉火焰柱→猛挥，地面2m直径旋转火柱冲天3m高，如火龙卷",
                "prompt_en": "Massive orange flame aura, right arm pulled back with dragon-like fire pillar, swings forward — colossal swirling fire tornado erupts from ground, 2m diameter 3m tall",
                "phases": "蓄力(火臂)→挥出→火柱爆发→火柱衰减→残留焦痕",
                "vfx_palette": "fire_orange",
                "camera": "斜侧+震动",
            },
        },
        "iori": {
            "yaotome_claw": {
                "name_cn": "葵花(三段爪击)",
                "type": "连续打击(紫焰)",
                "prompt_cn": "三段爪击：斜抓→反手横抓(紫色X形残影)→双手合拢下砸紫色能量爆发，紫色火焰闪烁",
                "prompt_en": "Three consecutive claw strikes: diagonal slash → backhand with crossing purple light trails → downward smash with purple energy burst, purple flames flickering between hits",
                "phases": "蓄紫能→第一爪→第二爪→第三爪爆发→收招",
                "vfx_palette": "purple_dark",
                "camera": "正面中景",
            },
            "orochi_yaotome": {
                "name_cn": "八稚女",
                "type": "超必杀(狂乱连击)",
                "prompt_cn": "狂笑突进，全身紫色火焰，连续8-12次疯狂爪击，紫色光轨充满画面，最后双手抓头紫色能量全屏爆炸",
                "prompt_en": "Maniacal lunge engulfed in purple flames, 8-12 frenzied claw strikes flooding the frame with purple light trails, final head-grab triggers full-screen purple energy explosion",
                "phases": "暴走→突进→狂乱连击→终结抓取→全屏爆炸→狂笑",
                "vfx_palette": "purple_dark",
                "camera": "多角度快切+闪光",
            },
            "kuzukaze": {
                "name_cn": "屑风(指令投)",
                "type": "投技",
                "prompt_cn": "单手掐脖领提起旋转180°重摔地面，手臂紫色气焰，地面龟裂尘土冲击波",
                "prompt_en": "One-hand collar grab, lifts and rotates 180° then slams hard into ground, purple flames on arm, ground cracks and dust shockwave",
                "phases": "抓取→提起旋转→猛砸→甩手",
                "vfx_palette": "purple_dark",
                "camera": "环绕镜头",
            },
        },
    },
    "tekken": {
        "kazuya": {
            "ewgf": {
                "name_cn": "最速风神拳",
                "type": "突进上勾拳(雷电)",
                "prompt_cn": "自然站姿瞬间突进，右拳斜上挥出，蓝色雷电爆发电弧呈树枝状扩散，命中蓝白电光爆炸",
                "prompt_en": "Instant dash from neutral stance, right fist swinging diagonally upward, intense blue lightning erupts from knuckles with branching arcs, blue-white electric explosion on hit",
                "phases": "预备→瞬间突进→电光爆发→电弧消散→残留电光",
                "vfx_palette": "lightning_blue",
                "camera": "微低角度",
            },
            "devil_wings_kick": {
                "name_cn": "恶魔飞翼",
                "type": "突进飞踢",
                "prompt_cn": "助跑腾空飞踢，身后隐约紫色半透明蝙蝠状恶魔翅膀虚影，命中时翅膀瞬间清晰，紫色能量脉络流动",
                "prompt_en": "Running flying kick, translucent purple bat-like demon wings phantom behind, wings momentarily solidify on impact with purple energy veins pulsing",
                "phases": "助跑→腾空→飞踢(翅膀虚影)→命中→消散",
                "vfx_palette": "purple_dark",
                "camera": "侧面跟拍",
            },
        },
        "jin": {
            "lightning_screw": {
                "name_cn": "雷闪",
                "type": "下段拳击(雷电)",
                "prompt_cn": "快速下蹲向前方地面挥拳，蓝色小型雷电效果，击中地面蓝色电弧溅射和尘土飞散",
                "prompt_en": "Quick crouch and punch toward ground, small blue electric sparks, blue arc splash and dust on ground impact",
                "phases": "下蹲→挥拳→电弧溅射→收招",
                "vfx_palette": "lightning_blue",
                "camera": "侧面近景",
            },
        },
    },
    "mortal_kombat": {
        "scorpion": {
            "spear": {
                "name_cn": "飞矛(Get Over Here!)",
                "type": "远程抓取",
                "prompt_cn": "从背后抽出带锁链苦无猛力投掷，锁链S形波浪摆动，命中后锁链绷直猛拉，对手被拖拽滑行",
                "prompt_en": "Hurls a chain-linked kunai, chain trailing in S-curve wave, on hit chain snaps taut and yanks opponent sliding across ground",
                "phases": "投掷→飞行(S链)→命中绷直→拖拽→近身",
                "vfx_palette": "fire_orange",
                "camera": "侧后方",
            },
            "hellfire": {
                "name_cn": "地狱火",
                "type": "地面火焰",
                "prompt_cn": "单手拍地，地面裂开喷涌橙红色地狱之火2米高，隐约可见骷髅面孔火焰纹理",
                "prompt_en": "Slams hand on ground, ground cracks open erupting orange-red hellfire 2m high, faint skull-face shaped flame patterns visible",
                "phases": "拍地→裂开→火焰喷涌→衰减→残留烟雾",
                "vfx_palette": "fire_orange",
                "camera": "低角度",
            },
        },
        "subzero": {
            "ice_ball": {
                "name_cn": "冰球",
                "type": "飞行道具(冻结)",
                "prompt_cn": "双手凝聚寒气，冰晶球体掌心生成(霜花纹理+蓝色能量核心)，推出飞行留冰晶粒子，命中瞬间冻结包裹",
                "prompt_en": "Gathers freezing energy, crystalline ice sphere with frost patterns and blue core, launched leaving ice crystal particles, instant freeze encasement on hit",
                "phases": "聚寒→冰球生成→飞行→命中冻结→残留冰晶",
                "vfx_palette": "ice_cyan",
                "camera": "侧面跟拍",
            },
            "ice_slide": {
                "name_cn": "冰滑",
                "type": "滑行铲腿",
                "prompt_cn": "俯身向前滑行，脚下生成冰道，冰晶从无到有快速生长，镜面光滑",
                "prompt_en": "Leans forward and slides, ice track forming beneath feet, ice crystals rapidly growing from nothing into mirror-smooth surface",
                "phases": "俯身→滑行(冰道生成)→铲腿命中→残留冰道",
                "vfx_palette": "ice_cyan",
                "camera": "侧面跟拍",
            },
        },
    },
    # ══ 热门网游 ══
    "honor_of_kings": {
        "libai": {
            "qinglian_sword_song": {
                "name_cn": "青莲剑歌",
                "type": "终极技(多段AOE)",
                "prompt_cn": "化身五道青色幻影交错穿梭切割，剑痕交汇绽放巨大青莲花(花瓣由剑气构成)，花心白色光柱冲天",
                "prompt_en": "Transforms into five cyan phantoms crisscross slashing, sword trails intersect blooming into a massive green lotus with razor-sharp petal blades, white beam erupting from flower center",
                "phases": "剑气汇聚→一分为五→穿梭切割→莲花绽放→光柱冲天→归一收剑",
                "vfx_palette": "dragon_green",
                "camera": "俯瞰环绕",
            },
            "jiangjinjiu": {
                "name_cn": "将进酒",
                "type": "三段位移",
                "prompt_cn": "三段突进(前→锐角转向→瞬移回原点)，青色水墨残影轨迹，酒杯雾化，地面三个墨晕圈",
                "prompt_en": "Three dashes (forward → sharp angle → recall to origin), cyan ink-wash afterimage trails, wine mist, three ink bloom circles on ground",
                "phases": "一段突进→二段转向→三段回原点→举杯收招",
                "vfx_palette": "dragon_green",
                "camera": "45°斜侧",
            },
        },
        "diaochan": {
            "zhanfenghua": {
                "name_cn": "绽风华",
                "type": "终极技(领域展开)",
                "prompt_cn": "优雅起舞，粉紫花瓣螺旋飘散形成20m圆形领域，花瓣屏障，地面盛唐牡丹花纹发光，每转一圈花瓣冲击波扩散",
                "prompt_en": "Graceful dance, pink-purple petals spiral outward forming 20m circular domain, petal barrier, Tang Dynasty peony ground patterns, petal shockwave per rotation",
                "phases": "起舞→领域展开→连续旋转→终极绽放→花瓣雨→残留",
                "vfx_palette": "nature_petal_pink",
                "camera": "俯瞰广角→轨道环绕",
            },
        },
        "wukong": {
            "dashengshenwei": {
                "name_cn": "大圣神威",
                "type": "终极技(AOE击飞)",
                "prompt_cn": "金箍棒急速变大至10m擎天巨柱，篆文点亮金色箍环旋转，跃起猛砸地面，金色冲击波海啸般扩散，碎石飞溅",
                "prompt_en": "Ruyi Jingu Bang rapidly grows to 10m sky-piercing pillar, golden seal script ignites, leaps and slams down with earth-shattering force, golden tsunami shockwave, debris flying",
                "phases": "召唤→变大→跃起→砸下→冲击波→收棒",
                "vfx_palette": "divine_gold",
                "camera": "低角度仰拍+侧面跟拍",
            },
        },
        "angela": {
            "chireguanghui": {
                "name_cn": "炽热光辉",
                "type": "终极技(火焰激光)",
                "prompt_cn": "魔法书悬浮翻页燃烧，喷出1m直径火焰光束(白核→橙焰→红黑热浪)，地面烧出焦黑沟壑，小萝莉后坐力滑行",
                "prompt_en": "Floating burning tome erupts 1m diameter fire beam (white plasma core → orange flames → red-black heat distortion), charred trench in ground, petite girl pushed back by recoil",
                "phases": "蓄力→喷射→持续输出→衰减→收招→地面冒烟",
                "vfx_palette": "magma_orange",
                "camera": "侧后方跟拍",
            },
        },
        "hanxin": {
            "guoshiwushuang": {
                "name_cn": "国士无双",
                "type": "终极技(枪舞)",
                "prompt_cn": "长枪四圈横扫：一圈尘土→二圈上挑银光→三圈满环银色光环→四圈猛挑银龙气劲冲天，击飞一切",
                "prompt_en": "Silver spear four sweeps: dust → upward silver blade-light → complete silver ring → upward thrust launches silver-white dragon-shaped energy skyward",
                "phases": "蓄力→一圈→二圈→三圈满环→四圈冲天→收枪",
                "vfx_palette": "sonic_white",
                "camera": "轨道环绕",
            },
        },
    },
    "league_of_legends": {
        "yasuo": {
            "last_breath": {
                "name_cn": "狂风绝息斩",
                "type": "终极技(空中连斩)",
                "prompt_cn": "瞬间闪烁到空中敌人旁，慢动作悬浮三连斩(横斩音锥→竖斩月牙风刃→全力劈下砸地)，青色旋风扩散",
                "prompt_en": "Blinks to airborne enemy, slow-motion three slashes (horizontal sonic cone → vertical crescent wind slash → overhead slam), cyan whirlwind blast on landing",
                "phases": "闪烁→慢动作悬浮→横斩→竖斩→劈下砸地→归鞘",
                "vfx_palette": "sonic_white",
                "camera": "轨道环绕+慢动作",
            },
        },
        "lux": {
            "final_spark": {
                "name_cn": "终极闪光",
                "type": "终极技(全图激光)",
                "prompt_cn": "法杖水晶变纯白，金色符文法阵3层旋转展开，喷射2m直径纯白光束(金粉光晕+彩虹折射)，空气电离闪电，地面金色沟壑",
                "prompt_en": "Staff crystal turns blinding white, 3-layer golden rune array, 2m diameter pure white beam with golden-pink halos and rainbow refraction, ionizing air lightning, golden ground trench",
                "phases": "蓄能→光束喷射→持续输出→衰减→收招→沟壑发光",
                "vfx_palette": "divine_gold",
                "camera": "侧后方→缓慢滑到正面",
            },
        },
        "zed": {
            "death_mark": {
                "name_cn": "瞬狱影杀阵",
                "type": "终极技(暗影刺杀)",
                "prompt_cn": "化为三道黑色暗影聚拢目标，掠过留红色X斩痕，真身身后现身单手结印，死亡印记(血红色手里剑)旋转脉冲后暗红爆炸",
                "prompt_en": "Body disperses into three dark shadows converging on target, X-shaped blood-red slash marks, real form materializes behind forming ninja seal, death mark (shuriken) pulses then detonates in dark red explosion",
                "phases": "化影→掠过斩痕→印记旋转→印记爆炸→终结→残留",
                "vfx_palette": "shadow_crimson",
                "camera": "侧面跟拍+慢动作",
            },
        },
        "jinx": {
            "super_mega_death_rocket": {
                "name_cn": "超究极死神飞弹",
                "type": "终极技(全图火箭)",
                "prompt_cn": "扛起鱼骨头火箭炮疯狂发射，鲨鱼涂装火箭歪歪扭扭飞越全图，尾焰从橙红变炽白，命中巨大蘑菇云+卡通星星飞出+涂鸦笑脸印记",
                "prompt_en": "Hoists Fishbones launcher, maniacal launch, shark-painted rocket wobbles across entire map, exhaust shifts orange-red to blazing white, massive mushroom cloud + cartoon stars + graffiti grin mark on explosion site",
                "phases": "装弹→发射→飞越全图→迫近→命中爆炸→狂笑",
                "vfx_palette": "shadow_crimson",
                "camera": "俯瞰全程+POV终点",
            },
        },
    },
    "world_of_warcraft": {
        "mage": {
            "pyroblast": {
                "name_cn": "炎爆术",
                "type": "核心输出(大型火球)",
                "prompt_cn": "三层橙色符文法阵旋转展开，4秒蓄力凝聚2m直径熔岩火球(半固态岩浆+黑色碎片漂浮+白金核心)，缓慢但不可阻挡飞行，命中'融化'而非爆炸",
                "prompt_en": "3-layer orange runic arrays, 4s channel凝聚 2m molten fireball (semi-liquid magma surface + floating rock fragments + platinum-white core), slow unstoppable advance, 'melting' not explosion on hit",
                "phases": "施法→法阵展开→火球成形→缓慢飞行→吞没目标→岩浆池冷却",
                "vfx_palette": "magma_orange",
                "camera": "侧面跟拍+慢动作",
            },
            "blink": {
                "name_cn": "闪现术",
                "type": "位移",
                "prompt_cn": "身体瞬间'折叠'为蓝色光点，20码外展开重组，蓝色奥术符文轨迹连接，起点碎裂消散，终点奥术新星",
                "prompt_en": "Body instantly 'folds' into blue light particles, unfolds and reassembles 20 yards away, blue arcane rune trail connecting points, origin shatters like broken mirror, arcane nova at destination",
                "phases": "折叠→传送→展开→消散",
                "vfx_palette": "ki_blue",
                "camera": "侧面同时拍起点终点",
            },
        },
        "warrior": {
            "bladestorm": {
                "name_cn": "剑刃风暴",
                "type": "AOE终结(旋风)",
                "prompt_cn": "怒吼后疯狂旋转，人剑合一5m直径灰色金属旋风，地面环形沟槽，被卷入一切切碎抛飞，人形绞肉机",
                "prompt_en": "Battle roar then frenzied spin, warrior and blade fuse into 5m diameter gray-metallic whirlwind, ground carved into circular grooves, everything caught shredded and flung outward",
                "phases": "蓄力怒吼→起转→全速风暴→衰减→停转插地→沉降",
                "vfx_palette": "fire_orange",
                "camera": "环绕+俯拍切换",
            },
        },
        "druid": {
            "starfall": {
                "name_cn": "星落",
                "type": "AOE终极(星雨)",
                "prompt_cn": "枭兽呼唤夜空，天空变暗切换星空模式，成百上千星辰碎片暴雨坠落(蓝白→紫罗兰彗星尾)，地面千疮百孔毁灭美感",
                "prompt_en": "Moonkin calls the night sky, sky darkens to starry mode, hundreds of star fragments rain down with blue-white to violet comet tails, ground pockmarked with destructive beauty",
                "phases": "召唤→初星→密集星雨→渐稀→收束→残余星光",
                "vfx_palette": "celestial_bluepurple",
                "camera": "广角俯瞰→缓慢推进",
            },
        },
    },
    "overwatch": {
        "genji": {
            "dragonblade": {
                "name_cn": "龙刃",
                "type": "终极技(近战爆发)",
                "prompt_cn": "绿龙从背后盘绕出缠绕手臂凝聚为翡翠能量长刃(龙鳞纹理+流动绿光粒子)，每次斩击龙啸+翠绿弧形刀光+龙形残影，斩杀后绿龙灵魂升天",
                "prompt_en": "Emerald dragon coils from behind condensing into jade energy blade with dragon scale texture and flowing green particles, each slash with dragon roar and lingering emerald arc with dragon afterimage, green dragon souls rise from fallen",
                "phases": "跪地拔刀→龙缠绕成刃→连续斩击→龙魂升天→收刀→绿光飘散",
                "vfx_palette": "dragon_green",
                "camera": "低角度环绕+慢动作",
            },
        },
        "dva": {
            "self_destruct": {
                "name_cn": "自毁",
                "type": "终极技(AOE毁灭)",
                "prompt_cn": "机甲警报核心变红裂纹蔓延→D.Va弹射离开→蓄爆颤抖→白屏0.2s→巨大蘑菇云+球形冲击波→粉色橙色光芒→D.Va落地持小手枪",
                "prompt_en": "Mech alarm, core turns red with spreading cracks → D.Va ejects → shuddering buildup → 0.2s white flash → massive mushroom cloud + spherical shockwave in pink/orange → D.Va lands with tiny pistol",
                "phases": "警报→弹射→蓄爆→白屏→爆炸→落地→残留",
                "vfx_palette": "mecha_blue",
                "camera": "环绕机甲→急剧拉远",
            },
        },
        "hanzo": {
            "dragonstrike": {
                "name_cn": "龙撃波",
                "type": "终极技(贯穿双龙)",
                "prompt_cn": "龙纹箭矢超音速飞出10m后'融化'化为两条3m直径深蓝东方巨龙DNA双螺旋飞驰，穿透一切留龙形空洞，双龙冲天消散",
                "prompt_en": "Dragon-marked arrow flies supersonic, after 10m 'melts' into two 3m diameter deep blue Eastern dragons racing in DNA double-helix, piercing everything leaving dragon-shaped holes, dragons soar skyward and vanish",
                "phases": "搭箭→箭矢飞行→融化变形→双龙飞驰→贯穿→冲天消散",
                "vfx_palette": "celestial_bluepurple",
                "camera": "侧面跟拍双龙",
            },
        },
    },
    "genshin_impact": {
        "zhongli": {
            "planet_befall": {
                "name_cn": "天星",
                "type": "元素爆发(陨石)",
                "prompt_cn": "单手挥令天空撕裂，金色岩陨石(远古璃月符文+几何多面体)加速下降砸地，环形岩刺放射+金色冲击波，范围内石化成灰色雕像",
                "prompt_en": "One hand sweeps forward, sky tears open, golden Geo meteorite with ancient Liyue runes and geometric polyhedron shape crashes down, radial Geo spikes + golden shockwave, enemies petrified into gray statues",
                "phases": "号令→天裂→陨落→命中→石化→收手威压",
                "vfx_palette": "divine_gold",
                "camera": "仰拍→侧面跟拍→地面冲击",
            },
        },
        "raiden_shogun": {
            "musou_no_hitotachi": {
                "name_cn": "无想的一刀",
                "type": "元素爆发(空间撕裂斩)",
                "prompt_cn": "胸口空间裂开紫色裂缝拔出纯雷等离子太刀，环境失色化(只剩紫灰)，一刀劈下撕裂空间30m紫色裂缝，无尽雷光扇形涌出",
                "prompt_en": "Chest spatial rift opens, draws pure lightning plasma tachi, environment desaturates to purple-gray, one slash tears space itself leaving 30m purple rift, endless lightning pours out in fan shape",
                "phases": "拔刀→聚势(失色化)→斩击(慢放)→雷暴→裂缝愈合→余电",
                "vfx_palette": "electro_purple",
                "camera": "环绕+侧面跟拍刀锋",
            },
        },
        "hutao": {
            "spirit_soother": {
                "name_cn": "安神秘法",
                "type": "元素爆发(火焰幽灵)",
                "prompt_cn": "护摩杖指前，巨大可爱白色幽灵浮现→瞬间橙红恶魔化膨胀5倍→巨口喷射扇形地狱烈焰+红色蝴蝶飞舞→胡桃蹦跳",
                "prompt_en": "Staff points forward, huge cute white spirit appears → instantly transforms into orange-red demon form expanding 5x → massive jaw unleashes fan-shaped hellfire + red butterflies → Hu Tao bounces happily",
                "phases": "召唤→可爱幽灵→恶魔化→烈焰喷射→消退",
                "vfx_palette": "fire_orange",
                "camera": "正面中景",
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
