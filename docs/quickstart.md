# 快速开始

## 前提

- Python 3.11+
- （可选）运行中的 ComfyUI，默认 `http://127.0.0.1:8188`

## 1. 安装

```bash
pip install -e .
```

验证安装：
```bash
comfyflow version
# ComfyFlow Compiler v6.5.0
```

## 2. 查看能力

```bash
# 列出所有蓝图
comfyflow list-blueprints

# 覆盖报告
comfyflow report
```

## 3. 编译工作流

```bash
# 文生图
comfyflow compile "a cat astronaut in space, cinematic"

# 图生图
comfyflow compile "turn this photo into anime style"

# 文生视频
comfyflow compile "a dog running on the beach, video"
```

## 4. 编译 + 执行

```bash
comfyflow run "a cat astronaut in space"
```

要求 ComfyUI 在线且已加载对应模型。

## 5. Python API

```python
from comfyflow_compiler.compiler import ComfyFlowCompiler
from comfyflow_compiler.capability.snapshot import probe_comfyui
from comfyflow_compiler.execution import ExecutionOrchestrator

# 编译
compiler = ComfyFlowCompiler()
result = compiler.compile("a cat astronaut")
print(result.blueprint_used)  # "SDXL 高清生成"
print(result.workflow_json)   # workflow dict

# 执行
orch = ExecutionOrchestrator()
exec_result = orch.execute(result.workflow_json)
print(exec_result.summary)    # "✅ trace=... | Output: 1 images"
```

## 6. 常见问题

**ComfyUI 不在线？**
→ `comfyflow probe` 会显示离线，编译照常进行，执行会报 submission offline

**没有模型？**
→ `comfyflow match "prompt"` 会显示兼容性评分，缺模型会标红

**想加新蓝图？**
→ 手写 JSON 放 `comfyflow_compiler/blueprints/`，或 `comfyflow pack` 从 workflow 打包
