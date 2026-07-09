"""
TaskSpec Builder — 任务意图结构化解析器
=========================================
ChatGPT 评审核心建议: "TRM 要从关键词匹配升级为 TaskSpec → 工具链规划"

将原始用户意图解析为结构化 TaskSpec:
  - 意图类型 (generate / analyze / modify / search / execute / review)
  - 输入资产 (files / images / urls / code)
  - 输出目标 (text / image / video / code / report)
  - 复杂度评分 (1-10)
  - 风险等级 (low / medium / high / critical)
  - 推荐工具链 (按优先级排序)

与 task_governor 和 tool_registry_mesh 联动，为 TRM 提供结构化输入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class IntentType(Enum):
    GENERATE = "generate"  # 生成 (图片/视频/代码/文档)
    ANALYZE = "analyze"  # 分析 (代码/日志/架构)
    MODIFY = "modify"  # 修改 (文件/配置)
    SEARCH = "search"  # 搜索 (代码/知识)
    EXECUTE = "execute"  # 执行 (脚本/命令/测试)
    REVIEW = "review"  # 审查 (代码/安全/质量)
    DIAGNOSE = "diagnose"  # 诊断 (错误/性能)
    DEPLOY = "deploy"  # 部署 (危险)


class AssetType(Enum):
    FILE = "file"
    IMAGE = "image"
    VIDEO = "video"
    CODE = "code"
    URL = "url"
    DIRECTORY = "directory"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Asset:
    type: AssetType
    path_or_value: str
    description: str = ""


@dataclass
class TaskSpec:
    """结构化任务描述 — TRM 路由的核心输入"""

    intent: str  # 原始用户输入
    intent_type: IntentType  # 意图分类
    summary: str  # 一句话摘要
    complexity: int = 1  # 复杂度 1-10
    risk: RiskLevel = RiskLevel.LOW  # 风险等级
    input_assets: list[Asset] = field(default_factory=list)
    output_type: str = "text"  # 预期输出类型
    suggested_category: str = "infra"  # 推荐工具分类 (infra/creative/code/web/data/ai)
    requires_multi_agent: bool = False  # 是否需要多智能体
    requires_approval: bool = False  # 是否需要人工确认
    estimated_tools: int = 1  # 预估工具调用数
    constraints: list[str] = field(default_factory=list)  # 约束条件
    context_hints: dict = field(default_factory=dict)  # 上下文提示


class TaskSpecBuilder:
    """将原始意图解析为 TaskSpec"""

    # 意图分类关键词
    INTENT_PATTERNS = {
        IntentType.GENERATE: [
            "生成",
            "创建",
            "画",
            "制作",
            "渲染",
            "导出",
            "generate",
            "create",
            "render",
            "make",
        ],
        IntentType.ANALYZE: [
            "分析",
            "查看",
            "检查",
            "评估",
            "评审",
            "审查",
            "analyze",
            "inspect",
            "evaluate",
            "review",
        ],
        IntentType.MODIFY: [
            "修改",
            "改",
            "更新",
            "修复",
            "修",
            "调整",
            "重构",
            "modify",
            "fix",
            "update",
            "refactor",
            "change",
        ],
        IntentType.SEARCH: [
            "搜索",
            "查找",
            "找",
            "搜索代码",
            "搜",
            "search",
            "find",
            "lookup",
        ],
        IntentType.EXECUTE: [
            "运行",
            "执行",
            "跑",
            "启动",
            "构建",
            "编译",
            "测试",
            "run",
            "execute",
            "build",
            "compile",
            "test",
        ],
        IntentType.REVIEW: [
            "审查",
            "review",
            "审计",
            "audit",
            "检查代码",
            "安全检查",
            "代码审查",
        ],
        IntentType.DIAGNOSE: [
            "为什么",
            "报错",
            "出错",
            "失败",
            "不行",
            "不对",
            "哪里错",
            "怎么回事",
            "debug",
            "排查",
            "诊断",
            "why",
            "error",
            "failed",
            "broken",
        ],
        IntentType.DEPLOY: [
            "部署",
            "发布",
            "上线",
            "推送",
            "deploy",
            "release",
            "publish",
        ],
    }

    # 输出类型推断
    OUTPUT_HINTS = {
        "图片": "image",
        "图": "image",
        "image": "image",
        "照片": "image",
        "插画": "image",
        "视频": "video",
        "video": "video",
        "动画": "video",
        "代码": "code",
        "code": "code",
        "脚本": "code",
        "script": "code",
        "报告": "report",
        "report": "report",
        "总结": "report",
        "文档": "document",
        "document": "document",
    }

    # 高风险关键词
    HIGH_RISK_PATTERNS = [
        "删除",
        "销毁",
        "清空",
        "重置",
        "覆盖",
        "生产环境",
        "正式环境",
        "线上",
        "prod",
        "所有",
        "全部",
        "整个项目",
    ]

    def build(self, intent: str, context: dict = None) -> TaskSpec:
        """解析意图为 TaskSpec"""
        context = context or {}
        intent_lower = intent.lower()

        # 1. 意图分类
        intent_type = self._classify_intent(intent_lower)
        summary = self._make_summary(intent, intent_type)

        # 2. 复杂度
        complexity = self._estimate_complexity(intent, context)

        # 3. 风险
        risk = self._assess_risk(intent_lower)

        # 4. 输入资产
        assets = self._extract_assets(intent)

        # 5. 输出类型
        output_type = self._infer_output(intent_lower)

        # 6. 工具分类
        category = self._suggest_category(intent_type, output_type)

        # 7. 多智能体
        try:
            from core.multi_agent import compute_agent_mode

            agent_mode, _, _ = compute_agent_mode(intent)
            requires_multi = agent_mode.value in ("swarm", "plan_execute")
        except (ImportError, AttributeError):
            requires_multi = False

        # 8. 人工确认
        requires_approval = risk in (RiskLevel.CRITICAL, RiskLevel.HIGH) or intent_type == IntentType.DEPLOY

        return TaskSpec(
            intent=intent,
            intent_type=intent_type,
            summary=summary,
            complexity=complexity,
            risk=risk,
            input_assets=assets,
            output_type=output_type,
            suggested_category=category,
            requires_multi_agent=requires_multi,
            requires_approval=requires_approval,
            estimated_tools=complexity // 2 + 1,
            constraints=self._extract_constraints(intent_lower),
            context_hints=context,
        )

    def _classify_intent(self, intent_lower: str) -> IntentType:
        scores = {}
        for itype, patterns in self.INTENT_PATTERNS.items():
            score = sum(1 for p in patterns if p in intent_lower)
            if score > 0:
                scores[itype] = score

        if not scores:
            return IntentType.ANALYZE  # 默认分析

        # 诊断优先（"为什么报错" 既匹配 diagnose 也匹配 analyze）
        if IntentType.DIAGNOSE in scores and scores.get(IntentType.DIAGNOSE, 0) >= 1:
            return IntentType.DIAGNOSE

        # 部署优先（高风险）
        if IntentType.DEPLOY in scores:
            return IntentType.DEPLOY

        return max(scores, key=scores.get)

    def _make_summary(self, intent: str, itype: IntentType) -> str:
        prefix = {
            IntentType.GENERATE: "生成",
            IntentType.ANALYZE: "分析",
            IntentType.MODIFY: "修改",
            IntentType.SEARCH: "搜索",
            IntentType.EXECUTE: "执行",
            IntentType.REVIEW: "审查",
            IntentType.DIAGNOSE: "诊断",
            IntentType.DEPLOY: "部署",
        }
        short = intent[:60] + ("..." if len(intent) > 60 else "")
        return f"[{prefix[itype]}] {short}"

    def _estimate_complexity(self, intent: str, context: dict) -> int:
        score = 1
        n = len(intent)
        if n > 500:
            score += 2
        elif n > 200:
            score += 1

        # 关键词密度
        for kw in ["并且", "同时", "然后", "接着", "另外", "还要", "再"]:
            if kw in intent:
                score += 1

        # 上下文复杂性
        if context.get("files_touched", 0) >= 3:
            score += 2
        if context.get("recent_failures", 0) >= 2:
            score += 2

        return min(score, 10)

    def _assess_risk(self, intent_lower: str) -> RiskLevel:
        high_risk_count = sum(1 for p in self.HIGH_RISK_PATTERNS if p in intent_lower)
        if "生产环境" in intent_lower or "prod" in intent_lower:
            return RiskLevel.CRITICAL
        if high_risk_count >= 2:
            return RiskLevel.HIGH
        if high_risk_count >= 1:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _extract_assets(self, intent: str) -> list[Asset]:
        assets = []
        # 文件路径
        import re

        path_patterns = [
            r"(?:文件|路径|path|file)[：:]\s*([^\s,，、]+)",
            r"([\w/\\-]+\.[\w]{1,6})",  # filename.ext
        ]
        found = set()
        for pat in path_patterns:
            for m in re.finditer(pat, intent):
                val = m.group(1) if m.lastindex else m.group(0)
                if val not in found and len(val) > 2:
                    found.add(val)
                    atype = (
                        AssetType.IMAGE
                        if val.endswith((".png", ".jpg", ".webp"))
                        else AssetType.VIDEO
                        if val.endswith((".mp4", ".mov", ".webm"))
                        else AssetType.FILE
                    )
                    assets.append(Asset(type=atype, path_or_value=val))
        return assets

    def _infer_output(self, intent_lower: str) -> str:
        for hint, otype in self.OUTPUT_HINTS.items():
            if hint in intent_lower:
                return otype
        return "text"

    def _suggest_category(self, itype: IntentType, output_type: str) -> str:
        if itype == IntentType.GENERATE and output_type in ("image", "video"):
            return "creative"
        if itype in (IntentType.MODIFY, IntentType.REVIEW):
            return "code"
        if itype == IntentType.SEARCH:
            return "web"
        if itype == IntentType.EXECUTE:
            return "infra"
        if itype == IntentType.DIAGNOSE:
            return "code"
        if itype == IntentType.DEPLOY:
            return "infra"
        return "infra"

    def _extract_constraints(self, intent_lower: str) -> list[str]:
        constraints = []
        if "不要修改" in intent_lower:
            constraints.append("read_only")
        if "只读" in intent_lower:
            constraints.append("read_only")
        if "不生成文件" in intent_lower:
            constraints.append("no_file_output")
        if "先确认" in intent_lower:
            constraints.append("confirm_before_execute")
        return constraints
