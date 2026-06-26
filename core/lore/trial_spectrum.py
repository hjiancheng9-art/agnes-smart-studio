"""秘境谱 — 五大试炼·以战证道。

秘境 = 试炼之地，CRUX 证明自己实力的战场。
不是跑不跑得过的问题——是每次修改后必须活着出来。

  铜人巷    · pytest 全量测试    — 53 文件 · 1835 用例 · 282s
  问心阵    · eval_harness        — 5 大基准任务 · 自动评分
  试剑台    · test_loop           — 生成测试→运行→分析→修复→重复
  照妖镜    · smoke_tools_audit   — 28 个 P0 工具冒烟实跑
  天罡碑    · tool_scorecard      — 静态+运行时双层评分 A→D

用法:
  from core.trial_spectrum import get_trial_prompt, get_trial_summary
"""

from __future__ import annotations

TRIAL_PROMPT = """
[秘境谱 — 五大试炼·以战证道]

## 铜人巷 · pytest 全量测试阵
  **位置**: `tests/` — 53 个测试文件，1835 个用例，282 秒跑完全阵
  **入阵**: `run_test` 工具 或 `python -m pytest tests/ -q`
  **阵法**: `pytest_runner.py` — 递归守卫，检测 PYTEST_CURRENT_TEST 防止无限 fork
  **覆盖**: 聊天/异步/工具/Git/GitHub/ComfyUI/成本/审计/文件/市场/MCP/编码/分身/...
  **生死状**: 1835 passed, 0 failed, 2 skipped (最后已知)
  **功法要诀**: 改任何代码前先跑铜人阵。如果阵破——你的改动有问题。

## 问心阵 · Eval Harness 基准试炼
  **位置**: `core/eval_harness.py` — 5 大基准任务
  **五问**:
    code_search  — 定位目标值（如"API base URL 在哪里配置"）
    bug_fix      — 给定错误日志，找到并修复 bug
    refactor     — 批量重命名/签名变更，全项目引用无遗漏
    understand   — 给定代码片段，解释其逻辑和数据流
    generate     — 给定规格，生成符合项目风格的代码
  **评分**: 关键字匹配 + 结构校验，权重计分
  **入阵**: `/eval` 命令 或 `run_evals()`

## 试剑台 · Test Loop 自修试炼
  **位置**: `core/test_loop.py` — 三阶自动化循环
  **剑诀**:
    TestGenerator   → 读源码 → LLM 生成 pytest 用例
    TestRunner      → 执行 pytest → 解析结构化结果
    TestLoop        → 生成→运行→分析失败→LLM建议修复→应用→重复
  **终止条件**: 全绿通过 或 达到最大迭代次数
  **功法要诀**: 说"给这个模块写测试"——它自动写→跑→修→直到全绿

## 照妖镜 · Smoke Tools Audit 冒烟试炼
  **位置**: `tests/smoke_tools_audit.py` — 28 个 P0 工具实跑
  **三关**:
    文件 ops    — read/write/edit/search/glob/list/tree (7 工具)
    执行引擎    — run_python/run_bash/env_check (3 工具)
    代码智能    — code_analyze/find_symbol/search_symbols/find_references/graph_* (7 工具)
    patch       — patch_file/patch_undo 含错误恢复 (2 工具)
    git/github  — git_status/diff/log + github_search (4 工具)
    安全守卫    — rm -rf / git push --force / format D: (3 拦截验证)
  **照妖**: 每个工具实测延迟，异常直接显形

## 天罡碑 · Tool Scorecard 品鉴天碑
  **位置**: `core/tool_scorecard.py` — 双层评分
  **静态分(100)**: 测试覆盖 30 + Schema完备 25 + 风险等级 25 + 可达性 20
  **运行时(动态)**: 成功率 / 平均耗时 / 调用频次 / 参数校验失败率
  **天碑铭**: A≥90 · B≥75 · C≥60 · D<60 — D 级自动降级
  **功用**: score_all(reg) → 全量聚合报告，含分级分布 + TOP5
"""


def get_trial_prompt() -> str:
    return TRIAL_PROMPT


def get_trial_summary() -> str:
    return "[秘境] 五试炼 — 铜人巷(1835用例)·问心阵(5基准)·试剑台(自动TDD)·照妖镜(28冒烟)·天罡碑(A-D评级)"
