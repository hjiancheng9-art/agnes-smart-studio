"""CWIM → ASM 映射挂载点

GPT 规格结论：CWIM 10 条原则中 6 条已泛化为 ASM.core，3 条保留为 CWIM 专属，
1 条不需要映射（LLM 不直接生成 JSON —— 这是 ComfyUI 工具链的内部约束，
不是方法论原则）。

映射表：
| CWIM 原则                           | 归属        | 处理方式                         |
|-------------------------------------|-------------|----------------------------------|
| 永远不要先生成 Workflow              | ASM.core    | 泛化为"先理解目标结构再执行"       |
| 优先复用成熟 Workflow               | CWIM        | 保留，domain=comfyui 时加载       |
| LLM 不直接生成 ComfyUI JSON         | CWIM        | 保留（工具链约束，非方法论）       |
| 所有 Workflow 必须经过 Validator     | ASM.core    | 泛化为"产物必须可验证"             |
| 失败不是结束而是学习                 | ASM.core    | 泛化为"失败必须写入 EventLog"      |
| 参数不是数字而是语义                 | ASM.core    | 已泛化                           |
| 所有推荐必须可解释                   | ASM.core    | 已泛化                           |
| LoRA 是项目不是文件                  | CWIM        | 保留，ComfyUI 专属                |
| Workflow 是图不是 JSON              | CWIM        | 保留，ComfyUI 专属                |
| 用户面对任务不是节点                 | ASM.core    | 已泛化                           |

CWIM 降级后保留 3 条专属原则（复用 Workflow / LoRA 生命周期 / 图结构）。
挂载点：domain=comfyui 时加载 ASM.core + CWIM（通过 Methodology Router）。
"""

from dataclasses import dataclass, field

# ── CWIM 原则归属映射 ─────────────────────────────────────

CWIM_PRINCIPLES = [
    # (序号, 原文, 归属, 备注)
    (1, "永远不要先生成 Workflow — 先理解任务类型/输入输出/约束",
     "ASM.core", "泛化为'先理解目标结构再执行'，通用原则"),
    (2, "优先复用成熟 Workflow — 模板 > Motif组合 > 子图 > 最后才生成",
     "CWIM", "ComfyUI 专属，保留为领域方法论"),
    (3, "LLM 不直接生成 ComfyUI JSON — 必须经过 TaskSpec → WorkflowIR → GraphCompiler",
     "CWIM", "工具链约束，保留为 ComfyUI 专属"),
    (4, "所有 Workflow 必须经过 Validator 校验",
     "ASM.core", "泛化为'产物必须可验证'，通用原则"),
    (5, "失败不是结束，而是学习 — 保存错误/参数/patch",
     "ASM.core", "泛化为'失败必须写入 EventLog + Retro'，通用原则"),
    (6, "参数不是数字，而是语义 — 按语义维度推荐",
     "ASM.core", "已泛化，核心原则"),
    (7, "所有推荐必须可解释 — 告诉用户'为什么推荐这个'",
     "ASM.core", "已泛化，核心原则"),
    (8, "LoRA 是项目，不是文件 — 全生命周期管理",
     "CWIM", "ComfyUI 专属，保留"),
    (9, "Workflow 是图，不是 JSON — 基于图结构操作",
     "CWIM", "ComfyUI 专属，保留"),
    (10, "用户面对任务，不是节点 — 术语面向任务",
     "ASM.core", "已泛化，核心原则"),
]


@dataclass
class CWIMMapping:
    """CWIM 到 ASM 的映射记录。"""
    asm_principles: list[dict] = field(default_factory=list)
    cwim_retained: list[dict] = field(default_factory=list)
    
    def __post_init__(self):
        for num, text, owner, note in CWIM_PRINCIPLES:
            entry = {"number": num, "text": text, "note": note}
            if owner == "ASM.core":
                self.asm_principles.append(entry)
            else:
                self.cwim_retained.append(entry)


def get_mapping() -> CWIMMapping:
    """获取 CWIM→ASM 映射。"""
    return CWIMMapping()


# ── domain=comfyui 时的方法论组合 ──────────────────────────

COMFYUI_METHODOLOGY_PACK = {
    "always": ["ASM.core"],        # 始终加载
    "domain_specific": ["CWIM"],   # 领域专属
    "notes": "CWIM 降级为 ASM 子方法论，挂载在 domain=comfyui",
}

# ComfyUI 任务路由规则（供 Methodology Router 使用）
COMFYUI_ROUTE = {
    "intents": ["generate"],       # 主要意图
    "domain": "comfyui",
    "methodologies": ["ASM.core", "CWIM"],
    "checks_extra": [
        "workflow-validate",       # Validator 校验
        "model-compatible",        # 模型兼容性
        "lora-lifecycle",          # LoRA 全生命周期
        "node-graph-valid",        # 图结构有效
    ],
}
