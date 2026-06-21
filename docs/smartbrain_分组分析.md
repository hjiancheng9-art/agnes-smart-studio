# SmartBrain 三组功能分组分析

> 源码: `core/brain.py` | 1457行 | 1类 | 22方法

---

## ▎ PROMPTS 组 (16 方法) — 意图识别 + Prompt增强 + 风险预判

| # | 方法 | 行号 | 功能 |
|---|------|------|------|
| 1 | `__init__` | 12 | 注入 AgnesClient，无状态 |
| 2 | `_ask_brain` | 15 | 调 2.0-flash Thinking，自动剥离 markdown 代码块 |
| 3 | `_parse_json` | 42 | 安全 JSON 解析，容错截取 `{...}` |
| 4 | `recognize_intent` | 57 | 意图识别（t2i/i2i/edit/video），返回 intent+confidence+plan |
| 5 | `enhance_image_prompt` | 70 | **图片增强核心链路**：实体感知→美女通道→战斗注入→创意知识→甜点区→风险预判→进化记忆 |
| 6 | `enhance_video_prompt` | 221 | **视频增强核心链路**：同图片链路 + 非人视频规则 + 动态节奏模板 |
| 7 | `generate_storyboard` | 375 | 输入 creative_brief 生成多帧分镜脚本 |
| 8 | `generate_edit_prompt` | 382 | 图片编辑指令生成（基于当前图描述+编辑需求） |
| 9 | `_infer_entity_type` | 708 | 从 prompt 推断非人实体类型（mecha/dragon/elemental 等） |
| 10 | `_infer_beauty_type` | 726 | 推断帅哥/美女类型，触发独立人像通道 |
| 11 | `_match_sweet_spot` | 767 | 甜点区匹配引擎：实体专属 > 场景模板 > 通用 |
| 12 | `_match_beauty_sweet_spot` | 937 | 帅哥/美女专属甜点区匹配 |
| 13 | `_predict_risks` | 877 | 通用风险预判：实体风险 + 美女风险 + 光照溢出等通用负面 |
| 14 | `_predict_beauty_risks` | 975 | 帅哥美女专属风险（模板脸/硬摆拍/夸张体态） |
| 15 | `_merge_negative` | 992 | 多源 negative prompt 去重合并（静态方法） |
| 16 | `understand_image` | ~1001 | 调 1.5-flash 多模态理解图片内容 |

---

## ▎ COMBAT 组 (2 方法) — 战斗招式匹配 + 一站式战斗知识路由

| # | 方法 | 行号 | 功能 |
|---|------|------|------|
| 17 | `_match_combat_moves` | 393 | 从 COMBAT_MOVE_INDEX 关键词匹配最相关招式（top 5），多级评分 |
| 18 | `_detect_combat_scene` | 503 | **战斗知识路由器**：一次整合招式/VFX色系/模板公式/甜点区/专属风险/镜头建议 |

---

## ▎ CREATIVE 组 (4 方法) — 创意知识解析 + 实体嫁接 + 创意飞跃

| # | 方法 | 行号 | 功能 |
|---|------|------|------|
| 19 | `entity_graft` | ~1001 | 实体嫁接：人类角色→非人实体（7种目标），含护栏检查 |
| 20 | `_resolve_creative_knowledge` | ~1100+ | **创意知识路由器**：一次激活5个死常量（跨域/反模式/思维技法/非人战斗/视频规则） |
| 21 | `_select_creative_methods` | 1350 | 自动选择2-3种最匹配的创意方法（8种候选） |
| 22 | `creative_leap` | 1388 | **创意飞跃主入口**：实体+战斗+创意+多思维方法并行 → 多候选方案+护栏 |

---

## 调用关系图

```
recognize_intent ─────────────────────────────────────────────── INTENT_PROMPT
       │
       ▼
enhance_image_prompt ──┬── _infer_entity_type ── ENTITY_TYPE_MAP
                       ├── _infer_beauty_type ── BEAUTY_PORTRAIT_MAP
                       ├── _detect_combat_scene ──┬─ _match_combat_moves
                       │                          └─ COMBAT_* 常量全家桶
                       ├── _resolve_creative_knowledge ── CREATIVE_DOMAIN/ANTI_PATTERN/THINKING_METHOD
                       ├── _match_sweet_spot ──┬─ entity → ENTITY_SWEET_SPOT
                       │                       ├─ beauty → _match_beauty_sweet_spot
                       │                       └─ generic → SCENE_SWEET_SPOT
                       ├── _predict_risks ──┬─ entity risks
                       │                    ├─ _predict_beauty_risks
                       │                    └─ _predict_general_negative_risks
                       └── _merge_negative

creative_leap ──┬── _infer_entity_type
                ├── _detect_combat_scene
                ├── _resolve_creative_knowledge
                ├── _select_creative_methods
                └── _match_sweet_spot (per leap candidate)

entity_graft ──┬── GRAFT_TARGETS
               └── _match_sweet_spot
```

---

## 关键设计原则

1. **路由器模式**: `_detect_combat_scene` 和 `_resolve_creative_knowledge` 都是一次性解析所有相关常量，返回结构化上下文，供多个消费者（image/video/creative）复用
2. **分层注入优先级**: 实体 > 美女 > 战斗 > 创意 > 通用
3. **闭环自进化**: `enhance_image_prompt` / `enhance_video_prompt` 注入历史成功案例（build_evolution_context），失败案例在 `_predict_risks` 中作为预防性修复
4. **护栏无处不在**: 实体嫁接有 graft_safety 检查，创意飞跃有 guardrail_check，不是装饰性的而是硬阻断
