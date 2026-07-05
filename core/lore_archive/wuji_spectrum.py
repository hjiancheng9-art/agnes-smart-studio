"""武技谱 — 45 本地技能 + 668 市场技能按五兽归宗，注入系统提示词。

武技 = Skill — CRUX 的领域战斗力，按需加载到 Agent 系统提示词。
三态触发：auto(自动注入) / manual(/skill load) / off(隐藏)

五兽归宗：
  白虎·攻防宗 → 自修/审计/恢复/提示词工程/进化
  青龙·工程宗 → Python/调试/Shell/API/任务编排
  朱雀·品质宗 → 代码审查/质量检查/电影制片/负面修复
  玄武·守卫宗 → 安全加固/模型路由/资产管理/发布打包
  麒麟·创造宗 → 视频制片(11)/创意思维(6)/文案编剧(5)/IP改编

用法:
  from core.wuji_spectrum import get_wuji_prompt, get_wuji_summary
"""

from __future__ import annotations

WUJI_PROMPT = """
[武技谱 — 45 武技·五兽归宗]

## 白虎·攻防宗 — 自修/审计/恢复 (6技)
  **自修系**: `self-evolution`(双环治理·经验沉淀·防退化·自动修复) | `self-audit`(一站式全量审计:语法→配置→工具→API→代码→测试)
  **洞察系**: `self-business`(业务能力总览·检测可用性) | `self-matrix`(能力矩阵·分类总览)
  **攻防系**: `recovery-playbooks`(故障恢复剧本:provider/API/ComfyUI/本地模型) | `prompt-engineering`(10段结构·甜点区·动作·实体推理)
  **功法要诀**: /skill load self-audit → 全自动诊断 → 修复 → 验证

## 青龙·工程宗 — 编码/调试/Shell (5技)
  `python-expert`      — Python全栈·类型安全·异步·测试
  `debug-master`       — 错误堆栈分析·性能瓶颈·内存泄漏
  `shell-master`       — Bash/Zsh/PowerShell 全能
  `api-designer`       — RESTful/GraphQL/gRPC 设计专家
  `code-review-autofix` — 代码审查→自动修复→验证通过
  **功法要诀**: 先读后写，探索优先，最小改动，改完自验

## 朱雀·品质宗 — 审查/品质/制片 (12技)
  **审查系**: `code-review`(代码审查) | `qc-inspector`(五维质量检查:视觉/文本/连续性/资产/交付) | `negative-prompt-rules`(拒绝约束+修复策略)
  **品质系**: `master-quality`(大师出品标准:文案对标编剧·图片对标摄影师·视频对标导演·音频对标声音设计)
  **制片系(9)**: `cinematic-master`(电影化提示词·镜头/光影/材质/情绪词汇库) | `cinematic-keyframe`(六层模板:世界/事件/摄影机/灯光/渲染/风格) | `storyboard-director`(简报→镜头列表→图像提示→运动→音频) | `motion-director`(摄像机运动·主体运动·节奏·连续性) | `visual-director`(视觉品味·参考·一致性·构图·灯光) | `prompt-director`(普通语言→提供商提示词+负面提示+验收标准) | `audio-director`(BGM场景·音效设计·旁白选型·混音标准) | `i2v-motion-rules`(一对一镜头规则·源帧连续性·运动幅度·闪烁检测) | `video-pipeline`(输入理解→资产拆解→独立生成→分镜融合→质检→导出)
  **功法要诀**: 任何输出先过自查镜，不确凿内容烧掉

## 玄武·守卫宗 — 安全/路由/交付 (4技)
  `security-hardening`  — 安全加固:依赖审计·密钥管理·攻击面扫描
  `model-routing`       — 模型路由矩阵:API/CLI/Web/手动回退四通道
  `asset-manager`       — 资产跟踪:源文件/参考/生成/外部/交付·清单维护
  `publishing-packager` — 平台发布:6大标题公式·封面规则·平台差异·复盘
  **功法要诀**: Schema版本化·运行时校验·双协议路径·向后兼容

## 麒麟·创造宗 — 视频/创意/文案/IP (18技)
  **视频制片(11)**: `showrunner` → `core-showrunner`(受控生产循环·诚实阻断·失败转修复) → `storyboard-director` → `script-writer`(电影/剧/短视频剧本) → `visual-director` → `motion-director` → `audio-director` → `cinematic-master` → `cinematic-keyframe` → `i2v-motion-rules` → `video-pipeline`
  **创意思维(6)**: `creative-engine`(跨域嫁接·四大创意域×反物理参数) | `creative-leap-pro`(14种创意思维法·SCAMPER/六顶帽/反模式) | `creative-thinking` | `world-building-engine`(六层模型·矛盾统一性) | `actor-craft`(5层角色设计·斯坦尼斯拉夫斯基) | `gaming-action-engine`(7步动作拆解·6阶段技能模型)
  **文案编剧(5)**: `copywriting-master`(全类型文案) | `novel-writer`(网文/短篇/中长篇) | `script-writer`(电影/电视剧/舞台剧) | `story-copywriter`(品牌/IP/产品故事) | `comic-drama-writer`(漫剧创作·红果/快看/腾讯动漫)
  **IP改编(1)**: `ip-adaptation-guard`(功能留下·表达重做·版权风险自检)
  **交付(1)**: `delivery-handoff`(编辑交付包:handoff.json/timeline.json/subtitles.srt)

## 杂学·工具宗 — 桥接/调度 (2技)
  `comfyui-bridge`      — ComfyUI全能桥接:29配方+12模式+自由编排+自创节点+LoRA炼制
  `delivery-handoff`    — 交付交接:生成编辑和交付交接包
"""

# Auto 技能的 prompt 片段（由 SkillManager.auto_skills_prompt() 注入，
# 此处仅为 AI 提供识别码，避免与 manager 重复注入）
WUJI_AUTO_SKILLS_NOTE = """
## 武技·自动激活 (auto-trigger)
  以下技能在会话启动时自动注入系统提示词（trigger=auto）：
  `coding-discipline`(rules), `self-preservation`(rules), `rendering`(rules)
  其余技能通过 `/skill load <name>` 手动激活。
"""


def get_wuji_prompt() -> str:
    """Return the full wuji spectrum prompt for system injection."""
    return WUJI_PROMPT


def get_wuji_summary() -> str:
    """Return a compact one-line summary of the wuji spectrum."""
    try:
        from pathlib import Path

        # Count from skills dir
        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        local = len(list(skills_dir.glob("*.skill.json"))) if skills_dir.exists() else 45
    except (OSError, RuntimeError):
        local = 45
    return f"[武技] {local}技 — 白虎·攻防(6) · 青龙·工程(5) · 朱雀·品质(12) · 玄武·守卫(4) · 麒麟·创造(18)"
