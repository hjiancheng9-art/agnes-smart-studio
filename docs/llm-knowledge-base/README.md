# 🧠 超级大模型知识库

> 目标：从零开始，逐步积累，最终训练出自己的 GPT/DeepSeek 级别大模型
> 创建时间：2025-01-15
> 状态：持续更新中

---

## 📋 总路线图

```
第一阶段 (1-3月)    第二阶段 (3-6月)    第三阶段 (6-12月)    第四阶段 (12月+)
  理论基础             小规模实验           中规模训练           全力冲刺
  ─────────           ─────────           ─────────           ─────────
  • Transformer原理    • GPT-2级别(124M)   • 1B-7B级别训练       • 100B+ 级别
  • 注意力机制          • 数据管道搭建       • MoE架构实验         • 生产化部署
  • 训练范式理解        • 微调实验           • 对齐训练(SFT/RLHF)  • 持续预训练
  • 分布式基础          • 评估体系建立       • 推理优化            • 多模态扩展
```

---

## 📚 一、核心理论基础

### 1.1 必读论文（按阅读顺序）

| # | 论文 | 核心贡献 | 状态 |
|---|------|---------|------|
| 1 | **Attention Is All You Need** (Vaswani et al., 2017) | Transformer 架构原点 | ⬜ |
| 2 | **GPT-1: Improving Language Understanding** (Radford et al., 2018) | 生成式预训练范式 | ⬜ |
| 3 | **GPT-2: Language Models are Unsupervised Multitask Learners** (2019) | 零样本泛化 | ⬜ |
| 4 | **GPT-3: Language Models are Few-Shot Learners** (Brown et al., 2020) | 规模定律初现 | ⬜ |
| 5 | **Scaling Laws for Neural Language Models** (Kaplan et al., 2020) | Chinchilla 定律前身 | ⬜ |
| 6 | **Training Compute-Optimal Large Language Models** (Hoffmann et al., 2022) | Chinchilla 定律 | ⬜ |
| 7 | **LLaMA: Open and Efficient Foundation Language Models** (Touvron et al., 2023) | 高效开源路线 | ⬜ |
| 8 | **LLaMA 2: Open Foundation and Fine-Tuned Chat Models** (2023) | 开源对齐方案 | ⬜ |
| 9 | **Mistral 7B** (Jiang et al., 2023) | 小模型高性能 | ⬜ |
| 10 | **DeepSeek-V2/V3 Technical Report** (2024) | MoE + 高效注意力 | ⬜ |
| 11 | **GPT-4 Technical Report** (OpenAI, 2023) | 能力边界参考 | ⬜ |
| 12 | **Llama 3 Herd of Models** (Meta, 2024) | 405B 开源巅峰 | ⬜ |

### 1.2 关键概念清单

- [ ] **Transformer 架构**: Self-Attention, Multi-Head Attention, FFN, Layer Norm, Residual
- [ ] **训练范式**: Pre-training → SFT (Supervised Fine-Tuning) → RLHF/DPO
- [ ] **注意力变体**: MHA, MQA (Multi-Query Attention), GQA (Grouped-Query Attention)
- [ ] **位置编码**: Absolute, Relative, RoPE (Rotary Position Embedding), ALiBi
- [ ] **MoE (Mixture of Experts)**: Router, Load Balancing, Auxiliary Loss
- [ ] **分布式训练**: Data Parallel, Model Parallel, Pipeline Parallel, FSDP, ZeRO
- [ ] **量化**: GPTQ, AWQ, GGUF, bitsandbytes, FP8/FP4
- [ ] **推理优化**: KV Cache, PagedAttention, Speculative Decoding, Flash Attention
- [ ] **对齐技术**: RLHF (PPO), DPO, Constitutional AI, RLAIF
- [ ] **评估基准**: MMLU, HumanEval, GSM8K, HELM, AlpacaEval, MT-Bench

---

## 🛠️ 二、关键开源工具和框架

### 2.1 训练框架

| 框架 | 特点 | 适用场景 |
|------|------|---------|
| **Megatron-LM** (NVIDIA) | 工业级分布式, 3D并行 | 大规模预训练 |
| **DeepSpeed** (Microsoft) | ZeRO优化, 易用 | 中大规模训练 |
| **ColossalAI** | 多维并行, 国产 | 弹性训练 |
| **FSDP** (PyTorch) | 原生集成 | 中小规模训练 |
| **HuggingFace Trainer** | 最易用 | 微调/小规模 |
| **Axolotl** | 社区活跃, 配置驱动 | 微调 |
| **LLaMA-Factory** | 国产, UI友好 | 微调/SFT |

### 2.2 数据处理

| 工具 | 用途 |
|------|------|
| **Datatrove** | 大规模语料过滤去重 |
| **Dolma** | Allen AI 的数据工具链 |
| **TextFilter** | 质量过滤 |
| **MinHashLSH** | 去重 |
| **KenLM** | 困惑度过滤 |
| **CCNet** | CommonCrawl 提取 |

### 2.3 推理部署

| 工具 | 特点 |
|------|------|
| **vLLM** | PagedAttention, 高吞吐 |
| **Text Generation Inference** (HuggingFace) | 生产级 |
| **TensorRT-LLM** | NVIDIA 极致优化 |
| **SGLang** | 结构化生成 |

---

## 📊 三、核心数据

### 3.1 算力需求估算（Chinchilla 最优）

| 模型规模 | 训练Token | 所需GPU时(A100-80G) | 成本估算 |
|---------|----------|-------------------|---------|
| 125M (GPT-2 small) | 2.5B | ~100 | ~$200 |
| 1.5B (GPT-2 XL) | 30B | ~1000 | ~$2,000 |
| 7B | 140B | ~5000 | ~$10,000 |
| 13B | 260B | ~10000 | ~$20,000 |
| 70B | 1.4T | ~50000 | ~$100,000 |
| 405B (Llama 3) | 15T | ~500000 | ~$1,000,000 |
| 1T+ (GPT-4级) | ~15T+ | ~数百万 | ~$数千万-亿 |

> 注：基于公开数据估算，实际出入可能较大。Chinchilla 定律: tokens ≈ 20 × params

### 3.2 训练数据组成参考

| 数据源 | 占比(典型) | 作用 |
|--------|-----------|------|
| CommonCrawl (清洗后) | 50-60% | 广度知识 |
| 代码 (GitHub等) | 10-15% | 推理能力 |
| 书籍 | 5-10% | 长文本、深度 |
| 学术论文 | 5-8% | 专业知识 |
| Wikipedia | 3-5% | 事实准确性 |
| 高质量对话 | 5% | 对话能力 |
| 多语言 | 10% | 多语言支持 |

---

## 🔬 四、著名模型架构速查

### 4.1 关键架构演进

| 模型 | 参数量 | 架构亮点 | 训练数据 | 训练成本 |
|------|--------|---------|---------|---------|
| GPT-2 | 1.5B | 纯Decoder | 40GB文本 | $数万 |
| GPT-3 | 175B | 纯Decoder,Dense | 570GB | $数百万 |
| LLaMA | 7/13/33/65B | RoPE,SwiGLU | 1.4T tokens | - |
| LLaMA 2 | 7/13/70B | GQA,更长上下文 | 2T tokens | - |
| Mistral 7B | 7B | GQA,Sliding Window | - | - |
| DeepSeek-V2 | 236B (21B active) | MLA,DeepSeekMoE | 8.1T tokens | ~$5M |
| DeepSeek-V3 | 671B (37B active) | MLA,MoE,FP8 | 14.8T tokens | ~$5.5M |
| Llama 3.1 | 8B/70B/405B | Dense+MoE,RoPE | 15T+ tokens | - |
| GPT-4 | ~1.8T (估计) | MoE (8×220B) | - | ~$数千万-亿 |

### 4.2 核心技术选择对比

| 技术 | 选项A | 选项B | 当前趋势 |
|------|-------|-------|---------|
| 注意力 | Multi-Head (MHA) | Grouped-Query (GQA) | → GQA |
| 位置编码 | Learned | RoPE | → RoPE |
| 激活函数 | GeLU | SwiGLU | → SwiGLU |
| 归一化 | LayerNorm | RMSNorm | → RMSNorm |
| 架构 | Dense (全连接) | MoE (混合专家) | → MoE (大模型) |
| 精度 | BF16 | FP8 | → FP8 (训练) |
| 批大小 | Fixed | Dynamic (warmup) | → Dynamic |

---

## 📖 五、推荐学习路径

### 5.1 视频课程

- [ ] **Andrej Karpathy - "Let's build GPT from scratch"** (YouTube): 从零写 GPT
- [ ] **Andrej Karpathy - "Let's reproduce GPT-2"**: 复现 GPT-2 124M
- [ ] **Stanford CS324 - Large Language Models**: 系统课程
- [ ] **Stanford CS25 - Transformers United**: Transformer 专题
- [ ] **李沐 - 动手学深度学习**: 中文首选

### 5.2 动手项目（按难度）

| 项目 | 难度 | 时间 |
|------|------|------|
| nanoGPT (Karpathy) | ⭐ | 1周 |
| 从头训练 GPT-2 124M | ⭐⭐ | 2-4周 |
| 微调 Llama 3 进行SFT | ⭐⭐ | 1-2周 |
| DPO/RLHF 对齐训练 | ⭐⭐⭐ | 2-4周 |
| 训练 1B+ 模型 | ⭐⭐⭐⭐ | 1-3月 |
| 搭建分布式训练集群 | ⭐⭐⭐⭐⭐ | 持续 |

---

## 🔗 六、关键资源链接

### 社区和论坛
- r/LocalLLaMA (Reddit): 本地LLM社区
- r/MachineLearning (Reddit): 机器学习研究
- HuggingFace Discord/Forum: 模型和工具
- EleutherAI Discord: 开源LLM核心社区

### 工具仓库
- github.com/karpathy/nanoGPT
- github.com/karpathy/llm101n (新课程)
- github.com/huggingface/alignment-handbook
- github.com/hiyouga/LLaMA-Factory
- github.com/OpenAccess-AI-Collective/axolotl

### 数据资源
- HuggingFace FineWeb (15T tokens)
- RedPajama-Data (1.2T+ tokens)
- The Pile (800GB)
- Dolma (3T tokens)
- CommonCrawl
- Stack (代码数据)

---

## 📝 七、日志与进度追踪

### 知识积累日志

| 日期 | 内容 | 备注 |
|------|------|------|
| 2025-01-15 | 知识库初始化 | 创建骨架，收录核心论文/工具/数据 |

### 待办事项

- [ ] 阅读 Attention Is All You Need
- [ ] 运行 nanoGPT 训练
- [ ] 复现 GPT-2 124M 训练
- [ ] 搭建数据处理管道 (CommonCrawl → 清洗 → 去重 → 分词)
- [ ] 积累 GPU 资源/预算
- [ ] 7B 模型首次预训练
- [ ] 实现 MoE 架构

---

> 📌 此文档将作为长期知识沉淀的索引中心。每有新发现、新论文、新工具，及时补充到对应章节。
