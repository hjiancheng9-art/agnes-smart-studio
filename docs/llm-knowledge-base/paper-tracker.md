# 📄 论文阅读追踪

> 每篇论文的阅读笔记和关键要点
> 格式: 标题 | 年份 | 阅读状态 | 评分 | 笔记

---

## 必读论文清单

### 🟢 已读完

_暂无_

### 🟡 阅读中

_暂无_

### ⬜ 待读 (按优先级排序)

#### P0 — 第一优先级 (动手前必读)

| # | 论文 | 年份 | 核心内容 | 链接 |
|---|------|------|---------|------|
| 1 | Attention Is All You Need | 2017 | Transformer 架构 | arxiv.org/abs/1706.03762 |
| 2 | Language Models are Unsupervised Multitask Learners (GPT-2) | 2019 | 预训练范式 | d4mucfpksywv.cloudfront.net/better-language-models/ |
| 3 | LLaMA: Open and Efficient Foundation Language Models | 2023 | 高效开源路线 | arxiv.org/abs/2302.13971 |
| 4 | Training Compute-Optimal Large Language Models (Chinchilla) | 2022 | 训练效率定律 | arxiv.org/abs/2203.15556 |
| 5 | The Llama 3 Herd of Models | 2024 | 405B 训练全流程 | arxiv.org/abs/2407.21783 |

#### P1 — 第二优先级 (训练前必读)

| # | 论文 | 年份 | 核心内容 | 链接 |
|---|------|------|---------|------|
| 6 | DeepSeek-V2 Technical Report | 2024 | MLA + DeepSeekMoE | arxiv.org/abs/2405.04434 |
| 7 | DeepSeek-V3 Technical Report | 2024 | FP8 + MoE 大规模训练 | arxiv.org/abs/2412.19437 |
| 8 | Mistral 7B | 2023 | 小模型高性能 | arxiv.org/abs/2310.06825 |
| 9 | Scaling Laws for Neural Language Models | 2020 | 规模定律 | arxiv.org/abs/2001.08361 |
| 10 | GPT-4 Technical Report | 2023 | 能力边界 | arxiv.org/abs/2303.08774 |

#### P2 — 进阶阅读

| # | 论文 | 核心内容 |
|---|------|---------|
| 11 | LoRA: Low-Rank Adaptation | 高效微调 |
| 12 | DPO: Direct Preference Optimization | 无需RLHF的对齐 |
| 13 | Training language models to follow instructions (InstructGPT) | RLHF原始方案 |
| 14 | RoPE: Rotary Position Embedding | 位置编码 |
| 15 | FlashAttention (1/2/3) | 高效注意力 |
| 16 | PagedAttention (vLLM) | 高效推理 |
| 17 | QLoRA | 量化微调 |
| 18 | Speculative Decoding | 推测解码 |
| 19 | Mixtral of Experts | 开源MoE方案 |
| 20 | OLMo | 完全开源LLM复现 |

---

## 阅读笔记模板

```markdown
### [论文标题]
- **链接**: 
- **状态**: 🟡/🟢
- **核心贡献**(3句话):
  1. 
  2. 
  3. 
- **关键数据**:
  - 模型规模: 
  - 训练数据: 
  - 训练成本: 
- **可复用技术/技巧**:
  - 
- **对我的项目启示**:
  - 
```
