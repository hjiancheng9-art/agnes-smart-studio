# GPT-First Advisor 层重构方案

## 核心原则
- 纯 CDP：只用 Edge CDP 连 ChatGPT 网页，不用 OpenAI API
- 同步架构：全部同步，无 async
- 向后兼容：保留 core/gpt_first.py 为薄兼容层，消费者无感知
- 文件附件：CDP Advisor 支持将文件传给 ChatGPT 网页

## 新建文件 (8个)

### 1. advisor/__init__.py — 包标记
### 2. advisor/base.py — AdvisorResult + AdvisorClient (Protocol, 同步)
### 3. advisor/circuit_breaker.py — 3次失败熔断120s
### 4. advisor/cache.py — SHA256 查询缓存, TTL 600s
### 5. advisor/prompt.py — build_advisor_prompt() 顾问提示词
### 6. advisor/cdp_advisor.py — CDP 实现，含 ask() + ask_with_files() 文件附件
### 7. core/fusion.py — build_fusion_prompt() 融合 DeepSeek
### 8. core/orchestrator.py — GPTFirstOrchestrator 主编排

## 修改文件 (1个)
### 9. core/gpt_first.py → 兼容层，委托到 orchestrator

## 不改文件
core/cdp_browser.py, crux_studio.py, ui/tui_app.py, core/cli_handlers.py