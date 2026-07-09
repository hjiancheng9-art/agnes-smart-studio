# Blueprint Schema

蓝图是 ComfyFlow Compiler 的核心资产，将真实 ComfyUI workflow 抽象为可复用的模板。

## 格式

每个蓝图为一个 JSON 文件，放在 `comfyflow_compiler/blueprints/` 目录下。

## 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema_version` | string | ✅ | 固定为 `"1.0.0"` |
| `id` | string | ✅ | 唯一标识，如 `"flux_txt2img_basic"` |
| `name` | string | ✅ | 可读名称 |
| `version` | string | ✅ | 语义版本 |
| `status` | string | ✅ | `stable` / `beta` / `deprecated` |
| `source` | object | ✅ | 来源信息 (origin/workflow_id/mined_at) |
| `capability` | object | ✅ | 能力描述 (task_type/tags/styles/models) |
| `requirements` | object | ✅ | 节点需求 (min_nodes/required_nodes) |
| `input_contract` | object | ✅ | 输入契约 (fields 定义) |
| `output_contract` | object | ✅ | 输出契约 |
| `graph_template` | object | ✅ | 图模板 (nodes/edges) |
| `slots` | object | ✅ | 可调参数槽位 |
| `quality_modes` | object | ✅ | draft/standard/quality 三档 |
| `validation` | object | ✅ | 验证信息 (vram/known_issues) |
| `metadata` | object | ✅ | 元信息 |

## 示例

```json
{
  "schema_version": "1.0.0",
  "id": "flux_txt2img_basic",
  "name": "Flux Text-to-Image",
  "status": "stable",
  "capability": {
    "task_type": "txt2img",
    "tags": ["flux", "realistic"],
    "models": [{"name": "flux1-schnell-fp8", "type": "unet", "required": true}]
  },
  "requirements": {
    "min_nodes": 7,
    "required_nodes": [
      {"class_type": "DualCLIPLoader", "reason": "Flux 需要双 CLIP 加载"}
    ]
  },
  "input_contract": {
    "fields": [
      {"name": "positive_prompt", "type": "text", "required": true}
    ]
  },
  "graph_template": {
    "nodes": [...],
    "edges": [...]
  }
}
```

## 覆盖矩阵

目标覆盖：

| 类型 | 最少 |
|------|------|
| txt2img | 5 |
| img2img | 4 |
| i2v | 2 |
| t2v | 1 |
| general | 2 |
| **总计** | **24** |

查看当前覆盖：`comfyflow report`
