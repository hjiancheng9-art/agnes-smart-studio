# ⚡ 超级大模型实战手册

> 从数据到部署，每一步的具体操作方案
> 持续更新中

---

## 一、数据处理流水线

### 1.1 数据来源优先级

| 优先级 | 数据源 | 规模 | 质量 | 获取难度 |
|--------|--------|------|------|---------|
| 1 | **FineWeb** (HuggingFace) | 15T tokens | ⭐⭐⭐⭐ | 极低 |
| 2 | **Dolma** (Allen AI) | 3T tokens | ⭐⭐⭐⭐ | 低 |
| 3 | **RedPajama v2** | 30T tokens(原始) | ⭐⭐⭐ | 低 |
| 4 | **The Pile** | 800GB | ⭐⭐⭐⭐⭐ | 低 |
| 5 | **CommonCrawl 原始** | PB级 | ⭐⭐ | 中 |
| 6 | **自行采集** | 定制 | 定制 | 高 |

### 1.2 FineWeb 使用指南

```
数据集: HuggingFaceFW/fineweb
大小: ~15T tokens (经过清洗)
版本: fineweb-2 (2024)
子集: sample-10BT, sample-100BT, sample-350BT

快速开始:
  from datasets import load_dataset
  ds = load_dataset("HuggingFaceFW/fineweb", "sample-10BT", streaming=True)
```

### 1.3 数据处理标准流程

```
原始文本 → 语言检测 → 质量过滤 → 去重 → PII去除 → 分词 → 打包
```

**关键过滤策略**:
1. **语言检测**: fastText 模型, 置信度 > 0.65
2. **困惑度过滤**: KenLM 5-gram 模型, 移除极高/极低困惑度文本
3. **去重**: MinHashLSH (行级) + URL去重 + 精确匹配去重
4. **启发式过滤**: 移除过短(<100字)、过长、特殊字符过多、无终止标点的文本
5. **质量打分**: 使用小模型(如 fastText 分类器)对教育价值/信息密度打分

### 1.4 分词器选择

| 分词器 | 词表大小 | 特点 |
|--------|---------|------|
| GPT-2/3/4 系 | 100K-200K | cl100k_base, o200k_base |
| LLaMA 系 | 32K-128K | SentencePiece BPE |
| DeepSeek 系 | 128K | BPE + 多语言优化 |
| **推荐: 从0训练** | 128K-256K | BPE + 中文优化 |

---

## 二、模型架构设计参考

### 2.1 DeepSeek-V3 架构精要

DeepSeek-V3 的核心创新：

**MLA (Multi-head Latent Attention)**:
- 将 KV cache 压缩到低维潜在空间
- 推理时从潜在向量重建 K, V
- 大幅减少 KV cache 内存(相比 MHA 节省 ~90%)
- 关键技术：低秩压缩 + 旋转位置编码解耦

**DeepSeekMoE**:
- 细粒度专家：256个专家, 每个token激活8个
- 共享专家：部分专家对所有token激活
- 负载均衡：auxiliary-loss-free 策略
- 动态偏置调整保持专家负载均衡

**辅助技术**:
- FP8 混合精度训练 (首次在大规模MoE中验证)
- 流水线并行 + 专家并行的双重并行
- Multi-Token Prediction (MTP) 辅助训练

### 2.2 Llama 3.1 405B 架构精要

```
• 纯 Dense Transformer (非MoE)
• 126层, 128个注意力头 (GQA, 8个KV头)
• 隐藏维度: 16384
• 前馈网络维度: 53248 (SwiGLU)
• RoPE 位置编码 (theta=500000)
• RMSNorm 归一化
• 上下文窗口: 128K tokens (原始8K, 后扩展)
• 词表大小: 128K
```

### 2.3 架构决策树（推荐路线）

```
目标参数量 < 7B? 
  YES → Dense + RoPE + GQA + RMSNorm + SwiGLU
  NO  → 目标 < 70B?
    YES → Dense + 同上 (或轻量 MoE, 4-8专家)
    NO  → MoE 必选
      专家数: 参数量/活跃量 ≈ 10-20x
      路由: Top-K (k=2-8)
      + 共享专家
      + 负载均衡策略
```

---

## 三、训练基础设施

### 3.1 GPU 选型对比 (2024-2025)

| GPU | 显存 | FP16 TFLOPS | 互联 | 参考单价(云) |
|-----|------|------------|------|------------|
| A100 80GB | 80GB | 312 | NVLink 600GB/s | ~$1-2/小时 |
| H100 80GB | 80GB | 989 | NVLink 900GB/s | ~$2-4/小时 |
| H100 NVL | 94GB×2 | 1978 | NVSwitch | ~$4-6/小时 |
| H200 | 141GB | 989 | NVLink 900GB/s | ~$3-5/小时 |
| B200 | 192GB | 2250 | NVLink 1.8TB/s | ~待定 |

### 3.2 训练规模与硬件需求 (估算)

| 模型规模 | 建议GPU | 数量 | 并行策略 | 预计时间 |
|---------|---------|------|---------|---------|
| 124M | 1×A100 | 1 | 单卡 | 几小时 |
| 1.5B | 1×A100 | 1 | 单卡 | 1-2天 |
| 7B | 8×A100 | 8 | FSDP/ZeRO-2 | 3-7天 |
| 13B | 8×A100 | 8-16 | ZeRO-3 | 1-2周 |
| 70B | 64×A100 | 64 | 3D并行 | 2-4周 |
| 405B | 256×H100 | 256+ | 全并行 | 1-3月 |
| 671B MoE | 2048×H800 | 2048 | 全并行+专家并行 | 2月 (DeepSeek-V3) |

### 3.3 分布式训练策略选择

```
单卡可以装下模型?
  YES → 普通 DDP 或单卡训练
  NO  → 单卡能装下优化器+梯度+激活?
    YES → FSDP (PyTorch) 或 ZeRO-2 (DeepSpeed)
    NO  → 单卡能装下模型一半?
      YES → ZeRO-3 (DeepSpeed) + Gradient Checkpointing
      NO  → 必须模型并行
        张量并行 (TP, 切分矩阵乘法)
        + 流水线并行 (PP, 切分层)
        + 数据并行 (DP)
        → 3D并行 (Megatron-LM方案)
        MoE?
          + 专家并行 (EP)
```

---

## 四、训练配方 (Training Recipe)

### 4.1 标准预训练配置

```yaml
优化器: AdamW
  - β1: 0.9
  - β2: 0.95
  - ε: 1e-8
  - weight_decay: 0.1

学习率调度:
  - warmup: 2000 steps → max_lr
  - cosine decay → min_lr = max_lr × 0.1
  - max_lr: 3e-4 (小模型) 到 1.5e-4 (大模型)

批大小:
  - global_batch_size: 4M tokens (推荐)
  - gradient_accumulation 达到目标批大小

精度: BF16 混合精度 (或 FP8)
序列长度: 4096 (初始) → 逐步扩展到目标长度
```

### 4.2 后训练 (Post-Training)

**SFT (监督微调)**:
- 数据量: 10K-1M 高质量指令对
- 学习率: 2e-5 ~ 1e-4
- Epoch: 1-3 (避免过拟合)
- 损失: 仅计算 response 部分

**DPO (直接偏好优化)**:
- 替代 RLHF 的简化方案
- 需要偏好对 (chosen vs rejected)
- 学习率: 5e-7 ~ 1e-5
- β参数: 0.1 ~ 0.5

**RLHF (PPO)**:
- 更强大但更复杂
- 需要奖励模型 (Reward Model)
- PPO clipping ε: 0.2
- KL penalty: 0.01 ~ 0.1

---

## 五、评估体系

### 5.1 必测基准

| 基准 | 测试能力 | 指标 |
|------|---------|------|
| MMLU | 多领域知识 | Accuracy |
| GSM8K | 数学推理 | Accuracy |
| MATH | 高等数学 | Accuracy |
| HumanEval | 代码生成 | pass@k |
| MBPP | 代码能力 | Accuracy |
| HellaSwag | 常识推理 | Accuracy |
| ARC-Challenge | 科学推理 | Accuracy |
| TruthfulQA | 真实性 | MC2 |
| MT-Bench | 对话能力 | GPT-4 评分 |
| AlpacaEval | 指令遵循 | Win Rate |
| C-Eval / CMMLU | 中文能力 | Accuracy |

### 5.2 评估框架

- **lm-evaluation-harness** (EleutherAI): 一站式评估
- **OpenCompass**: 国产中文友好
- **AlpacaEval**: 对话质量
- **Chatbot Arena**: 人类偏好 (需要部署)

---

## 六、快速动手路径 (30天计划)

### Week 1: nanoGPT 快速入门
```
Day 1-2: 阅读并运行 nanoGPT (github.com/karpathy/nanoGPT)
Day 3-4: 在 Shakespeare 数据集上训练 character-level GPT
Day 5-6: 扩展到 OpenWebText, 训练 GPT-2 级别 (124M)
Day 7: 理解每个模块的代码实现
```

### Week 2: 数据处理实战
```
Day 8-9: 下载 FineWeb sample-10BT
Day 10-11: 搭建数据清洗管道 (去重/过滤)
Day 12-13: 训练 BPE 分词器
Day 14: 数据打包 (将 token 序列打包成训练样本)
```

### Week 3: 小规模预训练
```
Day 15-17: 用 nanoGPT 框架训练 124M 模型 在 FineWeb 上
Day 18-19: 用 lm-evaluation-harness 评估
Day 20-21: 分析训练曲线, 调整超参数
```

### Week 4: SFT + 对齐
```
Day 22-24: 准备 SFT 数据 (开源指令数据集)
Day 25-26: SFT 微调
Day 27-28: DPO 对齐训练
Day 29-30: 部署并测试对话能力
```

---

## 七、关键开源项目速查

```
训练:
  github.com/karpathy/nanoGPT         # 最简GPT实现
  github.com/karpathy/build-nanogpt   # 复现GPT-2 124M
  github.com/karpathy/llm.c           # 纯C实现LLM训练
  github.com/huggingface/nanotron     # 分布式训练库

微调:
  github.com/hiyouga/LLaMA-Factory    # 中文SFT/DPO/RLHF一条龙
  github.com/OpenAccess-AI-Collective/axolotl  # 配置驱动微调
  github.com/huggingface/trl          # SFT/DPO/PPO库

推理:
  github.com/vllm-project/vllm        # 高吞吐推理
  github.com/sgl-project/sglang       # 结构化生成

评估:
  github.com/EleutherAI/lm-evaluation-harness
  github.com/open-compass/opencompass

数据:
  github.com/huggingface/datatrove    # 大规模数据处理
  HuggingFaceFW/fineweb              # 高质量预训练数据
```

---

> 📌 此文档随实践进程持续更新。每次动手实验后记录关键参数和踩坑经验。
