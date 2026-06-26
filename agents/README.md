# CRUX Agent 仓

应龙号令 — 多智能体协同体系。每个 Agent 有独立定义、权限范围、交接目标。

## Agent 定义标准

```yaml
name: Agent名
description: 单句描述
target: crux
model: ['model-name']           # 或 disable-model-invocation: true
tools: ['tool1', 'tool2']        # 独立 allowlist
permission: read-only|write|elevated
agents: ['sub-agent']            # 可派生子Agent
handoffs:                        # 可交接目标
  - label: 标签
    agent: 目标agent
    prompt: 交接提示
```

## 权限分级
- **read-only**: search/read/web，禁止任何写操作
- **write**: read + 文件编辑，受限写
- **elevated**: 全权限，含 execute/bash

## 现有 Agent
| Agent | 权限 | 模型 | 职责 |
|---|---|---|---|
| Ask | read-only | 路由(不调模型) | 只读问答 |
| Explore | read-only | deepseek-v4-pro | 快速探索 |
| Plan | read-only | 路由(不调模型) | 结构化规划 |
