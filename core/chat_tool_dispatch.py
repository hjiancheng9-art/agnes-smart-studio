"""Tool dispatch implementation — extracted from chat.py.

Contains _dispatch_tool_impl: executes tool calls with permission checks,
hook integration, TRM routing, and adversarial bypass fallback.
Injected into ChatSession at module level for circular import safety.
"""
from __future__ import annotations

import json
import logging

from engines.image_to_image import ImageToImageEngine
from engines.text_to_image import TextToImageEngine

logger = logging.getLogger('crux.tool_dispatch')

def _dispatch_tool_impl(self, name: str, args_json: str, *, confirmed: bool=False) -> tuple[str, list[tuple]]:
    """执行工具，返回 (给模型的文本, 给用户的副作用列表)。

    副作用列表元素: ("info", str) / ("image", dict) / ("video", dict) / ("confirm", dict)

    与命令式路径对齐：均经过 SmartBrain Prompt 增强后再调引擎。
    支持生命周期 hook（PRE_TOOL_USE / POST_TOOL_USE）和高风险工具确认。

    Args:
        confirmed: 若 True，跳过高风险工具确认检查（用户已在 UI 层确认）。
            由 _run_tool_calls 在 confirm 通过后二次调用时传入。
    """
    try:
        args = json.loads(args_json or '{}')
    except json.JSONDecodeError:
        args = {}
    if not confirmed:
        from core.permission import get_permission_manager
        pm = get_permission_manager()
        if pm.needs_confirmation(name, args):
            confirm_data = {'tool': name, 'args': args, 'mode': pm.get_mode_name()}
            return ('', [('confirm', confirm_data)])
    try:
        from core.hooks import HookType, hook_manager
        pre_evt = hook_manager.fire(HookType.PRE_TOOL_USE, data={'tool_name': name, 'args': args})
        if pre_evt.stop_processing:
            return ('工具调用被拦截（PRE_TOOL_USE hook）', [])
    except (ImportError, OSError):
        pass
    prompt = args.get('prompt', '')
    image_url = args.get('image_url', '') or args.get('image', '')
    image_urls = args.get('image_urls', []) or []
    mode = args.get('mode', '')
    gen_client = self.media_client
    if name == 'generate_image':
        size = args.get('size', '1024x768')
        seed = args.get('seed')
        system = args.get('system')
        neg_from_args = args.get('negative_prompt')
        side: list[tuple[str, str | dict]] = [('info', f'正在生成图片: {prompt}')]
        try:
            try:
                r = self.brain.enhance_image_prompt(prompt)
                fp = r.get('optimized_prompt', prompt)
                neg = neg_from_args or r.get('negative_prompt', '') or None
            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
                logger.debug('brain.enhance_image_prompt failed: %s: %s', type(e).__name__, e)
                fp, neg = (prompt, neg_from_args)
            if system:
                fp = f'[{system}] {fp}'
            if image_urls:
                i2i = ImageToImageEngine(gen_client)
                data = i2i.edit(prompt=fp, image_urls=image_urls, size=size)
            elif image_url:
                from utils import image_input
                url = image_input.load_image_as_url_or_data(image_url)
                i2i = ImageToImageEngine(gen_client)
                data = i2i.edit(prompt=fp, image_urls=url, size=size)
            else:
                t2i = TextToImageEngine(gen_client)
                data = t2i.generate(prompt=fp, size=size, seed=seed, negative_prompt=neg)
            side.append(('image', data))
            try:
                from core.cost_tracker import record_usage
                record_usage(model='agnes-image-2.1-flash', kind='image', label='generate_image', call_count=1)
            except (ImportError, OSError) as e:
                logger.debug('cost_tracker.record_usage(image) failed: %s: %s', type(e).__name__, e)
            return (f"图片已生成并保存: {data.get('local_path', '')}", side)
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            return (f'图片生成失败: {e}', side)
    if name == 'generate_video':
        size_str = args.get('size', '1152x768')
        num_frames = args.get('num_frames', 121)
        seed = args.get('seed')
        system = args.get('system')
        neg_from_args = args.get('negative_prompt')
        try:
            w_str, h_str = size_str.split('x')
            w, h = (int(w_str), int(h_str))
        except (ValueError, AttributeError):
            w, h = (1152, 768)
        side: list[tuple[str, str | dict]] = [('info', f'正在生成视频（可能需几分钟）: {prompt}')]
        try:
            try:
                r = self.brain.enhance_video_prompt(prompt)
                fp = r.get('optimized_prompt', prompt)
                neg = neg_from_args or r.get('negative_prompt', '') or None
            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
                logger.debug('brain.enhance_video_prompt failed: %s: %s', type(e).__name__, e)
                fp, neg = (prompt, neg_from_args)
            if system:
                fp = f'[{system}] {fp}'
            frame_rate = args.get('frame_rate', 24)
            if mode == 'keyframes' and image_urls:
                data = self.vid.keyframe_animation(prompt=fp, image_urls=image_urls, width=w, height=h, num_frames=num_frames, frame_rate=frame_rate, negative_prompt=neg, timeout=120.0)
            elif image_urls:
                data = self.vid.multi_image_video(prompt=fp, image_urls=image_urls, width=w, height=h, num_frames=num_frames, frame_rate=frame_rate, negative_prompt=neg, timeout=120.0)
            elif image_url:
                from utils import image_input
                url = image_input.load_image_as_url_or_data(image_url)
                data = self.vid.image_to_video(prompt=fp, image_url=url, width=w, height=h, num_frames=num_frames, frame_rate=frame_rate, negative_prompt=neg, timeout=120.0)
            else:
                data = self.vid.text_to_video(prompt=fp, width=w, height=h, num_frames=num_frames, frame_rate=frame_rate, negative_prompt=neg, timeout=120.0)
            side.append(('video', data))
            try:
                from core.cost_tracker import record_usage
                record_usage(model='agnes-video-v2.0', kind='video', label='generate_video', call_count=1)
            except (ImportError, OSError) as e:
                logger.debug('cost_tracker.record_usage(video) failed: %s: %s', type(e).__name__, e)
            if data.get('status') == 'timeout':
                vid = data.get('video_id', '')
                pct = data.get('progress', 0)
                return (f'视频生成超时（进度 {pct:.0f}%），请稍后用 video_id={vid} 查询状态', side)
            return (f"视频已生成: {data.get('local_path', '')}", side)
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            return (f'视频生成失败: {e}', side)
    if name == 'multi_agent':
        goal = args.get('goal', '')
        side: list[tuple[str, str | dict]] = [('info', f'正在启动多智能体协调: {goal}')]
        try:
            from core.multi_agent import coordinate

            def _tool_exec(tool, tool_args):
                if self.tools.has(tool):
                    return self.tools.execute(tool, tool_args)
                return f'[multi_agent] 工具 {tool} 不可用'
            result = coordinate(goal, _tool_exec)
            summary = f"多智能体协调完成: {result['tasks_done']}/{result['tasks_total']} 任务成功, 耗时 {result['elapsed']}s"
            if result['tasks_failed']:
                summary += f", {result['tasks_failed']} 失败"
            return (summary, side)
        except (RuntimeError, OSError, ValueError) as e:
            return (f'多智能体协调失败: {e}', side)
    if name == 'trm_tune':
        try:
            from core.growth_engine import get_growth_engine
            ge = get_growth_engine()
            do_apply = args.get('apply', False)
            result = ge.auto_tune(apply=do_apply)
            bottlenecks = ge.detect_bottlenecks()
            suggestions = ge.suggest_improvements()
            lines = ['CRUX Self-Optimization Results', '=' * 40]
            lines.append(f'Total calls analyzed: {ge._total_calls_ever}')
            if result.get('applied'):
                lines.append(f"\nApplied changes ({len(result['applied'])}):")
                for change in result['applied']:
                    lines.append(f"  + {change['action']}: {change.get('intent', '')}/{change.get('tool', '')}")
                    if 'new_order' in change:
                        lines.append(f"    -> {' > '.join(change['new_order'])}")
            if not do_apply:
                lines.append('\n[Dry run — use apply=true to commit changes]')
            if bottlenecks:
                lines.append(f'\nBottlenecks ({len(bottlenecks)}):')
                for b in bottlenecks[:3]:
                    lines.append(f"  ! [{b['severity']}] {b['intent']}/{b['tool']}: {', '.join(b['reasons'])}")
            if suggestions:
                lines.append('\nSuggestions:')
                for s in suggestions:
                    lines.append(f'  ? {s}')
            return ('\n'.join(lines), [])
        except Exception as e:
            logger.debug('error in except: %s', e, exc_info=True)
            return (f'Auto-tune error: {e}', [])
    if name == 'trm_growth':
        try:
            from core.growth_engine import get_growth_engine
            ge = get_growth_engine()
            if args.get('reset'):
                ge.reset()
                return ('Growth data reset.', [])
            intent_filter = args.get('intent', '')
            if intent_filter and intent_filter in ge.intents:
                is_ = ge.intents[intent_filter]
                lines = [f'Growth — [{intent_filter}] ({is_.total_calls} calls)']
                for ts in is_.ordered_tools:
                    status = 'D' if ts.demoted else '✓'
                    lines.append(f'  {status} {ts.tool}: {ts.success_rate:.0%} success, {ts.avg_latency_ms:.0f}ms avg, {ts.calls} calls' + (f' (CF:{ts.consecutive_failures})' if ts.consecutive_failures else ''))
                return ('\n'.join(lines), [])
            return (ge.get_summary(), [])
        except Exception as e:
            logger.debug('error in except: %s', e, exc_info=True)
            return (f'Growth engine error: {e}', [])
    if name == 'trm_catalog':
        try:
            from core.tool_registry_mesh import CATEGORY_META, get_trm
            trm = get_trm()
            trm.discover_all(timeout=5.0)
            cat_filter = args.get('category', '')
            src_filter = args.get('source', '')
            tools_found = trm.find(category=cat_filter, source=src_filter)
            lines = [f'TRM Catalog — {len(tools_found)} tools', f'Sources: {trm.sources}', f'Categories: {trm.categories}']
            for intent, meta in sorted(CATEGORY_META.items()):
                available = [t for t in meta['order'] if t in trm._tools or '*' in t]
                lines.append(f"\n  [{intent}] {meta['desc']}")
                lines.append(f"    路由: {(' → '.join(available) if available else '(none)')}")
            lines.append('\n--- Tools ---')
            for t in sorted(tools_found, key=lambda x: (x.category, x.name)):
                desc = t.description[:80].replace('\n', ' ')
                lines.append(f'  [{t.category}] {t.name} ({t.source}) — {desc}')
            return ('\n'.join(lines), [])
        except Exception as e:
            logger.debug('error in except: %s', e, exc_info=True)
            return (f'TRM catalog error: {e}', [])
    if name == 'trm_route':
        intent = args.get('intent', '')
        if not intent:
            return ("trm_route requires 'intent' parameter (search/review/execute/think/generate/status)", [])
        try:
            from core.tool_registry_mesh import get_trm
            trm = get_trm()
            trm.discover_all(timeout=5.0)
            route_kwargs = {}
            if args.get('query'):
                route_kwargs['query'] = args['query']
            if args.get('prompt'):
                route_kwargs['prompt'] = args['prompt']
            if args.get('target'):
                route_kwargs['target'] = args['target']
            if args.get('plan'):
                route_kwargs['prompt'] = args['plan']
            if args.get('work_dir'):
                route_kwargs['work_dir'] = args['work_dir']
            if args.get('timeout'):
                route_kwargs['timeout'] = args['timeout']
            if not route_kwargs:
                route_kwargs['prompt'] = args.get('query') or args.get('prompt') or intent
            result = trm.route(intent, **route_kwargs)
            summary = f"TRM Route [{intent}] → {result.tool} ({result.source}) [{('fallback' if result.fallback_used else 'primary')}] ({result.latency_ms:.0f}ms)\n"
            if result.error:
                summary += f'Error: {result.error}\n'
            if result.result:
                summary += f'Result: {json.dumps(result.result, ensure_ascii=False, default=str)[:2000]}'
            return (summary, [('info', f'Routed to {result.tool}')])
        except Exception as e:
            logger.debug('error in except: %s', e, exc_info=True)
            return (f'TRM route error: {e}', [])
    if self.tools.has(name):
        from core.constraints import LONG_RUNNING_TOOLS
        _LONG_RUNNING = LONG_RUNNING_TOOLS
        side: list[tuple[str, str | dict]] = []
        if name in _LONG_RUNNING:
            side.append(('info', f'正在执行 {name}...'))
        result = self.tools.execute(name, args)
        try:
            from core.hooks import HookType, hook_manager
            is_error = isinstance(result, str) and result.startswith('[错误]')
            post_evt = hook_manager.fire(HookType.POST_TOOL_USE, data={'tool_name': name, 'args': args, 'result': result, 'error': is_error})
            if isinstance(post_evt.result, str) and post_evt.result:
                result = post_evt.result
        except (ImportError, OSError):
            logger.debug('spectrum module not available')
        side.append(('info', f'工具 {name} 执行完成'))
        return (result, side)
    return (f'未知工具: {name}', [])
