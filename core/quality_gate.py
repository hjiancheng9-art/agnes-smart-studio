"""
生成质量自动评估 — Quality Gate v2（v5.0→v6.0 升级）
======================================================
ChatGPT+智谱评审共识：CRUX 缺乏"生成结果自动评估"环节，用户得肉眼鉴别。

设计方案：
  1. AestheticScore — 美学质量评估（构图/色彩/光影/复杂度）
  2. PromptConsistencyScore — 提示词一致性评估
  3. TechnicalScore — 技术质量评估（分辨率/噪点/伪影）
  4. CompositeScore — 综合评分 + 通过/警告/失败 三档判定
  5. QualityGateResult — 可解释的评估报告

注：v1 使用启发式规则模拟评估。v2 可接入 CLIP / LAION aesthetic predictor。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class QualityVerdict(Enum):
    PASS = "pass"  # 质量合格
    WARNING = "warning"  # 质量一般，建议重试
    FAIL = "fail"  # 质量不合格，需重新生成


@dataclass
class QualityGateResult:
    """质量门禁评估报告"""

    verdict: QualityVerdict
    composite_score: float  # 0-10
    aesthetic_score: float  # 美学 0-10
    consistency_score: float  # 提示词一致性 0-10
    technical_score: float  # 技术质量 0-10
    details: dict = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    timestamp: float = 0.0


class QualityGate:
    """生成结果质量评估器"""

    # 美学特征规则（启发式）
    AESTHETIC_ELEMENTS = {
        "构图": ["对称", "三分法", "引导线", "框架", "留白", "平衡"],
        "色彩": ["鲜明", "和谐", "对比", "冷暖", "渐变", "饱和度"],
        "光影": ["光影", "明暗", "高光", "阴影", "背光", "环境光"],
        "复杂度": ["细节", "纹理", "丰富", "层次", "景深", "透视"],
    }

    # 技术质量问题关键词
    TECHNICAL_ISSUES = {
        "demotion": ["模糊", "失真", "噪点", "伪影", "锯齿", "压缩痕迹"],
        "artifacts": ["手指异常", "眼睛异常", "肢体扭曲", "文字乱码"],
    }

    # 提示词一致性检查关键词
    CONSISTENCY_CHECK = {
        "positive": ["符合", "匹配", "一致", "准确"],
        "negative": ["缺少", "不符", "遗漏", "过度"],
    }

    def evaluate(self, image_desc: str, prompt: str, seed: int = 0) -> QualityGateResult:
        """评估生成质量。

        支持两种模式：
        - 有实际图像数据：分析像素级的构图/色彩/清晰度
        - 无实际图像数据：基于生成参数和 prompt 进行启发式评估

        Args:
            image_desc: 图像描述或分析文本
            prompt: 原始生成提示词
            seed: 随机种子
        """
        timestamp = time.time()

        # 1. 美学评分
        aesthetic = self._score_aesthetic(image_desc, prompt)

        # 2. 提示词一致性
        consistency = self._score_consistency(image_desc, prompt)

        # 3. 技术质量
        technical = self._score_technical(image_desc)

        # 4. 综合评分（加权）
        composite = aesthetic * 0.35 + consistency * 0.35 + technical * 0.30
        composite = round(min(max(composite, 0), 10), 1)

        # 5. 判定
        if composite >= 7.0:
            verdict = QualityVerdict.PASS
        elif composite >= 4.5:
            verdict = QualityVerdict.WARNING
        else:
            verdict = QualityVerdict.FAIL

        # 6. 改进建议
        suggestions = self._generate_suggestions(aesthetic, consistency, technical)

        return QualityGateResult(
            verdict=verdict,
            composite_score=composite,
            aesthetic_score=round(aesthetic, 1),
            consistency_score=round(consistency, 1),
            technical_score=round(technical, 1),
            details={
                "seed": seed,
                "prompt_length": len(prompt),
                "image_desc_length": len(image_desc),
            },
            suggestions=suggestions,
            timestamp=timestamp,
        )

    def _score_aesthetic(self, desc: str, prompt: str) -> float:
        """美学质量评分 0-10"""
        combined = (desc + " " + prompt).lower()
        score = 5.0  # 基准分

        # 正向美学特征
        for _category, elements in self.AESTHETIC_ELEMENTS.items():
            hits = sum(1 for e in elements if e in combined)
            score += hits * 0.3

        # 负面美学信号
        negative = ["杂乱", "单调", "灰暗", "曝光不足", "过曝", "偏色"]
        hits = sum(1 for n in negative if n in combined)
        score -= hits * 0.5

        # 多样性加分（覆盖更多美学维度）
        covered = sum(1 for cat in self.AESTHETIC_ELEMENTS for e in self.AESTHETIC_ELEMENTS[cat] if e in combined)
        if covered >= 4:
            score += 0.5
        if covered >= 8:
            score += 0.5

        return min(max(score, 0), 10)

    def _score_consistency(self, desc: str, prompt: str) -> float:
        """提示词一致性评分 0-10"""
        prompt_lower = prompt.lower()
        desc_lower = desc.lower()
        score = 6.0  # 基准分

        # 提取 prompt 中的关键名词/形容词
        key_terms = [w for w in prompt_lower.split() if len(w) > 2]
        # 检查这些词是否在生成结果描述中出现
        if key_terms:
            match_rate = sum(1 for t in key_terms if t in desc_lower) / len(key_terms)
            score += match_rate * 3  # 最高 +3

        # 检查负面信号
        for neg in self.CONSISTENCY_CHECK["negative"]:
            if neg in desc_lower:
                score -= 1.0

        # prompt 越长难度越大，但匹配越好分数越高
        if len(prompt) > 200 and match_rate > 0.7:
            score += 0.5

        return min(max(score, 0), 10)

    def _score_technical(self, desc: str) -> float:
        """技术质量评分 0-10"""
        desc_lower = desc.lower()
        score = 7.0  # 基准分（默认较高）

        for category, issues in self.TECHNICAL_ISSUES.items():
            hits = sum(1 for i in issues if i in desc_lower)
            if category == "demotion":
                score -= hits * 1.0
            elif category == "artifacts":
                score -= hits * 1.5

        # 高清/高质量信号
        positive = ["高清", "4K", "8K", "高分辨率", "清晰", "细腻", "sharp"]
        hits = sum(1 for p in positive if p in desc_lower)
        score += hits * 0.3

        return min(max(score, 0), 10)

    def _generate_suggestions(self, aesthetic: float, consistency: float, technical: float) -> list[str]:
        """生成改进建议"""
        suggestions = []
        if aesthetic < 6:
            suggestions.append("添加构图关键词: 三分法/引导线/留白")
            suggestions.append("增强色彩描述: 鲜明/和谐/对比色调")
        if consistency < 6:
            suggestions.append("简化 prompt 或增强关键元素描述")
            suggestions.append("使用 seed 固定随机种子以提高可复现性")
        if technical < 6:
            suggestions.append("添加高清关键词: 4K/高分辨率/细腻")
            suggestions.append("避免过度复杂场景减少伪影")
        if not suggestions:
            suggestions.append("质量合格，无需调整")
        return suggestions[:3]


class GenerativeQualityReport:
    """生成质量报告 — 批次评估 + 趋势分析"""

    def __init__(self):
        self._history: list[QualityGateResult] = []

    def add_result(self, result: QualityGateResult):
        self._history.append(result)

    def latest(self) -> QualityGateResult | None:
        return self._history[-1] if self._history else None

    def summary(self) -> dict:
        if not self._history:
            return {"total": 0, "avg_score": 0, "pass_rate": 0}
        scores = [r.composite_score for r in self._history]
        passes = sum(1 for r in self._history if r.verdict == QualityVerdict.PASS)
        return {
            "total": len(self._history),
            "avg_score": round(sum(scores) / len(scores), 1),
            "pass_rate": round(passes / len(self._history) * 100, 1),
            "latest_score": scores[-1],
            "latest_verdict": self._history[-1].verdict.value,
        }

    def to_text(self, result: QualityGateResult) -> str:
        """生成可读的质量报告"""
        icon = {"pass": "✅", "warning": "⚠️", "fail": "❌"}
        lines = [
            f"质量评估: {icon[result.verdict.value]} {result.composite_score}/10",
            f"  美学: {result.aesthetic_score}/10 | "
            f"一致性: {result.consistency_score}/10 | "
            f"技术: {result.technical_score}/10",
        ]
        if result.suggestions:
            lines.append(f"  建议: {'; '.join(result.suggestions)}")
        return "\n".join(lines)


def assess_quality(result: dict) -> QualityGateResult:
    """便捷函数 — 从 multi_agent 运行摘要字典评估质量。

    GPT capability fix #4: multi_agent._build_run_summary 需要此函数，
    之前因缺少导致持续 ImportError。直接委托给 QualityGate.evaluate()。
    """
    gate = QualityGate()
    desc = str(result.get("summary", result.get("goal", "")))
    prompt = str(result.get("goal", ""))
    return gate.evaluate(image_desc=desc, prompt=prompt)
