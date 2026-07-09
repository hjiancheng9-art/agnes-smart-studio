# ComfyFlow Compiler — 架构文档

## 一句话

把「用户自然语言」编译成「ComfyUI 可执行的 Workflow JSON」。

## 14 模块依赖图

```
用户输入
   │
   ▼
┌──────────────────────────────────────────────────────────────┐
│ intent_parser.py          自然语言 → TaskSpec + 生产意图     │
│   └── models.py           所有数据模型                        │
└──────────────────────┬───────────────────────────────────────┘
                       │ TaskSpec
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ hardware_profiler.py   GPU检测 → 显存 → RuntimeBudget         │
│ environment_scanner.py ComfyUI路径 → 模型/节点列表            │
└──────────────────────┬───────────────────────────────────────┘
                       │ HardwareProfile + EnvironmentProfile + Budget
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ blueprint_registry.py  场景配方匹配 + 硬件约束选蓝图          │
│   └── node_catalog.py  节点能力图谱                          │
└──────────────────────┬───────────────────────────────────────┘
                       │ Blueprint
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ graph_composer.py     TaskSpec + Blueprint → Workflow JSON   │
│   └── parameter_table.py  参数集中管理                       │
└──────────────────────┬───────────────────────────────────────┘
                       │ Workflow JSON
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ quality_gate.py      7维度评分                                │
│ workflow_validator.py 拓扑/连接/循环校验                     │
│ workflow_parser.py    3种Workflow格式互转                    │
└──────────────────────┬───────────────────────────────────────┘
                       │ 校验通过
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ user_facing.py       UserFacingResult → 小白友好的输出        │
│ safety_gate.py       提交 /prompt 前安全检查                  │
│   └── launcher.py    ComfyUI 进程管理                        │
│   └── api_client.py  HTTP + WebSocket 双通道                 │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
                  compiler.py  ← 总入口（编排上述所有模块）
```

## 数据流向

```
用户输入 (str)
  → TaskSpec (结构化需求)
    → HardwareProfile + RuntimeBudget + EnvironmentProfile
      → Blueprint (最佳方案)
        → Workflow JSON (API Prompt Format)
          → UserFacingResult (小白输出)
```

## 关键设计决策

1. **编译器不是聊天机器人** — LLM 负责语义理解，拓扑由蓝图保证
2. **硬件前置** — 先检测硬件再选方案，不是跑崩了再降级
3. **集中参数** — 所有 steps/cfg/sampler 在 parameter_table.py 管理
4. **三格式支持** — API Prompt / Save V1 / Legacy，互转在 workflow_parser.py
