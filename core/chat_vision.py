"""Vision fallback chain — extracted from chat.py."""

from __future__ import annotations

import contextlib
import logging

import httpx

from core.observability import metrics

logger = logging.getLogger("crux.vision")

def _vision_fallback(self, text: str, image_url: str) -> str:
    """视觉理解调用 + fallback 链（供应商质量优先，CRUX > 智谱）。

    依次尝试 _vision_model_chain(complexity) 中的模型，首个成功即返回；
    全部失败时返回包含尝试列表的人类可读错误（不抛异常，保证流式不中断）。

    失败原因分类：
    - KeyError/IndexError: 返回 JSON 结构异常（供应商换了 schema）
    - OSError/TimeoutError: 网络/超时（最常见，触发下一档 fallback）
    - RuntimeError: 供应商上游错误
    """
    # Vision 复杂度分级：light → 2048 tokens + light tier 首选；
    #                  complex → 4096 tokens + pro tier 首选 + 推理引导
    complexity, max_tok = self._classify_vision_complexity(text)
    chain = self._vision_model_chain(complexity)
    tried: list[str] = []
    last_reason = ""
    vision_text = text
    if complexity == "complex":
        # 注入逐步推理引导（不修改用户原始文本，只影响 API 调用）
        vision_text = f"请仔细观察图片，逐步推理分析：\n{text}"
    for model_id in chain:
        tried.append(model_id)
        # 503 瞬时故障：同模型最多重试 2 次 (backoff 1s/4s)
        retry_503 = 0
        while True:
            try:
                # Use provider-aware client: route to correct API endpoint
                vc = self.vision_client
                model_lower = model_id.lower()
                if model_lower.startswith("glm-") or model_lower.startswith("cog"):
                    try:
                        from core.provider import get_provider_manager
                        mgr = get_provider_manager()
                        vc = mgr.create_client("zhipu")
                    except (ImportError, RuntimeError, OSError) as e:
                        last_reason = f"智谱客户端创建失败: {e}"
                        logger.warning("zhipu client creation failed for model %s: %s", model_id, e)
                        break  # skip this model, try next in chain
                elif model_lower.startswith("agnes-"):
                    # CRUX/Agnes vision models must route to CRUX API, not main client
                    try:
                        from core.provider import get_provider_manager
                        mgr = get_provider_manager()
                        vc = mgr.create_client("crux")
                    except (ImportError, RuntimeError, OSError) as e:
                        last_reason = f"CRUX客户端创建失败: {e}"
                        logger.warning("crux client creation failed for model %s: %s", model_id, e)
                        break
                r = vc.chat_multimodal(
                    text=vision_text,
                    image_url=image_url,
                    model=model_id,
                    max_tokens=max_tok,
                )
                content = r["choices"][0]["message"]["content"] or ""
                # #6 成本追踪：视觉调用按 token 计费（text kind），usage 来自 API 返回
                try:
                    from core.cost_tracker import record_usage

                    record_usage(model=model_id, kind="text", usage=r.get("usage"), label="vision")
                except (ImportError, OSError, KeyError, TypeError) as e:
                    logger.debug("cost_tracker.record_usage(vision) failed: %s: %s", type(e).__name__, e)
                return content
            except httpx.HTTPStatusError as e:
                last_reason = f"HTTP {e.response.status_code}: {e}"
                logger.warning("vision model %s returned HTTP %s", model_id, e.response.status_code)
                metrics.increment("fallback.vision_model")
                # 503: 瞬时故障 → 重试同模型（最多 2 次，backoff 1s/4s）
                if e.response.status_code == 503 and retry_503 < 2:
                    retry_503 += 1
                    import time as _time
                    _time.sleep(retry_503 * retry_503)
                    continue  # retry same model
                break  # 非 503 或重试耗尽 → 下一个模型
            except (KeyError, IndexError) as e:
                last_reason = f"返回格式异常: {e}"
                _r_usage = None
                with contextlib.suppress(NameError):
                    _r_usage = r.get("usage")
                if _r_usage:
                    try:
                        from core.cost_tracker import record_usage
                        record_usage(model=model_id, kind="text", usage=_r_usage, label="vision_fail")
                    except (ImportError, OSError, KeyError, TypeError) as e:
                        logger.debug("cost_tracker.record_usage(vision_fail) failed: %s: %s", type(e).__name__, e)
                break
            except (OSError, TimeoutError) as e:
                last_reason = f"网络/超时: {e}"
                metrics.increment("fallback.vision_model")
                break
            except RuntimeError as e:
                last_reason = f"上游错误: {e}"
                break
            except Exception as e:
                last_reason = f"未知错误({type(e).__name__}): {e}"
                logger.exception("vision fallback unexpected error for model %s", model_id)
                break

    # 全部失败：返回可读错误，列出已尝试模型与最后原因
    return (
        f"(视觉理解失败 · 已尝试 {len(tried)} 个模型: {', '.join(tried)})\n"
        f"最后错误: {last_reason}\n"
        "建议：检查网络/供应商 Key，或用 /provider 切换视觉供应商后重试。"
    )


