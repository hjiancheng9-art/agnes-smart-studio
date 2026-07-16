"""
Routing Signals — 20+ 路由信号定义
===================================
每个信号是一个函数，输入请求文本 → 输出信号值 (0.0 ~ 1.0)。
信号加权投票给不同模式，替代简单关键词 if/elif。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class RouteSignal:
    """单个路由信号"""

    name: str  # 信号名称
    weight: float = 1.0  # 权重
    votes: dict[str, float] = field(default_factory=dict)  # {mode: score}
    description: str = ""


# ── 信号函数类型 ──
SignalFn = Callable[[str, dict], float]  # (text, context) → value 0.0~1.0


# ════════════════════════════════════════════════
# ── 信号集合 ──
# ════════════════════════════════════════════════


def signal_has_code(text: str, ctx: dict) -> float:
    """是否包含代码相关关键词"""
    score = 0.0
    if re.search(r"```\w*\n|def |class |import |\.py\b|\.js\b|\.ts\b|\.go\b|\.rs\b|\.java\b", text):
        score = max(score, 0.8)
    if re.search(
        r"函数|方法|类\s|接口|模块|实现|编写|代码|脚本|func |const |let |var |async |await |export|lambda|API|库|包|依赖",
        text,
    ):
        score = max(score, 0.6)
    if re.search(r"写一个|写个|实现.*功能|编写.*代码|改成|修改.*代码", text):
        score = max(score, 0.4)
    # 特定技术栈关键词
    if re.search(r"requests|httpx|flask|django|react|vue|spring|sql|orm|jwt|oauth|graphql", text.lower()):
        score = max(score, 0.5)
    if re.search(r"rag|llm|gpt|向量|embedding|微服务|docker|k8s|kubernetes|aws|gcp|azure", text.lower()):
        score = max(score, 0.5)
    return score


def signal_has_multi_step(text: str, ctx: dict) -> float:
    """是否包含多步骤指示"""
    score = 0.0
    if re.search(r"首先|然后|接着|最后|步骤[\s：:]?\d|第一步|第二步", text):
        score = max(score, 0.7)
    if re.search(r"1\.\s|2\.\s|3\.\s|第一步|第二步|第三步", text):
        score = max(score, 0.8)
    if text.count("\n") >= 8:
        score = max(score, 0.4)
    return score


def signal_is_architecture(text: str, ctx: dict) -> float:
    """是否架构/重构类任务"""
    score = 0.0
    if re.search(r"架构|重构|设计模式|分层|模块化|模块拆分", text):
        score = max(score, 0.8)
    if re.search(r"migration|refactor|architecture|decouple|monolith|microservice", text.lower()):
        score = max(score, 0.9)
    if re.search(r"拆分|迁移|重写|改造|升级|替换", text):
        score = max(score, 0.6)
    # 小范围重构（函数/方法级别）→ 降低架构分
    if score > 0.4 and re.search(
        r"重构.*函数|重构.*方法|重构.*变量|重构.*参数|refactor.*func|refactor.*method", text.lower()
    ):
        score *= 0.4
    return score


def signal_has_security_risk(text: str, ctx: dict) -> float:
    """是否存在安全风险"""
    score = 0.0
    if re.search(r"密码|token|secret|密钥|凭证|password|credential", text.lower()):
        score = max(score, 0.6)
    if re.search(r"所有用户|全部用户|批量(重置|删除|修改)", text):
        score = max(score, 0.5)
    if re.search(r"ssh|api[_-]?key|encrypt|decrypt|sudo|root|passwd|shadow", text.lower()):
        score = max(score, 0.7)
    if re.search(r"auth|permission|权限|授权", text.lower()):
        score = max(score, 0.4)
    return score


def signal_has_destructive_ops(text: str, ctx: dict) -> float:
    """是否包含破坏性操作"""
    score = 0.0
    if re.search(r"删除|清空|覆盖|重置|移除|drop\s+table|drop\s+database|truncate|rm\s+-rf", text.lower()):
        score = max(score, 0.6)
    if re.search(r"delete|remove|overwrite|format.*disk|destroy", text.lower()):
        score = max(score, 0.7)
    if re.search(r"/etc/|passwd|系统文件|配置文件|rm\b", text.lower()):
        score = max(score, 0.5)
    if re.search(r"删除.*文件|删除.*所有|清空.*数据|重置.*系统", text):
        score = max(score, 0.8)
    return score


def signal_is_research(text: str, ctx: dict) -> float:
    """是否研究/调查型任务"""
    score = 0.0
    if re.search(r"研究|调研|调查|分析.*对比|对比.*分析|趋势|最新的|当前.*技术", text):
        score = max(score, 0.7)
    if re.search(r"research|survey|compare.*analysis|investigate|state.*of.*art", text.lower()):
        score = max(score, 0.8)
    if re.search(r"选型|方案对比|技术选型|how to|best practice|对比", text.lower()):
        score = max(score, 0.6)
    if re.search(r"研究一下|研究.*技术|技术.*选型|最新.*技术", text):
        score = max(score, 0.8)
    # 如果同时有代码关键词，轻微降低研究分（不降太多）
    if score > 0 and signal_has_code(text, ctx) > 0.5:
        score *= 0.7
    return score


def signal_is_creative(text: str, ctx: dict) -> float:
    """是否创意/设计型任务"""
    score = 0.0
    if re.search(r"创意|设计|风格|美观|配色|布局|UI|UX|文案|brand|marketing", text.lower()):
        score = max(score, 0.6)
    if re.search(r"好看|漂亮|科技感|简约|大气|现代感|酷炫", text):
        score = max(score, 0.7)
    if re.search(r"logo|banner|海报|落地页|首页|产品页", text.lower()):
        score = max(score, 0.8)
    # 如果有代码，降低创意分
    if score > 0 and signal_has_code(text, ctx) > 0.5:
        score *= 0.3
    # 如果有架构/规划/技术方案关键词，降低创意分
    if score > 0.3:
        tech_patterns = [
            "方案",
            "架构",
            "数据库",
            "系统",
            "模块",
            "机制",
            "平台",
            "引擎",
            "框架",
            "协议",
            "接口",
            "服务",
            "中间件",
            "plan",
            "architecture",
            "system",
            "module",
            "schema",
            "platform",
            "engine",
            "framework",
            "protocol",
            "service",
        ]
        tech_hits = sum(1 for p in tech_patterns if p in text.lower())
        if tech_hits >= 2:
            score *= 0.3
    return score


def signal_has_debug_symptom(text: str, ctx: dict) -> float:
    """是否调试/故障排查类"""
    score = 0.0
    if re.search(r"不工作|不生效|炸了|报错|卡住|偶尔|间歇|复现|根因|排查|挂掉|崩溃|死锁", text):
        score = max(score, 0.7)
    if re.search(r"doesn't work|not working|flaky|intermittent|bug|error|crash|traceback|exception", text.lower()):
        score = max(score, 0.8)
    if re.search(r"为什么|what.*wrong|why.*fail|how.*fix", text.lower()):
        score = max(score, 0.4)
    # 深度排查 — 更强的 DEEP 信号
    if re.search(r"排查根因|排查一下|排查.*问题|定位.*问题|根因.*分析|总是.*挂掉|凌晨.*挂", text):
        score = max(score, 0.95)
    return score


def signal_is_deep_investigation(text: str, ctx: dict) -> float:
    """是否深度排查/复杂调试"""
    score = 0.0
    if re.search(r"排查根因|排查一下|排查.*问题|根因分析|定位.*bug|总是.*挂|凌晨.*崩溃", text):
        score = max(score, 0.9)
    if re.search(r"间歇性|随机.*挂|偶发|不定时|复现.*难", text):
        score = max(score, 0.8)
    return score


def signal_has_file_ops(text: str, ctx: dict) -> float:
    """是否涉及文件操作"""
    score = 0.0
    if re.search(r"创建文件|写入|修改文件|新建文件|创建目录|write file|create file|mkdir", text.lower()):
        score = max(score, 0.7)
    if re.search(r"在.*中.*创建|在.*下.*新建|src/|app/|lib/|utils/|core/", text):
        score = max(score, 0.5)
    return score


def signal_is_simple_lookup(text: str, ctx: dict) -> float:
    """是否简单查询/查找"""
    score = 0.0
    if re.search(r"查一下|帮我查查|帮我找找|搜一下|搜索", text):
        score = max(score, 0.7)
    if re.search(r"查.*IP|查.*地址|查.*天气|查.*时间|查.*日期|查.*汇率", text):
        score = max(score, 0.9)
    if re.search(r"look up|find|search.*for|get.*info|what is", text.lower()):
        score = max(score, 0.6)
    # 如果有代码关键词，降低简单查询分
    if score > 0.3 and signal_has_code(text, ctx) > 0.3:
        score *= 0.3
    return score


def signal_is_simple_chat(text: str, ctx: dict) -> float:
    """是否简单聊天"""
    score = 0.0
    # 短文本，无代码，无特殊要求 — 但需要有聊天关键词
    chat_keywords = [
        "你好",
        "hi",
        "hello",
        "hey",
        "早",
        "晚上好",
        "谢谢",
        "感谢",
        "ok",
        "好的",
        "明白",
        "再见",
        "拜拜",
        "晚安",
        "今天.*天气",
        "星期几",
        "几点了",
        "你叫什么",
        "你是谁",
    ]
    has_chat_keyword = any(re.search(k, text.lower()) for k in chat_keywords)

    if has_chat_keyword and len(text) < 15:
        score = 0.9
    elif has_chat_keyword and not signal_has_code(text, ctx) and not signal_has_file_ops(text, ctx):
        score = 0.7
    # 极短的无意义文本
    if len(text) <= 5 and not signal_has_code(text, ctx):
        score = max(score, 0.8)
    # 如果有设计/创意/架构等关键词，降低简单聊天分
    if score > 0.3:
        if signal_is_creative(text, ctx) > 0.3 or signal_is_architecture(text, ctx) > 0.3:
            score *= 0.2
        if signal_has_code(text, ctx) > 0.3 or signal_has_planning_indicators(text, ctx) > 0.3:
            score *= 0.2
    return score


def signal_is_ambiguous(text: str, ctx: dict) -> float:
    """是否模糊请求"""
    score = 0.0
    if re.search(r"帮我看看|你看一下|这个是什么|怎么回事|帮我查查|帮我找找", text):
        score = max(score, 0.5)
    if re.search(r"help me|what is this|how (to|do|can)", text.lower()):
        score = max(score, 0.4)
    if len(text) < 15 and not signal_is_simple_chat(text, ctx):
        score = max(score, 0.3)
    return score


def signal_needs_web_search(text: str, ctx: dict) -> float:
    """是否需要联网搜索"""
    score = 0.0
    web_markers = [
        "最新的",
        "当前的",
        "最近",
        "2024",
        "2025",
        "2026",
        "latest",
        "current",
        "news",
        "update",
        "release",
        "version",
        "compare",
        "vs ",
        "alternative",
    ]
    for m in web_markers:
        if m in text.lower():
            score = max(score, 0.4)
    # 研究型天然需要搜索
    if signal_is_research(text, ctx) > 0.5:
        score = max(score, 0.7)
    return score


def signal_is_test_task(text: str, ctx: dict) -> float:
    """是否测试编写任务"""
    score = 0.0
    if re.search(r"测试|test|spec|unittest|pytest|jest|mocha|vitest|specs", text.lower()):
        score = max(score, 0.5)
    if re.search(r"写.*测试|加.*测试|测试.*覆盖|测试.*用例|单元测试|集成测试", text):
        score = max(score, 0.8)
    return score


def signal_is_rapid_prototype(text: str, ctx: dict) -> float:
    """是否快速原型/最小实现"""
    score = 0.0
    if re.search(r"快速|简单|简易|demo|prototype|最小|quick|simple|basic|minimal|starter|template", text.lower()):
        score = max(score, 0.4)
    if re.search(r"脚手架|样板|模板|boilerplate|scaffold|skeleton", text.lower()):
        score = max(score, 0.6)
    return score


def signal_has_planning_indicators(text: str, ctx: dict) -> float:
    """是否有规划/设计需求"""
    score = 0.0
    if re.search(r"方案|计划|设计|规划|策略|路线|roadmap|plan|strategy|blueprint", text.lower()):
        score = max(score, 0.5)
    # "方案" + "分析" 组合 → 更强的规划信号
    if re.search(r"方案.*分析|分析.*方案|方案.*设计|设计.*方案|压测方案|瓶颈分析", text):
        score = max(score, 0.8)
    if signal_is_architecture(text, ctx) > 0.5:
        score = max(score, 0.8)
    if signal_has_multi_step(text, ctx) > 0.5:
        score = max(score, 0.6)
    return score


def signal_is_bug_fix(text: str, ctx: dict) -> float:
    """是否修复bug"""
    score = 0.0
    if re.search(r"修复|bug|fix|修补|补丁|patch|hotfix|缺陷", text.lower()):
        score = max(score, 0.6)
    if signal_has_debug_symptom(text, ctx) > 0.5:
        score = max(score, 0.3)
    return score


def signal_is_code_review(text: str, ctx: dict) -> float:
    """是否代码审查"""
    score = 0.0
    if re.search(r"审查|review|code review|评审|检视|看看.*代码|检查.*代码", text.lower()):
        score = max(score, 0.8)
    return score


def signal_has_shell_ops(text: str, ctx: dict) -> float:
    """是否涉及shell命令"""
    score = 0.0
    if re.search(r"npm |pip |git |docker |kubectl |bash |sh\s|yarn |pnpm |cargo |go\s", text.lower()):
        score = max(score, 0.7)
    if re.search(r"部署|发布|deploy|build|compile|install|配置环境|setup", text.lower()):
        score = max(score, 0.4)
    return score


# ── 信号注册表 ──


@dataclass
class SignalEntry:
    """信号条目"""

    fn: SignalFn
    weight: float
    votes: dict[str, float]  # {mode: score}
    name: str


# 信号表: 每个信号 + 投票权重 + 投给哪些模式
SIGNAL_REGISTRY: list[SignalEntry] = [
    SignalEntry(signal_has_code, 3.0, {"BALANCED": 0.8, "DEEP": 0.5, "FAST": -0.5}, name="has_code"),
    SignalEntry(signal_has_multi_step, 3.0, {"DEEP": 1.0, "BALANCED": 0.3, "FAST": -1.0}, name="has_multi_step"),
    SignalEntry(signal_is_architecture, 4.0, {"DEEP": 1.0, "BALANCED": 0.2, "FAST": -1.0}, name="is_architecture"),
    SignalEntry(signal_has_security_risk, 5.0, {"SAFE": 1.0, "DEEP": 0.5, "FAST": -1.0}, name="has_security_risk"),
    SignalEntry(signal_has_destructive_ops, 4.0, {"SAFE": 1.0, "DEEP": 0.3, "FAST": -1.0}, name="has_destructive_ops"),
    SignalEntry(
        signal_is_research, 3.5, {"RESEARCH": 1.0, "DEEP": 0.4, "BALANCED": 0.3, "FAST": -0.5}, name="is_research"
    ),
    SignalEntry(signal_is_creative, 2.5, {"CREATIVE": 1.0, "BALANCED": 0.3, "DEEP": -0.3}, name="is_creative"),
    SignalEntry(signal_has_debug_symptom, 3.0, {"BALANCED": 0.7, "DEEP": 0.3, "FAST": -0.3}, name="has_debug_symptom"),
    SignalEntry(
        signal_is_deep_investigation, 4.0, {"DEEP": 1.0, "BALANCED": 0.2, "FAST": -1.0}, name="is_deep_investigation"
    ),
    SignalEntry(signal_has_file_ops, 2.0, {"BALANCED": 0.5, "DEEP": 0.7}, name="has_file_ops"),
    SignalEntry(signal_is_simple_chat, 3.0, {"FAST": 1.0, "BALANCED": -0.5, "DEEP": -1.0}, name="is_simple_chat"),
    SignalEntry(signal_is_simple_lookup, 2.0, {"FAST": 1.0, "BALANCED": -0.2, "DEEP": -0.5}, name="is_simple_lookup"),
    SignalEntry(signal_is_ambiguous, 1.5, {"BALANCED": 0.3, "DEEP": 0.4, "FAST": 0.2}, name="is_ambiguous"),
    SignalEntry(signal_needs_web_search, 2.0, {"RESEARCH": 0.8, "BALANCED": 0.3}, name="needs_web_search"),
    SignalEntry(signal_is_test_task, 2.0, {"BALANCED": 0.5, "DEEP": 0.6}, name="is_test_task"),
    SignalEntry(
        signal_is_rapid_prototype, 1.5, {"FAST": 0.4, "BALANCED": 0.6, "DEEP": -0.3}, name="is_rapid_prototype"
    ),
    SignalEntry(
        signal_has_planning_indicators,
        2.5,
        {"DEEP": 0.8, "RESEARCH": 0.5, "FAST": -0.5},
        name="has_planning_indicators",
    ),
    SignalEntry(signal_is_bug_fix, 2.0, {"BALANCED": 0.6, "DEEP": 0.4, "FAST": 0.2}, name="is_bug_fix"),
    SignalEntry(signal_is_code_review, 2.0, {"BALANCED": 0.5, "DEEP": 0.3}, name="is_code_review"),
    SignalEntry(signal_has_shell_ops, 2.0, {"BALANCED": 0.5, "SAFE": 0.5}, name="has_shell_ops"),
]


def compute_mode_scores(text: str, context: dict | None = None) -> dict[str, float]:
    """计算所有模式的信号评分"""
    ctx = context or {}
    scores: dict[str, float] = {}

    for entry in SIGNAL_REGISTRY:
        try:
            signal_value = entry.fn(text, ctx)
        except Exception:
            signal_value = 0.0

        for mode, vote in entry.votes.items():
            contribution = signal_value * entry.weight * vote
            scores[mode] = scores.get(mode, 0.0) + contribution

    return scores


def get_top_modes(text: str, context: dict | None = None, top_n: int = 2) -> list[tuple[str, float]]:
    """获取得分最高的 N 个模式"""
    scores = compute_mode_scores(text, context)
    sorted_modes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_modes[:top_n]


def get_route_decision(text: str, context: dict | None = None) -> tuple[str, dict[str, float]]:
    """获取路由决策 + 全部分数"""
    scores = compute_mode_scores(text, context)
    if not scores:
        return "BALANCED", {}

    best_mode = max(scores, key=scores.get)
    # 确保分数不过低
    if scores[best_mode] < -2:
        return "FAST", scores

    return best_mode, scores
