"""
技能市场推荐引擎 — 与 TRM 联动实现隐式推荐（v5.0→v6.0 升级）
=============================================================
ChatGPT+智谱评审共识：51 个技能包利用率低的根因是"有市场无推荐引擎"。

设计方案：
  1. 技能包注册场景标签 (tags) + 使用频率 (usage_count)
  2. SkillRecommender 根据 TaskSpec 意图分类推荐技能包
  3. 与 TRM suggest_tools() 联动，推荐工具的同时推荐关联技能包
  4. 高频/高质量技能包自动置顶，低频技能包折叠
  5. 记录技能包使用效果反馈 (success_rate)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SkillEntry:
    """技能包元数据"""

    name: str
    category: str  # creative / quality / tool / video / other
    tags: list[str]  # 场景标签，如 "comfyui", "code-review", "batch"
    description: str = ""
    version: str = "1.0"
    usage_count: int = 0
    success_count: int = 0
    avg_latency_ms: float = 0.0
    is_local: bool = True  # CodeBuddy 本地 or 远程市场
    hidden: bool = False  # 低频技能折叠

    @property
    def success_rate(self) -> float:
        if self.usage_count == 0:
            return 0.5
        return self.success_count / self.usage_count

    @property
    def score(self) -> float:
        """综合评分：成功率 × 使用量因子"""
        base = self.success_rate * 10
        usage_factor = min(self.usage_count / 50, 1.0)  # 50次以上达满分
        return round(base * (0.6 + 0.4 * usage_factor), 2)


class SkillRecommender:
    """技能市场推荐引擎 — 根据 TaskSpec/意图推荐技能包"""

    # 技能包 → 场景标签映射（基于 CRUX 技能市场分类）
    SKILL_TAGS: dict[str, list[str]] = {
        # creative 类
        "comfyui-basic": ["comfyui", "workflow", "图片生成", "节点编排"],
        "comfyui-advanced": ["comfyui", "高级节点", "自定义节点", "LoRA"],
        "image-batch": ["图片", "批量处理", "后处理", "放大"],
        "video-pipeline": ["视频", "动画", "关键帧", "渲染"],
        "style-transfer": ["风格迁移", "滤镜", "艺术效果"],
        # quality 类
        "code-linter": ["代码检查", "lint", "风格检查", "质量"],
        "security-scan": ["安全", "漏洞扫描", "审计"],
        "performance-audit": ["性能", "基准测试", "优化"],
        # tool 类
        "git-workflow": ["git", "版本控制", "分支管理"],
        "ci-cd-pipeline": ["CI/CD", "构建", "部署", "流水线"],
        "db-manager": ["数据库", "SQL", "迁移"],
        "api-tester": ["API", "测试", "REST", "接口"],
        # video 类
        "video-editing": ["视频编辑", "剪辑", "特效"],
        "motion-graphics": ["动效", "运动图形"],
        # other
        "document-gen": ["文档", "报告", "导出", "markdown"],
        "prompt-optimizer": ["提示词", "prompt", "优化", "模板"],
    }

    # 意图类型 → 推荐技能包
    INTENT_SKILL_MAP: dict[str, list[str]] = {
        "generate": ["comfyui-basic", "image-batch", "video-pipeline", "style-transfer"],
        "analyze": ["code-linter", "security-scan", "performance-audit"],
        "modify": ["git-workflow", "db-manager"],
        "search": ["prompt-optimizer"],
        "execute": ["ci-cd-pipeline", "api-tester", "git-workflow"],
        "review": ["code-linter", "security-scan", "performance-audit"],
        "diagnose": ["code-linter", "performance-audit"],
        "deploy": ["ci-cd-pipeline"],
    }

    def __init__(self):
        self._skills: dict[str, SkillEntry] = {}
        self._load_defaults()

    def _load_defaults(self):
        for name, tags in self.SKILL_TAGS.items():
            # 自动推断分类
            cat = "other"
            for c in ["creative", "quality", "tool", "video"]:
                if c in name or any(c in t for t in tags):
                    cat = c
                    break
            self._skills[name] = SkillEntry(
                name=name,
                category=cat,
                tags=tags,
                description=f"技能包: {name} ({', '.join(tags[:3])})",
            )

    def register(self, skill: SkillEntry):
        self._skills[skill.name] = skill

    def recommend(self, task_type: str, top_k: int = 5) -> list[tuple[str, float]]:
        """根据任务类型推荐技能包"""
        candidates = []
        recommended_names = self.INTENT_SKILL_MAP.get(task_type, [])

        for name in recommended_names:
            skill = self._skills.get(name)
            if skill and not skill.hidden:
                candidates.append((name, skill.score))

        # 按评分排序
        candidates.sort(key=lambda x: -x[1])

        # 如果推荐不足，补充其他分类的高分技能包
        if len(candidates) < top_k:
            for name, skill in self._skills.items():
                if name not in [c[0] for c in candidates] and not skill.hidden:
                    candidates.append((name, skill.score * 0.5))  # 降权

        candidates.sort(key=lambda x: -x[1])
        return candidates[:top_k]

    def recommend_by_tags(self, tags: list[str], top_k: int = 5) -> list[tuple[str, float]]:
        """根据场景标签推荐技能包"""
        candidates = []
        for name, skill in self._skills.items():
            if skill.hidden:
                continue
            match_score = sum(1 for t in tags if t in skill.tags)
            if match_score > 0:
                candidates.append((name, skill.score * (1 + 0.2 * match_score)))

        candidates.sort(key=lambda x: -x[1])
        return candidates[:top_k]

    def record_use(self, name: str, success: bool, latency_ms: float = 0):
        """记录技能包使用效果"""
        if name in self._skills:
            self._skills[name].usage_count += 1
            if success:
                self._skills[name].success_count += 1
            if latency_ms > 0:
                old = self._skills[name].avg_latency_ms
                n = self._skills[name].usage_count
                self._skills[name].avg_latency_ms = (old * (n - 1) + latency_ms) / n

    def hide_low_performers(self, threshold: float = 0.3):
        """自动隐藏低绩效技能包（成功率 < 阈值 且 使用量 > 10）"""
        for _name, skill in self._skills.items():
            if skill.usage_count > 10 and skill.success_rate < threshold:
                skill.hidden = True

    def get_stats(self) -> dict:
        """获取技能市场统计"""
        total = len(self._skills)
        hidden = sum(1 for s in self._skills.values() if s.hidden)
        by_cat = {}
        for s in self._skills.values():
            by_cat.setdefault(s.category, 0)
            by_cat[s.category] += 1
        top = sorted(self._skills.values(), key=lambda s: -s.score)[:5]
        return {
            "total_skills": total,
            "hidden": hidden,
            "active": total - hidden,
            "by_category": by_cat,
            "top_skills": [{"name": s.name, "score": s.score, "usage": s.usage_count} for s in top],
        }

    def to_recommendation_text(self, task_type: str, top_k: int = 3) -> str:
        """生成技能推荐文本（用于嵌入系统提示词）"""
        recs = self.recommend(task_type, top_k)
        if not recs:
            return ""
        lines = ["📦 推荐技能包:"]
        for name, score in recs:
            skill = self._skills.get(name)
            if skill:
                lines.append(f"  • {name} (评分{score:.1f}) — {skill.description}")
        return "\n".join(lines)
