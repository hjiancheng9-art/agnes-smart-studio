"""智能大脑 - 意图识别、Prompt增强、分镜生成"""

import json

import httpx

from .async_client import AsyncCruxClient
from .brain_data import (
    BEAUTY_PORTRAIT_MAP,
    ENHANCE_IMAGE_PROMPT,
    ENHANCE_VIDEO_PROMPT,
    ENTITY_TYPE_MAP,
    INTENT_PROMPT,
)
from .client import CruxClient

__all__ = ["SmartBrain", "AsyncSmartBrain"]



# ── Mixin imports ──
from core.brain_aesthetics import SmartBrainMixin as AestheticsMixin
from core.brain_combat import SmartBrainMixin as CombatMixin
from core.brain_creative import SmartBrainMixin as CreativeMixin
from core.brain_vision import SmartBrainMixin as VisionMixin


class SmartBrain(CombatMixin, CreativeMixin, AestheticsMixin, VisionMixin):
    """智能大脑：意图识别 + Prompt增强 + 分镜生成"""

    def __init__(self, client: CruxClient) -> None:
        self.client = client

    def _ask_brain(self, system_prompt: str, user_input: str, temperature: float = 0.7) -> str:
        """调用文本模型（自动使用当前激活的供应商）。

        若当前供应商调用失败（HTTP 错误等），自动降级到 CRUX light
        模型（agnes-2.0-flash），保证 prompt 增强不阻断主流程。
        """
        model = self._get_model()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        try:
            from core.provider_adapter import get_max_tokens as _gmt
            result = self.client.chat(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=_gmt(model),
            )
        except (httpx.HTTPError, OSError) as primary_err:
            # 当前供应商失败（网络/HTTP 错误）→ 降级到 CRUX light 模型。
            # 注意：收窄到 httpx/OSError，避免把编程 bug（AttributeError 等）
            # 当作"供应商故障"去降级，从而掩盖真实问题。
            # 降级块自包含：空 key 或降级上游同故障时，抛原始异常，
            # 由调用方（chat.py 已有 try/except 退化原始 prompt）兜底。
            from core.client import CruxClient
            from core.config import CRUX_VISION_BASE_URL

            crux_key = ""
            try:
                from core.provider import get_provider_manager

                mgr = get_provider_manager()
                crux_p = mgr.providers.get("crux", {})
                crux_key = crux_p.get("api_key") or ""
            except (ImportError, OSError):
                pass
            if not crux_key:
                import os

                crux_key = os.getenv("CRUX_API_KEY", "") or os.getenv("AGNES_API_KEY", "")
            try:
                if not crux_key:
                    raise RuntimeError("CRUX fallback api_key missing") from primary_err
                fallback = CruxClient(api_key=crux_key, base_url=CRUX_VISION_BASE_URL)
                result = fallback.chat(
                    model="agnes-2.0-flash",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=2048,
                )
            except (httpx.HTTPError, OSError, RuntimeError) as fallback_err:
                # 降级链本身也失败 → 抛原始异常（primary_err 才是根因），
                # 同时把降级链失败作为 __context__ 保留，便于排查二次故障。
                # 切勿 `raise primary_err from primary_err`：那会把异常自身设成
                # __cause__，因果链语义错乱（"自己是自己的原因"）。
                raise primary_err from fallback_err
        try:
            msg = result["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content")
        except (KeyError, IndexError):
            raise RuntimeError(f"Brain API返回格式异常: {str(result)[:200]}") from None
        if not content:
            raise RuntimeError(f"Brain 返回内容为空: {str(result)[:300]}")
        # 尝试提取JSON（可能被包裹在```json中）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return content

    def _get_model(self) -> str:
        """获取当前激活供应商的模型 ID。
        Prompt 增强是文本改写任务，用 light 模型即可，不需要 Pro。
        """
        try:
            from core.provider import get_provider_manager

            mgr = get_provider_manager()
            return mgr.get_model("light") or mgr.get_model("pro")
        except (OSError, ValueError, RuntimeError):
            return "agnes-2.0-flash"  # fallback

    def _parse_json(self, text: str) -> dict:
        """安全解析JSON"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试找到JSON部分
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return {"raw_text": text}

    def recognize_intent(self, user_input: str) -> dict:
        """识别用户意图"""
        text = self._ask_brain(INTENT_PROMPT, user_input, temperature=0.3)
        result = self._parse_json(text)
        # 确保必要字段存在
        result.setdefault("intent", "text_to_image")
        result.setdefault("confidence", 0.5)
        result.setdefault("plan", user_input)
        result.setdefault("has_image_input", False)
        result.setdefault("wants_video", False)
        result.setdefault("wants_editing", False)
        return result

    def enhance_image_prompt(self, user_prompt: str, style: str | None = None) -> dict:
        """增强图片生成Prompt，自动匹配甜点区模板 + 实体感知 + 帅哥美女通道 + 战斗知识 + 风险预判"""
        # 推断实体类型
        entity_type, surface_policy = self._infer_entity_type(user_prompt)

        # 推断帅哥美女类型
        beauty_type = self._infer_beauty_type(user_prompt)  # pyright: ignore[reportCallIssue]

        # 检测战斗场景
        combat_ctx = self._detect_combat_scene(user_prompt, "image")

        # 构建LLM输入
        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (
                f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                f"表面策略：{surface_policy}]\n原始描述：{user_prompt}"
            )
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            angle_rules_str = "\n".join(f"  {angle}: {rule}" for angle, rule in beauty_info["angle_rules"].items())
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[多角度规则：\n{angle_rules_str}]\n"
                f"[可用气质：{', '.join(beauty_info['aura_options'])}]\n"
                f"[禁止：模板脸、空泛形容词、出招姿势、硬摆拍、夸张武打体态]\n"
                f"原始描述：{user_prompt}"
            )
        # 战斗场景注入（优先级低于实体/美女，高于通用）
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['image_prompt_hints']}\n原始描述：{user_prompt}"

        # 创意知识注入（CREATIVE_DOMAIN_MAP/ANTI_PATTERN_MAP/THINKING_METHOD_MAP 激活）
        # 仅对通用场景（非战斗、非美女）注入跨域参考元素，为LLM提供更多灵感
        if not combat_ctx and not beauty_type:
            creative_ctx = self._resolve_creative_knowledge(user_prompt, "image")  # pyright: ignore[reportArgumentType]
            if creative_ctx and creative_ctx.get("image_prompt_hints"):
                input_text = f"{creative_ctx['image_prompt_hints']}\n原始描述：{input_text}"

        if style:
            input_text = f"风格要求：{style}\n{input_text}"

        # 注入历史成功案例，让增强器持续进化
        try:
            from utils.memory import build_evolution_context

            evo_ctx = build_evolution_context("image")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except (OSError, ValueError, RuntimeError):
            pass

        text = self._ask_brain(ENHANCE_IMAGE_PROMPT, input_text)
        return self._postprocess_image_enhance(user_prompt, text, entity_type, surface_policy, beauty_type, combat_ctx)


    def enhance_video_prompt(self, user_prompt: str) -> dict:
        """增强视频生成Prompt，自动匹配甜点区模板 + 实体感知 + 帅哥美女通道 + 战斗知识 + 风险预判"""
        # 推断实体类型
        entity_type, surface_policy = self._infer_entity_type(user_prompt)

        # 推断帅哥美女类型
        beauty_type = self._infer_beauty_type(user_prompt)  # pyright: ignore[reportCallIssue]

        # 检测战斗场景
        combat_ctx = self._detect_combat_scene(user_prompt, "video")

        # 构建LLM输入
        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (
                f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                f"表面策略：{surface_policy}]\n原始描述：{user_prompt}"
            )
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[视频生产路由：逐镜 compact，I2V strength 0.70-0.72]\n"
                f"[允许动作：眼神、呼吸、轻微转头、整理衣领]\n"
                f"[禁止：出招姿势、硬摆拍、夸张武打体态、多镜头切换]\n"
                f"原始描述：{user_prompt}"
            )
        # 战斗场景注入（优先级低于实体/美女，高于通用）
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['video_prompt_hints']}\n原始描述：{user_prompt}"

        # 非人实体视频规则注入（NONHUMAN_VIDEO_RULES 知识激活）
        if entity_type and not beauty_type:
            creative_ctx = self._resolve_creative_knowledge(user_prompt, "video")  # pyright: ignore[reportArgumentType]
            if creative_ctx and creative_ctx.get("nonhuman_video_ctx"):
                i2v = creative_ctx["nonhuman_video_ctx"]["i2v_first_frame"]
                specs = creative_ctx["nonhuman_video_ctx"]["sweet_spot_specs"]
                pipeline = creative_ctx["nonhuman_video_ctx"]["prompt_assembly_pipeline"]
                nonhuman_video_hints = (
                    f"[非人实体视频规则]\n"
                    f"I2V首帧限制：{i2v['max_allowed']}\n"
                    f"适合动作：{', '.join(i2v['suitable_actions'][:4])}\n"
                    f"不适合动作：{', '.join(i2v['unsuitable_actions'][:4])}\n"
                    f"设计锁定：{i2v['design_lock_template']}\n"
                    f"甜点区方法：{specs['default_method']}，禁止：{', '.join(specs['forbidden'])}\n"
                    f"组装流水线：{' → '.join(pipeline['steps'])}"
                )
                input_text = f"{nonhuman_video_hints}\n原始描述：{input_text}"

        # 注入历史成功案例，让视频增强也持续进化
        try:
            from utils.memory import build_evolution_context

            evo_ctx = build_evolution_context("video")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except (OSError, RuntimeError, ConnectionError):
            pass

        text = self._ask_brain(ENHANCE_VIDEO_PROMPT, input_text)
        return self._postprocess_video_enhance(user_prompt, text, entity_type, surface_policy, beauty_type, combat_ctx)


    def understand_image(self, question: str, image_url: str) -> str:
        """利用视觉模型理解图片（供应商感知）。"""
        from core.config import get_crux_vision_model
        from core.provider_adapter import get_max_tokens as _gmt
        model = get_crux_vision_model()
        result = self.client.chat_multimodal(
            text=question,
            image_url=image_url,
            model=model,
            temperature=0.3,
            max_tokens=_gmt(model),
        )
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"多模态API返回格式异常: {str(result)[:200]}") from None


class AsyncSmartBrain:
    """AsyncSmartBrain：SmartBrain 的 asyncio 原生异步对应物。

    复用 SmartBrain 的全部知识库与逻辑（通过组合持有同步 SmartBrain 实例），
    仅将涉及网络 I/O 的方法（_ask_brain / enhance_*_prompt / understand_image）
    重写为 async 版本，使用 AsyncCruxClient。

    所有纯计算逻辑（_infer_entity_type / _match_sweet_spot / _predict_risks 等）
    直接委托给内部的同步 SmartBrain，无需重复实现。
    """

    def __init__(self, client: AsyncCruxClient) -> None:
        self.client = client
        # 持有同步 SmartBrain 以复用全部纯计算逻辑（这些方法不触发 I/O）
        # 传入一个 dummy sync client（不会被调用，因为只复用计算方法）
        self._sync = SmartBrain(client=client)  # type: ignore[arg-type]

    async def _ask_brain(self, system_prompt: str, user_input: str, temperature: float = 0.7) -> str:
        """异步调用文本模型（自动使用当前激活的供应商）"""
        model = self._sync._get_model()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        result = await self.client.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=2048,
        )
        try:
            msg = result["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content")
        except (KeyError, IndexError):
            raise RuntimeError(f"Brain API返回格式异常: {str(result)[:200]}") from None
        if not content:
            raise RuntimeError(f"Brain 返回内容为空: {str(result)[:300]}")
        # 尝试提取JSON（可能被包裹在```json中）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return content

    async def enhance_image_prompt(self, user_prompt: str, style: str | None = None) -> dict:
        """异步增强图片生成 Prompt。

        复用 SmartBrain.enhance_image_prompt 的全部逻辑，仅将唯一的 I/O 点
        （self._ask_brain 调用）替换为 async 版本。通过 monkey-patch 临时
        将同步 _ask_brain 替换为 async 版本不可行（同步代码无法 await），
        因此采用"复制逻辑 + 替换 I/O 调用"策略，保持与同步版完全一致的业务逻辑。
        """
        # 委托计算部分给同步 SmartBrain（构建 input_text），仅 I/O 异步化
        sync = self._sync

        entity_type, surface_policy = sync._infer_entity_type(user_prompt)
        beauty_type = sync._infer_beauty_type(user_prompt)  # pyright: ignore[reportCallIssue]
        combat_ctx = sync._detect_combat_scene(user_prompt, "image")

        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (
                f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                f"表面策略：{surface_policy}]\n原始描述：{user_prompt}"
            )
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            angle_rules_str = "\n".join(f"  {angle}: {rule}" for angle, rule in beauty_info["angle_rules"].items())
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[多角度规则：\n{angle_rules_str}]\n"
                f"[可用气质：{', '.join(beauty_info['aura_options'])}]\n"
                f"[禁止：模板脸、空泛形容词、出招姿势、硬摆拍、夸张武打体态]\n"
                f"原始描述：{user_prompt}"
            )
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['image_prompt_hints']}\n原始描述：{user_prompt}"
        if not combat_ctx and not beauty_type:
            creative_ctx = sync._resolve_creative_knowledge(user_prompt, "image")  # pyright: ignore[reportArgumentType]
            if creative_ctx and creative_ctx.get("image_prompt_hints"):
                input_text = f"{creative_ctx['image_prompt_hints']}\n原始描述：{input_text}"
        if style:
            input_text = f"风格要求：{style}\n{input_text}"

        try:
            from utils.memory import build_evolution_context

            evo_ctx = build_evolution_context("image")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except (OSError, ValueError, RuntimeError):
            pass

        # ── 唯一的异步 I/O 点 ──
        text = await self._ask_brain(ENHANCE_IMAGE_PROMPT, input_text)
        # ── 后续逻辑全部是纯计算，委托给同步 SmartBrain 的后处理 ──
        return sync._postprocess_image_enhance(user_prompt, text, entity_type, surface_policy, beauty_type, combat_ctx)

    async def enhance_video_prompt(self, user_prompt: str) -> dict:
        """异步增强视频生成 Prompt。逻辑同 enhance_image_prompt。"""
        sync = self._sync

        entity_type, surface_policy = sync._infer_entity_type(user_prompt)
        beauty_type = sync._infer_beauty_type(user_prompt)  # pyright: ignore[reportCallIssue]
        combat_ctx = sync._detect_combat_scene(user_prompt, "video")

        input_text = user_prompt
        if entity_type:
            entity_info = ENTITY_TYPE_MAP[entity_type]
            input_text = (
                f"[实体类型：{entity_info['name_cn']}({entity_type}) — "
                f"表面策略：{surface_policy}]\n原始描述：{user_prompt}"
            )
        elif beauty_type:
            beauty_info = BEAUTY_PORTRAIT_MAP[beauty_type]
            input_text = (
                f"[人像通道：{beauty_info['name_cn']} — 独立人像通道，不混入非人/战斗/怪诞逻辑]\n"
                f"[重点描写：{beauty_info['focus_points']}]\n"
                f"[视频生产路由：逐镜 compact，I2V strength 0.70-0.72]\n"
                f"[允许动作：眼神、呼吸、轻微转头、整理衣领]\n"
                f"[禁止：出招姿势、硬摆拍、夸张武打体态、多镜头切换]\n"
                f"原始描述：{user_prompt}"
            )
        if combat_ctx and not beauty_type:
            input_text = f"{combat_ctx['video_prompt_hints']}\n原始描述：{user_prompt}"
        if entity_type and not beauty_type:
            creative_ctx = sync._resolve_creative_knowledge(user_prompt, "video")  # pyright: ignore[reportArgumentType]
            if creative_ctx and creative_ctx.get("nonhuman_video_ctx"):
                i2v = creative_ctx["nonhuman_video_ctx"]["i2v_first_frame"]
                specs = creative_ctx["nonhuman_video_ctx"]["sweet_spot_specs"]
                pipeline = creative_ctx["nonhuman_video_ctx"]["prompt_assembly_pipeline"]
                nonhuman_video_hints = (
                    f"[非人实体视频规则]\n"
                    f"I2V首帧限制：{i2v['max_allowed']}\n"
                    f"适合动作：{', '.join(i2v['suitable_actions'][:4])}\n"
                    f"不适合动作：{', '.join(i2v['unsuitable_actions'][:4])}\n"
                    f"设计锁定：{i2v['design_lock_template']}\n"
                    f"甜点区方法：{specs['default_method']}，禁止：{', '.join(specs['forbidden'])}\n"
                    f"组装流水线：{' → '.join(pipeline['steps'])}"
                )
                input_text = f"{nonhuman_video_hints}\n原始描述：{input_text}"

        try:
            from utils.memory import build_evolution_context

            evo_ctx = build_evolution_context("video")
            if evo_ctx:
                input_text = f"{evo_ctx}\n\n{input_text}"
        except (OSError, RuntimeError, ConnectionError):
            pass

        # ── 唯一的异步 I/O 点 ──
        text = await self._ask_brain(ENHANCE_VIDEO_PROMPT, input_text)
        return sync._postprocess_video_enhance(user_prompt, text, entity_type, surface_policy, beauty_type, combat_ctx)

    async def understand_image(self, question: str, image_url: str) -> str:
        """异步利用多模态能力理解图片"""
        result = await self.client.chat_multimodal(
            text=question,
            image_url=image_url,
            model="agnes-2.0-flash",
            temperature=0.3,
            max_tokens=1024,
        )
        try:
            return result["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise RuntimeError(f"多模态API返回格式异常: {str(result)[:200]}") from None
