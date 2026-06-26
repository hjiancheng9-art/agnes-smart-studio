# core/showrunner.py — 创意流水线导演

> Goal → Plan → Skill Steps → Generation → Delivery — 全自动创意制片。

## 流水线模板

```python
class StepKind(Enum):
    THINK = "think"           # 推理/决策
    PROMPT = "prompt"         # 提示词生成
    TEXT = "text"             # 文本创作
    IMAGE = "image"           # 图像生成
    VIDEO = "video"           # 视频生成
    AUDIO = "audio"           # 音频生成
    REVIEW = "review"         # 质检审核
    DELIVER = "deliver"       # 成品交付
    CUSTOM = "custom"         # 自定义步骤
```

### 预置模板

| 模板 | 流程 |
|------|------|
| `short_video` | brainstorm → script → prompts → images → animate → review → deliver |
| `concept_art` | explore → prompts → generate → curate → deliver |
| `novel_chapter` | expand → write → illustrate → polish → export |

## 渲染源

```python
class SourceKind(Enum):
    AGNES = "crux"       # CRUX API（主源）
    COMFYUI = "comfyui"  # ComfyUI 本地渲染
    EXTERNAL = "external" # 外部 Web API
    API = "api"          # 通用 API
    CLI = "cli"          # CLI 工具
```

每个源可配置 fallback — 主源失败自动切换备用。

## 数据模型

| 类 | 职责 |
|----|------|
| `StepResult` | 步骤执行结果：step_name、kind、source、status、output |
| `PipelinePlan` | 流水线计划：goal、template、steps、source_config |

## 公共 API

```python
from core.showrunner import (
    StepResult,          # 步骤结果
    PipelinePlan,        # 流水线计划
    run_pipeline,        # 执行流水线
)
```

## 集成

- `ui/mixins/creative.py` — `/showrun <goal>` 命令入口
- `core/skills.py` — Showrunner 作为技能加载（`showrunner.skill.json`）
- `engines/text_to_image.py` / `engines/video.py` — 图像/视频生成引擎
- `core/comfyui_tools.py` — ComfyUI 桥接

## 用法

```
/showrun 制作一支赛博朋克风格的30秒短片
```
→ 自动选择 `short_video` 模板，逐步执行 brainstorm→script→prompts→images→animate→review→deliver。
