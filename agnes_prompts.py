"""
Agnes 提示词增强引擎 — 注入专业方法论到生图/生视频/对话。

提供:
  - 预设方法论模板（图片/视频/思维）
  - PromptEnhancer 类：自动检测类型并增强用户提示词
  - 独立增强函数：enhance_image_prompt / enhance_video_prompt
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


# ============================================================
# 方法论预设 — 图片生成
# ============================================================

IMAGE_METHODOLOGY = """
[视觉方法论]
1. 构图层次：主体(前景) > 陪体(中景) > 背景(远景)，建立清晰视觉层级
2. 光影语言：明确光源方向(侧光/逆光/顶光)、色温(冷/暖)、质感(柔/硬)
3. 色彩系统：主色调 + 辅助色 + 点缀色，避免超过5个主色
4. 风格锚定：指定明确的视觉风格参照（如：赛博朋克/水墨/印象派/超写实）
5. 细节密度：前景纹理丰富、中景结构清晰、背景简洁
6. 情绪设计：通过色调、构图、光影传达特定情感（压抑/希望/孤寂/温暖）
"""

IMAGE_STYLE_PRESETS = {
    "cinematic": """
[电影级风格]
- 宽银幕比例感，浅景深(bokeh)，胶片颗粒
- 三分法构图，引导线，负空间
- 色彩分级：青橙对比 / 蓝黄互补 / 低饱和高级灰
- 光源动机明确，画面有叙事感
""",
    "product": """
[产品级风格]
- 干净背景（纯色或极简），主体居中或三分
- 棚拍级布光：主光+辅光+轮廓光+背景光
- 材质表现优先：金属反光、玻璃透射、织物质感
- 色温中性偏冷（5500K），无偏色
""",
    "concept_art": """
[概念艺术风格]
- 史诗感构图，宏大场景或强烈人物姿态
- 氛围优先于细节，用光影建立空间深度
- 笔触可见，色彩大胆
- 构图留出 UI/文字空间（如果用于封面）
""",
    "anime": """
[动画风格]
- 干净轮廓线，扁平色彩区域
- 高饱和 + 柔和阴影（cel shading）
- 夸张透视/动态pose
- 日系/新海诚风：光影唯美 或 吉卜力风：手绘质感
""",
    "watercolor": """
[水彩风格]
- 湿画法：色彩自然晕染，边缘柔和
- 留白是构图元素，不是空白
- 颜色叠加透明感，笔触可见
- 纸张纹理可见
""",
    "cyberpunk": """
[赛博朋克风格]
- 霓虹光源（品红/青色/紫色），暗部蓝黑
- 湿地面反射光，烟雾/雨雾氛围
- 高对比度，剪影+发光边缘
- 东方元素混搭高科技（九龙城寨美学）
""",
    "fantasy": """
[奇幻风格]
- 史诗感，宏大场景或神秘森林/城堡
- 黄金时刻光线或魔法光源
- 色彩绚丽但不刺眼，有层次
- 细节丰富：植被、建筑纹理、服装质地
""",
    "portrait": """
[人像风格]
- 眼神光必备，眼睛是焦点
- 伦勃朗光 / 蝴蝶光 / 环形光
- 背景虚化(bokeh)，肤色自然
- 姿态自然，不僵硬
""",
}

IMAGE_NEGATIVE_PROMPTS = {
    "default": "blurry, low quality, distorted, deformed, ugly, bad anatomy, extra limbs, watermark, text, signature, cropped, out of frame",
    "portrait": "blurry face, distorted face, asymmetric eyes, bad anatomy, extra fingers, fused fingers, ugly, deformed, watermark",
    "product": "blurry, noise, grain, harsh shadows, reflections on product, watermark, text, logo, cluttered background",
    "architecture": "blurry, distorted perspective, people, cars, clutter, watermark, text",
}

# ============================================================
# 方法论预设 — 视频生成
# ============================================================

VIDEO_METHODOLOGY = """
[视频生成方法论]
1. 单一动作原则：每段视频只描述一个核心动作/事件，不要堆叠多个动作
2. 摄影机语言：
   - 固定镜头(static)：适合对话/凝视/氛围
   - 推轨(dolly in/out)：渐进揭示/疏离感
   - 横摇(pan L/R)：展示空间/跟随主体
   - 竖摇(tilt up/down)：揭示高度/力量关系
   - 跟拍(tracking)：保持主体居中跟随
   - 升格(slow motion)：情绪强调/细节展示
   - 降格(fast motion)：时间流逝/效率感
3. 三幕微结构：起始状态 → 变化发生 → 结束状态（即使是5秒视频）
4. 运动层次：主体动作 + 次级元素运动 + 环境氛围变化
5. 光影连续性：光源方向/色温/强度在视频全程保持一致
6. 时长感知：2s=一个眼神/一个动作, 3-4s=一个完整事件, 5-6s=有起承转合的场景
"""

VIDEO_STYLE_PRESETS = {
    "cinematic": """
[电影级视频]
- 电影级调色，浅景深
- 摄影机运动平稳克制，不花哨
- 注重光影变化和氛围
- 画面有叙事感和情绪张力
""",
    "commercial": """
[商业广告视频]
- 快节奏，干净利落的转场
- 产品始终是视觉焦点
- 色彩鲜艳饱和，高对比度
- 光影精致，无杂乱元素
""",
    "atmospheric": """
[氛围视频]
- 慢节奏，环境优先
- 光影缓慢变化（日出/日落/云过）
- 细微元素运动：树叶颤动、水面波纹、烟雾飘散
- 沉浸式体验，不强调主体动作
""",
    "dynamic": """
[动态视频]
- 快速运动，高能量
- 大幅度摄影机运动
- 粒子/碎片/流体效果
- 强烈的光影对比变化
""",
    "minimalist": """
[极简视频]
- 单色或有限色调
- 干净构图，大量负空间
- 极慢的、克制的运动
- 几何形体和光影互动
""",
}

VIDEO_CAMERA_GUIDE = """
[摄影机运动速查]
- 静态凝视: "static camera, locked off shot"
- 缓慢推进: "slow dolly in, camera slowly pushes forward"
- 缓慢拉远: "slow dolly out, camera slowly pulls back"
- 左摇: "slow pan left, camera rotates horizontally"
- 右摇: "slow pan right, camera sweeps across"
- 上摇: "tilt up, camera looks upward"
- 环绕: "orbital camera movement around subject"
- 手持感: "handheld camera, slight natural shake"
- 无人机: "drone shot, aerial perspective sweeping"
- 升格: "slow motion, 60fps captured, 24fps playback"
"""

# ============================================================
# 方法论预设 — 思维/对话
# ============================================================

CALIBER_METHODOLOGY = """
[Caliber 软件工程方法论]
任务分类 → 证据框架 → 三镜分析 → 高级工程师检查 → 自验证循环

任务分类：
- 架构决策: 对比方案、权衡、迁移风险、可逆性
- 调试/根因: 分离症状 → 触发条件 → 机制 → 修复
- 代码审查: 正确性、可靠性、安全性、可维护性、测试覆盖
- 重构: 保持行为不变 → 降低耦合 → 减少重复

三镜分析（每个方案从三个维度评估）：
1. 正确性 — 是否真正修复了故障？
2. 可维护性 — 6个月后初级工程师能理解吗？
3. 运行风险 — 爆炸半径、回滚安全性、状态损坏

自验证循环：
1. 我忽略了什么边界情况？
2. 什么隐藏依赖可能导致错误？
3. 有更简单的修复吗？
4. 我把症状和原因搞混了吗？
5. 我假设了未验证的 API 或行为吗？
"""

SUPERPOWERS_METHODOLOGY = """
[Superpowers 软件开发方法论]
核心理念：
- 测试驱动开发(TDD): 永远先写测试
- 系统化优于临时性: 按流程走，不凭猜测
- 降低复杂度: 简单是首要目标。DRY、YAGNI
- 证据优于声明: 先验证再宣布成功

强制7步工作流：
1. 头脑风暴 — 设计推敲，2-3种方案，硬性门禁
2. Git Worktree 隔离 — 新分支隔离工作
3. 编写计划 — 2-5分钟小任务，精确文件路径
4. 子代理驱动开发 — 并行分派
5. 实施 — 按计划精确执行
6. 评审 — 代码审查 + 测试验证
7. 合并 — 通过所有门禁后合并
"""

TDD_METHODOLOGY = """
[TDD 测试驱动开发]
核心理念：测试验证行为而非实现细节

好测试：通过公共接口验证行为，不关心内部结构
坏测试：耦合实现细节，模拟内部协作者

Mock 原则：
- 只在系统边界 mock（网络、文件系统、外部服务）
- 绝不 mock 内部协作者
- 真实实现优于 mock

循环：RED（写测试→确认失败）→ GREEN（最小代码→通过）→ REFACTOR
反模式：水平切片（先写所有测试再写所有实现）
正确做法：垂直切片（一次一个测试→实现→循环）
"""

FRONTEND_DESIGN_METHODOLOGY = """
[前端设计方法论]
设计令牌系统：4-6 个命名色值 + 2+ 字体角色 + 布局概念 + 标志性元素

色彩：避免 AI 生成设计的三大默认套路：
  (1) 暖奶油背景 + 高对比衬线 + 赤陶色点缀
  (2) 近黑背景 + 酸绿/朱红单色点缀
  (3) 报纸式布局 + 细线分割 + 零圆角

字体：展示字体（有性格但克制使用）+ 正文字体（互补）+ 工具字体（可选）
布局：hero 是论点，结构即信息，动效有意图

写作：从最终用户视角写，主动语态，失败/空状态是方向而非情绪
"""

CODING_DISCIPLINE = """
[编码纪律]
探索优先：定位 → 读现状 → 匹配约定 → 查证而非记忆
补丁优先于覆写：结构化补丁 > 单文件小改 > 绝不覆写核心模块
读后编：编辑前必读文件，不凭记忆猜测
三段式（复杂任务）：探索 → 计划 → 执行
"""

# ============================================================
# 提示词增强器
# ============================================================

class EnhanceMode(Enum):
    """增强模式"""
    APPEND = "append"        # 追加到提示词末尾
    PREPEND = "prepend"      # 插入到提示词开头
    REPLACE = "replace"      # 完全替换（用增强后的提示词）


@dataclass
class PromptEnhancer:
    """提示词增强器 — 注入方法论到用户提示词
    
    用法:
        enhancer = PromptEnhancer()
        enhanced = enhancer.enhance_image("一只猫")
        enhanced = enhancer.enhance_video("海浪拍打岩石")
    """
    
    mode: EnhanceMode = EnhanceMode.APPEND
    image_methodology: bool = True
    image_style: str | None = None          # cinematic/product/concept_art/anime/...
    image_negative: str | None = "default"  # 预设名称或自定义否定提示词
    video_methodology: bool = True
    video_style: str | None = None          # cinematic/commercial/atmospheric/...
    video_camera: str | None = None         # static/dolly_in/dolly_out/pan_left/...
    chat_methodology: bool = True
    
    # 自定义注入
    custom_prepend: str = ""
    custom_append: str = ""
    
    def enhance_image(self, prompt: str, style: str | None = None) -> str:
        """增强图片生成提示词"""
        parts = []
        
        if self.custom_prepend:
            parts.append(self.custom_prepend)
        
        parts.append(prompt)
        
        # 风格注入
        style_name = style or self.image_style
        if style_name and style_name in IMAGE_STYLE_PRESETS:
            parts.append(IMAGE_STYLE_PRESETS[style_name])
        
        # 通用方法论
        if self.image_methodology:
            parts.append(IMAGE_METHODOLOGY)
        
        if self.custom_append:
            parts.append(self.custom_append)
        
        return "\n\n".join(parts)
    
    def enhance_video(
        self, prompt: str, 
        style: str | None = None, 
        camera: str | None = None
    ) -> str:
        """增强视频生成提示词"""
        parts = []
        
        if self.custom_prepend:
            parts.append(self.custom_prepend)
        
        parts.append(prompt)
        
        # 风格注入
        style_name = style or self.video_style
        if style_name and style_name in VIDEO_STYLE_PRESETS:
            parts.append(VIDEO_STYLE_PRESETS[style_name])
        
        # 摄影机运动
        camera_name = camera or self.video_camera
        if camera_name:
            parts.append(f"[摄影机运动] {camera_name}")
        
        # 通用方法论
        if self.video_methodology:
            parts.append(VIDEO_METHODOLOGY)
        
        if self.custom_append:
            parts.append(self.custom_append)
        
        return "\n\n".join(parts)
    
    def enhance_chat(self, prompt: str) -> str:
        """增强对话提示词（注入方法论）"""
        if not self.chat_methodology:
            return prompt
        
        return f"""{prompt}

---
[方法论注入]
{CALIBER_METHODOLOGY}

{CODING_DISCIPLINE}
"""
    
    def get_negative_prompt(self, style: str | None = None) -> str:
        """获取否定提示词"""
        key = style or self.image_negative or "default"
        if key in IMAGE_NEGATIVE_PROMPTS:
            return IMAGE_NEGATIVE_PROMPTS[key]
        return key  # 可能是自定义文本


# ============================================================
# 便捷函数
# ============================================================

_default_enhancer = PromptEnhancer()


def enhance_image_prompt(
    prompt: str, 
    style: str | None = None,
    methodology: bool = True,
) -> str:
    """增强图片生成提示词（便捷函数）"""
    enhancer = PromptEnhancer(
        image_methodology=methodology,
        image_style=style,
    )
    return enhancer.enhance_image(prompt)


def enhance_video_prompt(
    prompt: str,
    style: str | None = None,
    camera: str | None = None,
    methodology: bool = True,
) -> str:
    """增强视频生成提示词（便捷函数）"""
    enhancer = PromptEnhancer(
        video_methodology=methodology,
        video_style=style,
        video_camera=camera,
    )
    return enhancer.enhance_video(prompt)


def get_style_list() -> dict[str, list[str]]:
    """列出所有可用风格"""
    return {
        "image_styles": list(IMAGE_STYLE_PRESETS.keys()),
        "video_styles": list(VIDEO_STYLE_PRESETS.keys()),
        "camera_movements": [
            "static", "dolly_in", "dolly_out", "pan_left", "pan_right",
            "tilt_up", "orbital", "handheld", "drone", "slow_motion"
        ],
        "negative_styles": list(IMAGE_NEGATIVE_PROMPTS.keys()),
    }


# ============================================================
# 系统提示词模板（用于 chat_text）
# ============================================================

SYSTEM_PROMPTS = {
    "caliber_engineer": f"""你正在运行 CALIBER 软件工程方法论。{CALIBER_METHODOLOGY}""",
    
    "tdd_master": f"""你是 TDD 专家。{TDD_METHODOLOGY}""",
    
    "frontend_designer": f"""你是前端设计专家。{FRONTEND_DESIGN_METHODOLOGY}""",
    
    "image_artist": f"""你是视觉艺术总监。{IMAGE_METHODOLOGY}""",
    
    "video_director": f"""你是视频导演。{VIDEO_METHODOLOGY}""",
    
    "fullstack_dev": f"""你是全栈开发专家。{CODING_DISCIPLINE}{SUPERPOWERS_METHODOLOGY}""",
}
