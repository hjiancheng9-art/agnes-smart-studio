# ComfyFlow Compiler v6.5

零门槛 ComfyUI 高级工作流编译器 — 自然语言 → 生产级 Workflow JSON → 真实 ComfyUI 执行。

```bash
pip install -e .
comfyflow probe              # 探测 ComfyUI 环境
comfyflow compile "a cat"    # 编译为 workflow
comfyflow run "a cat"        # 编译 + 执行
```

---

## 10 分钟上手

### 1. 安装

```bash
git clone <repo>
cd comfyflow-compiler
pip install -e .
```

### 2. 探测环境

```bash
comfyflow probe
# 🔍 探测 ComfyUI: http://127.0.0.1:8188
#   在线:     ✅
#   版本:     v1.0.0
#   节点:     342 total (56 custom)
#   模型:     28 across 5 categories
```

### 3. 编译一条指令

```bash
comfyflow compile "a cat astronaut in space, cinematic"
# ✅ 编译成功
#   蓝图: SDXL 高清生成
#   节点: 8 (CLIPTextEncode, KSampler, VAEDecode, SaveImage, ...)
```

### 4. 一键执行

```bash
comfyflow run "a cat astronaut in space"
# ✅ 编译成功: SDXL 高清生成
# 🚀 提交到 ComfyUI...
# ✅ trace=a1b2c3 | task=txt2img | blueprint=flux_basic | elapsed=8.2s | Output: 1 images
#   📁 C:/ComfyUI/output/ComfyUI_00001.png (image)
```

### 5. 匹配兼容性

```bash
comfyflow match "a dog running, video"
# 🎯 匹配: a dog running, video
#   意图: task_type=t2v, style=['realistic']
#   配方: video_t2v_ltx → ['ltx_t2v_basic']
#   最佳兼容: ltx_t2v_basic (score=0.85)
```

### 6. 查看蓝图

```bash
comfyflow list-blueprints
# 📋 共 24 个蓝图:
#   ✅ flux_txt2img_basic                     txt2img   9 nodes  [stable]
#   ✅ sdxl_img2img_basic                     img2img   8 nodes  [stable]
#   🔶 ltx_t2v_basic                          t2v       5 nodes  [beta]
#   ...
```

---

## CLI 命令

| 命令 | 用途 |
|------|------|
| `comfyflow probe [url]` | 探测 ComfyUI 环境 |
| `comfyflow list-blueprints` | 列出所有蓝图 |
| `comfyflow match <prompt>` | 匹配最佳蓝图 |
| `comfyflow compile <prompt>` | 编译为 workflow JSON |
| `comfyflow run <prompt>` | 编译 + 执行 |
| `comfyflow pack <workflow.json> [id]` | 打包 workflow 为蓝图 |
| `comfyflow report [--json]` | 蓝图覆盖报告 |
| `comfyflow version` | 版本信息 |

---

## 架构概览

```
用户输入 (NL)
    ↓
[intent_parser] → task_type, style, subject
    ↓
[blueprint_registry] → 匹配场景配方 + 选择最佳蓝图
    ↓
[graph_composer] → 组装 workflow JSON
    ↓
[quality_gate] → 质量门 (结构/模型/参数/环境)
    ↓
[capability/snapshot] → 运行时能力探测
    ↓
[capability/compatibility] → 蓝图兼容性匹配
    ↓
[orchestrator/mcp_first] → MCP / 本地降级
    ↓
[execution] → 提交 → 轮询 → 收集产物
    ↓
输出 (图片/视频/音频)
```

## 蓝图资产

| 类型 | 数量 | 覆盖 |
|---|---|---|
| txt2img | 14 | ✅ |
| img2img | 4 | ✅ |
| i2v | 2 | ✅ |
| t2v | 2 | ✅ |
| general | 2 | ✅ |
| **合计** | **24** | **全达标** |

```bash
comfyflow report
```

---

## 开发

```bash
# 运行全部测试
pytest tests/golden/

# 批量打包 workflow
python scripts/batch_pack.py --input ./output/workflows --output ./blueprints

# 覆盖报告 (JSON)
python -m comfyflow_compiler.blueprint.report --json
```

## 依赖

- Python ≥ 3.11
- httpx (MCP 客户端)
- ComfyUI (运行时，可选)

## 版本历史

| 版本 | 代号 | 核心 |
|---|---|---|
| v6.1 | Reality Closure | 蓝图资产 + MCP fallback |
| v6.2 | Video-MCP Closure | t2v 链路 + MCP 真实端点 |
| v6.3 | Capability Closure | 运行时探测 + 兼容性匹配 |
| v6.4 | Execution Closure | 提交/轮询/输出契约 |
| **v6.5** | **Polish Closure** | **CLI + 文档 + examples** |
