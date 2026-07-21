"""
ShotContract — 镜头合同编译器

将用户需求编译成强制"一镜一动作"的结构化镜头合同。
防止 AI 生成多动作/多场景的混乱视频。

Usage:
    contract = ShotContract.compile("一条龙在天空飞翔，然后俯冲到水面，再飞向太阳")
    # → 拆成 3 个独立合同，每个一镜一动作

    contract = ShotContract.compile("夕阳下的沙滩，海浪轻轻拍打")
    # → 1 个合同，提取核心要素

    contract = ShotContract.compile(prompt, image_url="https://...")
    # → 图生视频合同
"""

import logging
import re
from dataclasses import asdict, dataclass, field

logger = logging.getLogger(__name__)

# 动作分隔词（用于检测多动作）
ACTION_SPLITTERS = re.compile(
    r"(然后|接着|随后|之后|再|又|最后|接下来|紧接着|突然|转而"
    r"|then |then,|and then|after that|next |finally |subsequently"
    r"|followed by|before |while |as he|as she|as it)",
    re.UNICODE | re.IGNORECASE,
)

CAMERA_MOTIONS = frozenset(
    {
        "推",
        "拉",
        "摇",
        "移",
        "跟",
        "升",
        "降",
        "dolly",
        "track",
        "pan",
        "tilt",
        "crane",
        "aerial",
        "推近",
        "拉远",
        "上摇",
        "下摇",
        "横移",
        "跟拍",
        "dolly in",
        "dolly out",
        "track left",
        "track right",
        "pan left",
        "pan right",
        "tilt up",
        "tilt down",
        "crane up",
        "crane down",
        "aerial shot",
        "drone shot",
        "稳定",
        "固定",
        "手持",
        "斯坦尼康",
        "static",
        "handheld",
        "steadicam",
        "locked off",
    }
)

VALID_STYLES = frozenset(
    {
        "cinematic",
        "realistic",
        "anime",
        "watercolor",
        "cyberpunk",
        "fantasy",
        "oil painting",
        "3d render",
        "pixel art",
        "水墨",
        "油画",
        "赛博朋克",
        "科幻",
        "写实",
        "卡通",
    }
)

VALID_ASPECT_RATIOS = frozenset({"16:9", "9:16", "1:1", "4:3", "3:2", "21:9"})


@dataclass
class ShotContract:
    """一镜一动作的镜头合同"""

    shot_id: str = ""
    prompt: str = ""  # 原始 prompt
    optimized_prompt: str = ""  # 结构化后的 prompt

    # 核心要素（各必须只有一个）
    subject: str = ""  # 主体
    action: str = ""  # 动作（一个！）
    scene: str = ""  # 场景/环境
    camera_motion: str = ""  # 运镜（一个！）
    lighting: str = ""  # 光线
    style: str = ""  # 风格

    # 技术参数
    aspect_ratio: str = "16:9"
    duration_seconds: float = 3.4  # 81/24 ≈ 3.4秒
    num_frames: int = 81
    frame_rate: int = 24
    seed: int | None = None

    # 图生视频
    image_url: str | None = None
    image_urls: list[str] | None = None

    # 质量控制
    keep_stable: list[str] = field(
        default_factory=lambda: [
            "主体位置",
            "构图比例",
            "风格一致性",
        ]
    )
    negative_prompt: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_video_prompt(self) -> str:
        """编译成 Agnes Video 推荐结构：
        [主体] + [动作] + [场景] + [镜头运动] + [光线] + [风格]
        """
        parts = []
        if self.subject:
            parts.append(self.subject)
        if self.action:
            parts.append(self.action)
        if self.scene:
            parts.append(self.scene)
        if self.camera_motion:
            parts.append(self.camera_motion)
        if self.lighting:
            parts.append(self.lighting)
        if self.style:
            parts.append(self.style)

        result = ", ".join(parts)
        if self.keep_stable:
            result += f", keep stable: {', '.join(self.keep_stable)}"
        return result


class ShotCompiler:
    """镜头编译器 — 分析 prompt 并编译为 ShotContract"""

    @classmethod
    def compile(cls, prompt: str, **kwargs) -> list[ShotContract]:
        """
        编译 prompt 为一个或多个 ShotContract（多动作时拆成多个）。

        返回:
            [ShotContract, ...]  # 必有一镜
        """
        # Step 1: 检测多动作
        shots = cls._split_multi_action(prompt)

        # Step 2: 每个镜头提取要素
        contracts = []
        for i, shot_prompt in enumerate(shots):
            contract = cls._extract_single(shot_prompt, **kwargs)
            contract.shot_id = f"shot_{i + 1:03d}"
            contracts.append(contract)

        if not contracts:
            contracts.append(cls._extract_single(prompt, **kwargs))
            contracts[0].shot_id = "shot_001"

        return contracts

    @classmethod
    def _split_multi_action(cls, prompt: str) -> list[str]:
        """按动作分隔词拆分为多个单动作镜头"""
        parts = ACTION_SPLITTERS.split(prompt)

        # 合并：分隔词作为分割点，前后分成不同镜头
        result = []
        buf = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # 如果是分隔词且当前有内容，则截断
            if ACTION_SPLITTERS.match(part) and part.strip() in [
                s.strip()
                for s in [
                    "然后",
                    "接着",
                    "随后",
                    "之后",
                    "再",
                    "又",
                    "最后",
                    "接下来",
                    "紧接着",
                    "突然",
                    "转而",
                    "then",
                    "and then",
                    "after that",
                    "next",
                    "finally",
                    "subsequently",
                    "followed by",
                    "before",
                    "while",
                ]
            ]:
                if buf:
                    result.append(buf)
                    buf = ""
                continue
            if buf:
                buf += " " + part
            else:
                buf = part

        if buf:
            result.append(buf)

        # 单镜头场景直接返回原始 prompt
        if len(result) <= 1:
            return [prompt]

        logger.info("多动作检测: %d 个镜头 -> %s", len(result), result)
        return result

    @classmethod
    def _extract_single(cls, prompt: str, **kwargs) -> ShotContract:
        """从单动作 prompt 中提取要素"""
        contract = ShotContract(prompt=prompt)

        # 提取风格
        for style in VALID_STYLES:
            if style in prompt.lower():
                contract.style = style
                break

        # 提取运镜
        for motion in CAMERA_MOTIONS:
            if motion in prompt.lower():
                contract.camera_motion = motion
                break

        # 提取光照
        lighting_keywords = {
            "sunset": "暖色夕阳",
            "golden hour": "金色时刻",
            "sunrise": "晨光",
            "night": "夜景",
            "dark": "暗调",
            "moody": "氛围光",
            "cinematic lighting": "电影布光",
            "soft light": "柔光",
            "hard light": "硬光",
            "背光": "逆光",
            "侧光": "侧光",
            "顶光": "顶光",
            "暖色": "暖色调",
            "冷色": "冷色调",
        }
        for kw, val in lighting_keywords.items():
            if kw in prompt.lower():
                contract.lighting = val
                break

        if not contract.lighting:
            contract.lighting = "自然光"

        # 提取场景
        scene_keywords = [
            "beach",
            "ocean",
            "mountain",
            "forest",
            "city",
            "street",
            "space",
            "desert",
            "snow",
            "river",
            "lake",
            "garden",
            "temple",
            "castle",
            "room",
            "hall",
            "market",
            "bridge",
            "海滩",
            "海",
            "山",
            "森林",
            "城市",
            "街道",
            "太空",
            "沙漠",
            "雪",
            "河",
            "湖",
            "花园",
            "寺",
            "城堡",
            "房间",
            "大厅",
            "市场",
            "桥",
        ]
        for scene in scene_keywords:
            if scene in prompt.lower():
                contract.scene = scene
                break

        if not contract.scene:
            # 尝试提取最后一个能作为场景的词
            contract.scene = prompt[:30]

        # 取前 N 个字作为主体（简化版）
        words = re.split(r"[,，]", prompt)
        if words:
            contract.subject = words[0].strip()[:50]

        # 提取动作
        action_keywords = [
            "flying",
            "running",
            "walking",
            "swimming",
            "dancing",
            "jumping",
            "sitting",
            "lying",
            "standing",
            "floating",
            "driving",
            "riding",
            "climbing",
            "falling",
            "turning",
            "飞",
            "跑",
            "走",
            "跳",
            "游",
            "舞",
            "坐",
            "躺",
            "站",
            "浮",
            "开",
            "骑",
            "爬升",
            "坠落",
            "转弯",
        ]
        for action in action_keywords:
            if action in prompt.lower():
                contract.action = action
                break

        if not contract.action:
            contract.action = "静止"
            contract.keep_stable.append("无大幅度动作")

        # 应用外部参数
        for k, v in kwargs.items():
            if hasattr(contract, k) and v is not None:
                setattr(contract, k, v)

        # 生成优化后的 prompt
        contract.optimized_prompt = contract.to_video_prompt()

        return contract


# 便捷函数
def compile_shot(prompt: str, **kwargs) -> ShotContract:
    """编译为单镜头合同（自动处理多动作场景）"""
    contracts = ShotCompiler.compile(prompt, **kwargs)
    if len(contracts) > 1:
        logger.warning("检测到 %d 个动作，自动取首镜", len(contracts))
    return contracts[0]


def validate_single_action(prompt: str) -> tuple[bool, str]:
    """
    校验是否为一镜一动作。

    返回:
        (is_valid, message)
    """
    contracts = ShotCompiler.compile(prompt)
    if len(contracts) > 1:
        msg = f"检测到 {len(contracts)} 个动作，请拆分为独立镜头："
        for c in contracts:
            msg += f"\n  - {c.action}: {c.subject} ({c.prompt[:40]}...)"
        return False, msg
    return True, "✅ 一镜一动作"
