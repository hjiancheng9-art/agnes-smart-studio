# 方案：将新烬龙V2拟人/非人/灵体知识嵌入 CRUX Studio

> 原则：只读取V2知识源，不修改V2任何文件

---

## 现状差距

| 能力 | V2 | CRUX |
|------|-----|-------|
| 实体分类 | 10种（spirit/energy_body/anthropomorphic/robot/AI/creature/animal/vehicle_character/object_character/human_or_humanoid） | 仅3类（person/animal/anime） |
| 实体推断 | `inferPrimaryCharacterEntity()` 正则自动识别 | 无 |
| 身份策略 | 非人→锁定材质/皮毛/外壳/能量色调 | 无 |
| 形态演化 | 基础形态→变身形态→成长阶段→连续性锁→禁止变异 | 无 |
| 实体专属负面词 | 每种类型有专属失败模式 | 无 |
| 实体嫁接 | 8种嫁接目标 | 无 |

---

## 实施方案（7步）

### 第1步：新增 `ENTITY_TYPE_MAP` 实体类型推断表

**文件**：`core/brain.py`（模块级常量，在 `NEGATIVE_REPAIR_MAP` 之后）

从V2的 `inferPrimaryCharacterEntity()` 移植，将正则转为Python关键词列表映射：

```python
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
        "keywords": ["猫", "狗", "鸟", "鱼", "虎", "龙(东方)", "马",
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
```

新增方法 `_infer_entity_type(self, prompt: str) -> str | None`：
- 遍历 `ENTITY_TYPE_MAP`，按优先级匹配关键词
- 优先级：spirit > energy_body > anthropomorphic > robot > AI > creature > animal > vehicle_character > object_character
- 无匹配返回 `None`（即 human_or_humanoid）

---

### 第2步：新增 `ENTITY_SWEET_SPOT_TEMPLATES` 实体专属甜点区

**文件**：`core/brain.py`（模块级常量）

每种非人实体类型有专属的正面/负面甜点区模板：

```python
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
```

---

### 第3步：新增 `ENTITY_NEGATIVE_REPAIR_MAP` 实体专属失败修复映射

**文件**：`core/brain.py`（模块级常量）

在现有 `NEGATIVE_REPAIR_MAP` 基础上，为每种非人实体新增专属失败模式：

```python
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
```

---

### 第4步：重写 `_match_sweet_spot()` → 拆分为 `_infer_entity_type()` + `_match_sweet_spot()`

**文件**：`core/brain.py`

**4.1 新增 `_infer_entity_type()`**：
- 遍历 `ENTITY_TYPE_MAP`，按固定优先级匹配关键词
- 返回实体类型字符串或 `None`（表示 human_or_humanoid）
- 同时返回 `surface_policy` 用于后续身份策略

**4.2 改写 `_match_sweet_spot()`**：
- 先调 `_infer_entity_type()` 判断实体类型
- 如果是非人实体 → 从 `ENTITY_SWEET_SPOT_TEMPLATES` 取专属模板
- 如果是人类/未识别 → 走原有7类模板逻辑
- 返回值增加 `entity_type` 和 `surface_policy` 字段

---

### 第5步：增强 `enhance_image_prompt()` 和 `enhance_video_prompt()`

**文件**：`core/brain.py`

**5.1 实体感知的 Prompt 增强**：
- 在调用 `_ask_brain()` 前，如果检测到非人实体类型，将实体类型信息注入用户输入：
  ```
  [实体类型：灵体(spirit) — 表面策略：translucent, ethereal, luminous body; no solid flesh, no human skin tone]
  原始描述：一个灵体在月光下漂浮
  ```
- 这样 LLM 在生成优化提示词时就知道主体是非人实体，不会生成人类肤色/质感描述

**5.2 实体专属甜点区叠加**：
- `_match_sweet_spot()` 返回非人实体的专属模板后，叠加其 `suffix` 和 `negative`

**5.3 实体专属风险预判**：
- `_predict_risks()` 增加实体类型参数
- 对非人实体，从 `ENTITY_NEGATIVE_REPAIR_MAP` 额外提取该实体类型的专属失败风险
- 将实体专属修复关键词也合并到 `negative_prompt`

**5.4 形态演化控制注入**：
- 非人实体 → 在返回结果中新增 `form_evolution` 字段：
  ```python
  "form_evolution": {
      "base_form": "基础可读轮廓",
      "transformed_form": "变身/觉醒形态（如适用）",
      "continuity_locks": ["身份核心", "轮廓关系", "材质/能量逻辑", "识别标记"],
      "forbidden_changes": ["随机物种替换", "无动机材质变化", "丢失身份核心", "装饰性突变"]
  }
  ```
- 如果用户描述中包含变身/进化关键词，激活 `transformed_form`

**5.5 表面材质策略注入**：
- 非人实体 → 在返回结果中新增 `surface_policy` 字段，来自 `ENTITY_TYPE_MAP`
- 确保负面提示词中排除"人类肤色/质感"相关词汇

---

### 第6步：更新 `ENHANCE_IMAGE_PROMPT` 和 `ENHANCE_VIDEO_PROMPT`

**文件**：`core/brain.py`

**6.1 `ENHANCE_IMAGE_PROMPT` 增加**：
- 规则11：如果输入标注了实体类型，`optimized_prompt` 必须尊重该实体的表面材质逻辑（如灵体不生成皮肤质感，机甲不生成有机纹理）
- 规则12：如果实体类型是非人，`negative_prompt` 必须包含该实体类型的"禁止人类化"关键词（如灵体加 `solid body, human skin, flesh`；机甲加 `organic texture, skin, flesh`）
- 规则13：`acceptance_criteria` 增加一条：主体保持实体类型的表面/材质/能量逻辑一致性，无物种/材质漂移

**6.2 `ENHANCE_VIDEO_PROMPT` 增加**：
- 规则8：非人实体的运动必须符合其类型逻辑（灵体漂浮不落地、机甲伺服驱动不软体、能量体脉动不碰撞）
- 规则9：非人实体的 `continuity_locks` 必须包含实体类型特有的连续性约束（如灵体的透明度/发光强度、机甲的板件/关节、拟人化的皮毛/爪指）
- 规则10：非人实体的 `risk_controls` 必须包含该实体类型的专属风险（如灵体的固化风险、拟人化的物种漂移、机甲的有机化风险）

---

### 第7步：新增 `entity_graft()` 实体嫁接方法

**文件**：`core/brain.py`

**方法签名**：`entity_graft(self, user_prompt: str, target_entity: str = "auto") -> dict`

**功能**：将人类角色描述嫁接为非人实体（来自V2 `creative-leap.md` 的 Entity Grafting 机制）

**8种嫁接目标**（来自V2 `thinking-engine.js`）：
1. `mechanical_body` — 机械体
2. `energy_form` — 能量形态
3. `digital_avatar` — 数字分身
4. `mythical_beast` — 神话异兽
5. `symbiotic_organism` — 共生有机体
6. `shadow_entity` — 暗影实体
7. `liquid_metal` — 液态金属
8. `crystalline_being` — 晶体生命

**护栏**（来自V2 `creative-leap.md`）：
- 嫁接不能是装饰性的——新形态必须改善钩子、主题、动作可读性或视觉回报
- 必须保持故事功能可读性
- 输出必须声明：故事功能、视觉回报、连续性风险、provider风险、fallback

**调用链**：
- `crux_studio.py` 新增 `--graft` CLI参数，指定嫁接目标类型
- `workflows.py` 在图片生成前可选择性调用 `entity_graft()` 预处理

---

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `core/brain.py` | +`ENTITY_TYPE_MAP`, +`ENTITY_SWEET_SPOT_TEMPLATES`, +`ENTITY_NEGATIVE_REPAIR_MAP`, +`GRAFT_TARGETS`, +`_infer_entity_type()`, 重写`_match_sweet_spot()`, 修改`_predict_risks()`, 修改`enhance_image_prompt()`, 修改`enhance_video_prompt()`, +`entity_graft()`, 更新`ENHANCE_IMAGE_PROMPT`, 更新`ENHANCE_VIDEO_PROMPT` |
| `pipeline/workflows.py` | 可选：嫁接工作流集成 |
| `crux_studio.py` | 可选：`--graft` CLI参数 |

> **核心变更集中在 `brain.py`，其他文件可选扩展**

---

## 不修改的文件

- V2知识源所有文件（只读取，不修改）
- `core/client.py`（API层不变）
- `engines/video.py`（引擎层不变）
