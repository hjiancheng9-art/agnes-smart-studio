# Agnes Smart Studio — Claude Code 配置

## 模型路由策略

settings.json 已把模型别名重定向到 DeepSeek：
- `haiku` → `deepseek-v4-flash`（轻量，便宜）
- `sonnet` → `deepseek-v4-pro[1m]`（强推理）
- `opus` → `deepseek-v4-pro[1m]`

### 子 Agent 类型 + 模型 联合路由（硬约束）

| 任务 | Agent 类型 | model | 实际模型 | 说明 |
|------|-----------|-------|---------|------|
| grep / glob / 读文件 / 搜代码 | **Explore** | `haiku` | deepseek-v4-flash | 只读，不能改文件，最安全 |
| 广泛代码调研（多目录扫） | **Explore** | `haiku` | deepseek-v4-flash | medium / very thorough |
| 单文件修改、简单重构 | **general-purpose** | `haiku` | deepseek-v4-flash | 需要写入权限 |
| 写测试 | **general-purpose** | `haiku` | deepseek-v4-flash | test-automator 太重，日常够用 |
| 调试错误/测试失败 | **debugger** | `haiku` | deepseek-v4-flash | 先排查，搞不定再升级 |
| 实现方案设计 | **Plan** | `haiku` | deepseek-v4-flash | 出计划，不出代码 |
| 架构设计、多文件重构 | 主对话 | — | deepseek-v4-pro | 需要全局视野 |
| 复杂调试根因分析 | 主对话 | — | deepseek-v4-pro | 需要深度推理 |

### 规则

1. **读文件 / 搜索 → Explore agent + haiku**，不要派 general-purpose（Explore 更快更省）
2. **写代码 → general-purpose agent + haiku**，简单修改不派 Pro
3. **审查 / 安全 → code_review / security_review**，规则引擎本地执行
4. **出方案 → Plan agent + haiku**，把方案拿回来看再决定要不要自己动手
5. 独立子任务**一次并行发出**（1-3 个），不要串行等
6. 子 Agent 失败不重试同一类型，换通路（haiku 挂了换 flash）
7. 禁止：派 haiku 做架构决策 / 派 Pro 做 grep / 串行等独立任务
8. Explore agent 的描述里写清搜索广度（medium / very thorough）

### 降级链路（settings.json fallbackModel）

```
deepseek-v4-pro[1m]  ← 主模型
  └─ 挂了 → glm-4-flash-250414（智谱，免费额度）
       └─ 挂了 → kimi-k2.6（Moonshot）
```

智谱通过 settings.json `fallbackModel` 参与自动降级，不用于主动路由。
项目内部可通过 `core/provider.py` + Bash 主动调智谱：
```bash
python -c "from core.provider import ProviderManager; ..."
```

## 项目环境

- Python: `C:\Users\huangjiancheng\AppData\Local\Programs\Python\Python311\python.exe`
- 测试: `python crux_studio.py --check`
- 冒烟: `python tests/test_smoke.py --quick`
- 启动: 双击 `launch.bat` 或 `python launcher.py`
