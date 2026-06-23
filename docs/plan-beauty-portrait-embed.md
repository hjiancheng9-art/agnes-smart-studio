# 帅哥美女描写设定嵌入 CRUX 方案

> 来源：新烬龙V2 `character-clothing.md` + `AI视频生成提示词知识库.md` + `LTX2.3生产甜点区规格.md` + `LTX2.3首帧驱动I2V规格.md` + `提示词与知识库编排中枢.md` + `video-generation.md`
> 目标文件：`crux-smart-studio/core/brain.py`

---

## 背景问题

当前 CRUX 的 `_infer_entity_type()` 只识别**非人实体**（灵体、能量体、机器人等），对人类高颜值角色无感知。用户输入"画一个帅哥""生成一个冷感美女"时：

1. 不会走帅哥美女独立通道
2. 不会注入多角度气质规则
3. 不会应用帅哥/美女子模板
4. 不会禁止混入非人战斗/怪诞逻辑
5. 视频生成不知道该用逐镜 compact + I2V 0.72

---

## Step 1：新增 `BEAUTY_PORTRAIT_MAP` — 帅哥美女检测与气质图谱

**位置**：`ENTITY_TYPE_MAP` 之后、`ENTITY_SWEET_SPOT_TEMPLATES` 之前

```python
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
```

**设计要点**：
- `keywords` 包含中英文触发词
- `aura_options` 是气质选项列表，LLM 从中选取最匹配的
- `angle_rules` 是6角度规则，注入 LLM 指令
- `template_suffix` / `template_negative` 是可直接复用的子模板，`{aura}` 占位符由代码替换

---

## Step 2：新增 `BEAUTY_SWEET_SPOT_TEMPLATES` — 帅哥美女专属甜点区

**位置**：`ENTITY_SWEET_SPOT_TEMPLATES` 之后、`ENTITY_NEGATIVE_REPAIR_MAP` 之前

```python
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
```

---

## Step 3：新增 `BEAUTY_NEGATIVE_REPAIR_MAP` — 帅哥美女专属失败修复

**位置**：`ENTITY_NEGATIVE_REPAIR_MAP` 之后、`GRAFT_TARGETS` 之前

```python
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
```

---

## Step 4：新增 `BEAUTY_PRODUCTION_RULES` — 生产路由规则

**位置**：`BEAUTY_NEGATIVE_REPAIR_MAP` 之后、`GRAFT_TARGETS` 之前

```python
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
```

---

## Step 5：新增 `_infer_beauty_type()` 方法

**位置**：`_infer_entity_type()` 方法之后

```python
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
            # "帅哥美女" / "高颜值" 是中性触发，不单独加分
            if kw in ("帅哥美女", "高颜值"):
                handsome_score += 1
                beauty_score += 1
            else:
                handsome_score += 2

    for kw in BEAUTY_PORTRAIT_MAP["beauty"]["keywords"]:
        if kw in p:
            if kw in ("帅哥美女", "高颜值"):
                continue  # 已在 handsome 循环中加分
            beauty_score += 2

    # 需要至少1个专属关键词（分数≥2）才触发
    if handsome_score >= 2 and handsome_score > beauty_score:
        return "handsome"
    if beauty_score >= 2 and beauty_score > handsome_score:
        return "beauty"
    # 分数相等时，检查是否有中性触发词 + 性别线索
    if handsome_score >= 2 and beauty_score >= 2:
        gender_hints_male = ["男", "他", "boy", "man", "male", "guy", "先生", "少年"]
        gender_hints_female = ["女", "她", "girl", "woman", "female", "lady", "小姐", "少女"]
        if any(h in p for h in gender_hints_male) and not any(h in p for h in gender_hints_female):
            return "handsome"
        if any(h in p for h in gender_hints_female) and not any(h in p for h in gender_hints_male):
            return "beauty"
    return None
```

---

## Step 6：增强 `enhance_image_prompt()` — 注入帅哥美女通道

**改动**：在 `enhance_image_prompt()` 中，在实体推断之后、LLM调用之前，增加帅哥美女推断和通道注入

**伪代码**：
```python
def enhance_image_prompt(self, user_prompt, style=None):
    # 已有：实体类型推断
    entity_type, surface_policy = self._infer_entity_type(user_prompt)

    # 新增：帅哥美女推断
    beauty_type = self._infer_beauty_type(user_prompt)

    # 构建LLM输入
    input_text = user_prompt
    if entity_type:
        # 已有逻辑...
        pass
    elif beauty_type:
        # 新增：帅哥美女通道注入
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
    if style:
        input_text = f"风格要求：{style}\n{input_text}"

    # LLM调用 + 解析（已有逻辑）
    text = self._ask_brain(ENHANCE_IMAGE_PROMPT, input_text)
    result = self._parse_json(text)
    # ...

    # 新增：帅哥美女甜点区叠加（优先级：实体专属 > 帅哥美女 > 场景模板）
    if beauty_type and not entity_type:
        template = self._match_beauty_sweet_spot(beauty_type, "image")
        if template:
            # 叠加负面提示词 + 补充 suffix 缺失词
            base_neg = result.get("negative_prompt", "")
            result["negative_prompt"] = self._merge_negative(base_neg, template["negative"])
            existing = result["optimized_prompt"].lower()
            suffix_terms = template["suffix"].split(", ")
            missing = [t for t in suffix_terms if t.lower() not in existing]
            if missing:
                result["optimized_prompt"] += ", " + ", ".join(missing[:5])
            result["sweet_spot"] = template["name"]

    # 新增：帅哥美女信息注入
    if beauty_type and not entity_type:
        result["beauty_type"] = beauty_type
        result["beauty_name_cn"] = BEAUTY_PORTRAIT_MAP[beauty_type]["name_cn"]
        result["beauty_aura_options"] = BEAUTY_PORTRAIT_MAP[beauty_type]["aura_options"]

    # 已有的风险预判
    risk_warnings = self._predict_risks(user_prompt, entity_type)
    # 新增：帅哥美女专属风险
    if beauty_type:
        beauty_risks = self._predict_beauty_risks(beauty_type)
        risk_warnings.extend(beauty_risks)
    # ... 后续逻辑不变
```

---

## Step 7：增强 `enhance_video_prompt()` — 注入帅哥美女视频规则

**改动**：与 Step 6 对称，但视频通道额外注入生产路由规则

**伪代码**：
```python
def enhance_video_prompt(self, user_prompt):
    entity_type, surface_policy = self._infer_entity_type(user_prompt)
    beauty_type = self._infer_beauty_type(user_prompt)

    input_text = user_prompt
    if entity_type:
        # 已有逻辑
        pass
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

    # ... LLM调用 + 解析

    # 新增：帅哥美女视频甜点区
    if beauty_type and not entity_type:
        template = self._match_beauty_sweet_spot(beauty_type, "video")
        if template:
            # 叠加逻辑同image
            pass
        # 注入生产路由信息
        result["production_route"] = "traditional compact + I2V"
        result["i2v_strength_recommendation"] = "0.72"
        result["beauty_type"] = beauty_type
        result["beauty_name_cn"] = BEAUTY_PORTRAIT_MAP[beauty_type]["name_cn"]

    # 风险预判 + 帅哥美女专属风险
    # ...
```

---

## Step 8：新增辅助方法 `_match_beauty_sweet_spot()` + `_predict_beauty_risks()`

**位置**：`_match_sweet_spot()` 和 `_predict_risks()` 之后

```python
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
```

---

## Step 9：增强 `_match_sweet_spot()` — 帅哥美女甜点区优先级

**改动**：在 `_match_sweet_spot()` 方法中，增加帅哥美女甜点区的匹配优先级

**优先级链**：实体专属 > 帅哥美女 > 场景模板

在方法开头（实体专属匹配之后、场景模板回退之前）插入：

```python
# 2.5 帅哥美女甜点区（实体未匹配时）
if not entity_type:
    beauty_type = self._infer_beauty_type(prompt)
    if beauty_type:
        beauty_tpl = self._match_beauty_sweet_spot(beauty_type, mode)
        if beauty_tpl:
            return beauty_tpl
```

---

## Step 10：增强 LLM 指令 — `ENHANCE_IMAGE_PROMPT` 和 `ENHANCE_VIDEO_PROMPT`

### ENHANCE_IMAGE_PROMPT 新增规则 14-16：

```
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
```

### ENHANCE_VIDEO_PROMPT 新增规则 11-13：

```
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
```

---

## 改动总览

| Step | 改动类型 | 位置 | 说明 |
|------|----------|------|------|
| 1 | 新增常量 | `ENTITY_TYPE_MAP` 后 | `BEAUTY_PORTRAIT_MAP`：检测+气质+角度+模板 |
| 2 | 新增常量 | `ENTITY_SWEET_SPOT_TEMPLATES` 后 | `BEAUTY_SWEET_SPOT_TEMPLATES`：专属甜点区 |
| 3 | 新增常量 | `ENTITY_NEGATIVE_REPAIR_MAP` 后 | `BEAUTY_NEGATIVE_REPAIR_MAP`：专属失败修复 |
| 4 | 新增常量 | Step 3 后 | `BEAUTY_PRODUCTION_RULES`：生产路由+隔离规则 |
| 5 | 新增方法 | `_infer_entity_type()` 后 | `_infer_beauty_type()`：帅哥美女推断 |
| 6 | 增强方法 | `enhance_image_prompt()` | 注入人像通道 + 甜点区 + 风险 |
| 7 | 增强方法 | `enhance_video_prompt()` | 注入人像通道 + 视频路由 + I2V规则 |
| 8 | 新增方法 | `_predict_risks()` 后 | `_match_beauty_sweet_spot()` + `_predict_beauty_risks()` |
| 9 | 增强方法 | `_match_sweet_spot()` | 帅哥美女甜点区优先级插入 |
| 10 | 增强常量 | `ENHANCE_IMAGE_PROMPT` / `ENHANCE_VIDEO_PROMPT` | 新增规则 14-16 / 11-13 |

---

## 优先级链（完整）

```
实体专属甜点区（灵体/机器人等9种）
  ↓ 未匹配
帅哥美女甜点区（handsome/beauty 2种）
  ↓ 未匹配
场景甜点区（portrait/full_body/action等7种）
  ↓ 未匹配
无甜点区
```

---

## 验证计划

```python
# 1. 帅哥美女推断
assert brain._infer_beauty_type("画一个清冷帅哥") == "handsome"
assert brain._infer_beauty_type("生成一个明艳美女") == "beauty"
assert brain._infer_beauty_type("画一只猫") is None
assert brain._infer_beauty_type("帅哥美女一起") is None  # 中性，无性别线索时返回None

# 2. 甜点区匹配
tpl = brain._match_beauty_sweet_spot("handsome", "image")
assert tpl is not None and "sharp bone structure" in tpl["suffix"]

# 3. 甜点区优先级
tpl = brain._match_sweet_spot("一个帅气的机器人", "image")
assert tpl["entity_type"] == "robot"  # 实体优先于帅哥

# 4. 风险预判
risks = brain._predict_beauty_risks("handsome")
assert any("template_face" in r["risk"] for r in risks)

# 5. enhance_image_prompt 集成
result = brain.enhance_image_prompt("画一个英气帅哥站在城墙上")
assert result.get("beauty_type") == "handsome"
assert "template face" in result.get("negative_prompt", "")
```
