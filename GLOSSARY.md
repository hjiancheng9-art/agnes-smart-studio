# ComfyFlow Compiler — 术语表

## 核心概念

| 缩写 | 全称 | 中文 | 解释 |
|------|------|------|------|
| **wf** | workflow | 工作流 | ComfyUI 可执行的节点图 JSON |
| **bp** | blueprint | 蓝图 | 预审的工作流模板（含节点拓扑和默认参数） |
| **recipe** | recipe | 配方 | 面向用户的场景方案（如"电影感写实"） |
| **task** | TaskSpec | 任务规格 | 自然语言解析后的结构化需求 |
| **intent** | production_intent | 生产意图 | 用户到底想做什么（Flux/视频/换装/...） |
| **ct** | class_type | 节点类型 | ComfyUI 节点的类名（如 KSampler） |
| **hw** | HardwareProfile | 硬件配置 | GPU/显存/算力 |
| **env** | EnvironmentProfile | 环境配置 | ComfyUI 安装/模型/插件 |
| **budget** | RuntimeBudget | 运行预算 | 硬件能承受的最大生成复杂度 |
| **gate** | quality_gate | 质量门 | 多维度质量评分 |
| **report** | QualityReport | 质量报告 | 评分+警告+错误 |
| **manifest** | manifest | 清单 | 工作流生成记录（可复现用） |

## 文件说明

| 文件 | 做的事 |
|------|--------|
| compiler.py | 总入口，编排所有模块 |
| models.py | 所有数据模型定义 |
| intent_parser.py | 自然语言 → TaskSpec |
| hardware_profiler.py | GPU检测 + 预算计算 |
| environment_scanner.py | ComfyUI 目录扫描 |
| blueprint_registry.py | 蓝图/配方/选择/降级 |
| node_catalog.py | 节点能力图谱 |
| graph_composer.py | 组装 Workflow JSON |
| parameter_table.py | 参数集中管理 |
| quality_gate.py | 质量评分 |
| workflow_validator.py | Workflow 校验 |
| workflow_parser.py | 三格式互转 |
| user_facing.py | 小白友好输出 |
| safety_gate.py | 安全检查 |
| api_client.py | ComfyUI API 客户端 |
| launcher.py | ComfyUI 进程管理 |

## Workflow 格式

| 格式 | 用途 | 结构 |
|------|------|------|
| API Prompt | POST /prompt 执行 | `{node_id: {class_type, inputs}}` |
| Save V1 | 前端保存/拖入 | `{version:1, state, nodes, links}` |
| Legacy | 老 LiteGraph 兼容 | `{nodes:[], links:[]}` |
