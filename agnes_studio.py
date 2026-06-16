#!/usr/bin/env python3
"""Agnes Smart Studio 主入口"""
import sys
import os
from pathlib import Path

# Windows UTF-8 兼容
if os.name == "nt":
    os.system("chcp 65001 >nul 2>&1")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import SETTINGS

def main():
    if not SETTINGS.api_key:
        print("错误: 未设置 AGNES_API_KEY，请在 .env 文件中添加")
        sys.exit(1)

    import argparse
    p = argparse.ArgumentParser(description="Agnes Smart Studio")
    p.add_argument("-c", "--chat", action="store_true", help="进入聊天模式（多轮对话+混合生成）")
    p.add_argument("-q", "--quick", type=str, help="快速模式描述")
    p.add_argument("-v", "--video", action="store_true", help="生成视频")
    p.add_argument("-p", "--pipeline", action="store_true", help="一站式流水线")
    p.add_argument("--no-enhance", action="store_true", help="禁用Prompt增强")
    p.add_argument("--size", type=str, default="1024x768")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--submit-only", action="store_true", help="仅提交任务，不等待结果（返回video_id）")
    p.add_argument("--video-id", type=str, default=None, help="查询指定视频状态（必须使用 video_id）")
    p.add_argument("--timeout", type=float, default=None, help="视频轮询超时秒数（默认120）")
    p.add_argument("--steps", type=int, default=40, help="视频推理步数(20-50，默认40，越高质量越好)")
    p.add_argument("--num-frames", type=int, default=None, help="视频帧数(8n+1, 如81/121/161/241/441)")
    p.add_argument("--frame-rate", type=int, default=None, help="视频帧率(默认24)")
    p.add_argument("--creative", "--leap", action="store_true", help="启用创意飞跃模式（运用超越常人的思维方法生成突破性创意）")
    p.add_argument("--methods", type=str, default=None, help="指定创意方法（逗号分隔），如：cross_domain_graft,anti_pattern")
    args = p.parse_args()

    if args.video_id:
        _check_task(args)
    elif args.chat:
        from ui.cli import AgnesCLI
        with AgnesCLI() as cli:
            cli._chat()
    elif args.quick:
        _quick(args)
    else:
        from ui.cli import AgnesCLI
        with AgnesCLI() as cli:
            cli.run()

def _check_task(args):
    """查询视频任务状态"""
    from core.client import AgnesClient
    from ui.display import show_info, show_success, show_warning, show_video_result
    from utils import history

    with AgnesClient() as client:
        video_id = args.video_id
        if not video_id:
            show_warning("必须提供 --video-id 查询视频状态，不要使用 task_id")
            return
        show_info(f"查询视频ID {video_id}...")
        data = client.check_video(video_id=video_id)
        status = data.get("status", "unknown")
        progress = data.get("progress", 0)

        if status == "completed":
            show_success("视频已完成!")
            video_url = data.get("video_url") or data.get("remixed_from_video_id", "")
            local_path = ""
            if video_url and video_url.startswith("http"):
                from core.config import OUTPUT_DIR
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                local_path = str(OUTPUT_DIR / "videos" / f"vid_{ts}.mp4")
                try:
                    client.download_video(video_url, local_path)
                    show_success(f"已下载: {local_path}")
                except RuntimeError as e:
                    show_warning(f"下载失败: {e}")
            show_video_result({"url": video_url, "local_path": local_path,
                               "video_id": video_id})
        elif status == "failed":
            from ui.display import show_error
            show_error(f"视频生成失败: {data.get('error', '未知错误')}")
        else:
            show_info(f"状态: {status} | 进度: {progress:.0f}%")
            if status in ("processing", "in_progress", "pending", "queued"):
                show_info(f"使用 --video-id {video_id} 可再次查询，或加 --timeout 等待完成")

def _quick(args):
    from core.client import AgnesClient, ContentPolicyError
    from core.brain import SmartBrain
    from engines.text_to_image import TextToImageEngine
    from engines.video import VideoEngine
    from pipeline.workflows import PipelineOrchestrator
    from ui.display import show_image_result, show_video_result, show_pipeline_result, show_info, show_warning
    from utils import history

    with AgnesClient() as client:
        prompt = args.quick
        enhance = not args.no_enhance
        creative = args.creative
        creative_methods = [m.strip() for m in args.methods.split(",")] if args.methods else None
        timeout = args.timeout or 120.0
        nf = args.num_frames or 121
        fps = args.frame_rate or 24

        brain = SmartBrain(client) if (enhance or creative) else None

        if args.pipeline:
            show_info("一站式流水线...")
            try:
                result = PipelineOrchestrator(client).text_to_image_to_video(
                    args.quick, enhance=enhance, submit_only=args.submit_only,
                    num_frames=nf, frame_rate=fps,
                    num_inference_steps=args.steps, timeout=timeout)
            except ContentPolicyError as e:
                show_warning(str(e))
                sys.exit(0)
            if args.submit_only:
                vid_result = result.get('video', {})
                display_id = vid_result.get('video_id', 'N/A')
                show_info(f"视频任务已提交! ID: {display_id}")
                query_id = vid_result.get('video_id', '')
                if query_id:
                    show_info(f"使用以下命令查询: python agnes_studio.py --video-id {query_id}")
                else:
                    show_warning("未返回 video_id，请检查任务响应")
            else:
                show_pipeline_result(result)
            history.add_record("pipeline", args.quick, "multi", result)
        elif args.video:
            vid_prompt = prompt
            neg = ""
            if brain:
                if creative:
                    show_info("创意飞跃模式（视频）：运用超越常人的思维方法...")
                    r = brain.creative_leap(args.quick, methods=creative_methods)
                    leaps = r.get("creative_leaps", [])
                    idx = r.get("recommended_leap_index", 0)
                    if leaps and idx < len(leaps):
                        # 创意飞跃生成的是图片概念，需进一步增强为视频
                        leap_prompt = leaps[idx].get("optimized_prompt", prompt)
                        vid_r = brain.enhance_video_prompt(leap_prompt)
                        vid_prompt = vid_r.get("optimized_prompt", leap_prompt)
                        neg = vid_r.get("negative_prompt", "")
                        show_info(f"创意方法: {r.get('methods_used', [])}")
                        if r.get("guardrail_warning"):
                            show_warning(r["guardrail_warning"])
                    else:
                        show_warning("创意飞跃未产生有效方案，回退到普通增强")
                        r = brain.enhance_video_prompt(args.quick)
                        vid_prompt = r.get("optimized_prompt", prompt)
                        neg = r.get("negative_prompt", "")
                elif enhance:
                    show_info("优化视频提示词...")
                    r = brain.enhance_video_prompt(args.quick)
                    vid_prompt = r.get("optimized_prompt", prompt)
                    neg = r.get("negative_prompt", "")

            if args.submit_only:
                show_info("提交视频任务（仅提交，不等待）...")
                data = VideoEngine(client).submit_only(
                    prompt=vid_prompt, seed=args.seed,
                    negative_prompt=neg or None, num_frames=nf, frame_rate=fps,
                    num_inference_steps=args.steps)
                display_id = data.get('video_id', 'N/A')
                show_info(f"任务已提交! ID: {display_id}")
                query_id = data.get('video_id', '')
                if query_id:
                    show_info(f"使用以下命令查询: python agnes_studio.py --video-id {query_id}")
                else:
                    show_warning("未返回 video_id，请检查任务响应")
                history.add_record("text_to_video", args.quick, "agnes-video-v2.0", data)
            else:
                show_info("生成视频...")

                def on_p(status, progress, data):
                    print(f"\r  [{status}] {progress:.0f}%", end="", flush=True)

                data = VideoEngine(client).text_to_video(
                    prompt=vid_prompt, negative_prompt=neg or None, seed=args.seed,
                    num_frames=nf, frame_rate=fps,
                    num_inference_steps=args.steps,
                    on_progress=on_p, timeout=timeout)
                print()
                if data.get("status") == "timeout":
                    show_warning(f"超时({timeout}s)，当前进度 {data.get('progress', 0):.0f}%")
                    query_id = data.get('video_id', '')
                    if query_id:
                        show_info(f"使用以下命令继续等待: python agnes_studio.py --video-id {query_id}")
                    else:
                        show_warning("未返回 video_id，无法自动查询")
                else:
                    show_video_result(data)
                history.add_record("text_to_video", args.quick, "agnes-video-v2.0", data)
        else:
            img_prompt = prompt
            neg = ""
            if brain:
                if creative:
                    show_info("创意飞跃模式：运用超越常人的思维方法...")
                    r = brain.creative_leap(args.quick, methods=creative_methods)
                    leaps = r.get("creative_leaps", [])
                    idx = r.get("recommended_leap_index", 0)
                    if leaps and idx < len(leaps):
                        img_prompt = leaps[idx].get("optimized_prompt", prompt)
                        neg = leaps[idx].get("negative_prompt", "")
                        show_info(f"创意方法: {r.get('methods_used', [])}")
                        for i, leap in enumerate(leaps):
                            marker = "★" if i == idx else " "
                            show_info(f"  {marker} [{leap.get('method', '?')}] {leap.get('leap_description', '')[:60]}")
                        if r.get("guardrail_warning"):
                            show_warning(r["guardrail_warning"])
                    else:
                        show_warning("创意飞跃未产生有效方案，回退到普通增强")
                        r = brain.enhance_image_prompt(args.quick)
                        img_prompt = r.get("optimized_prompt", prompt)
                        neg = r.get("negative_prompt", "")
                elif enhance:
                    show_info("优化图片提示词...")
                    r = brain.enhance_image_prompt(args.quick)
                    img_prompt = r.get("optimized_prompt", prompt)
                    neg = r.get("negative_prompt", "")

            show_info("生成图片...")
            data = TextToImageEngine(client).generate(
                prompt=img_prompt, size=args.size, seed=args.seed,
                negative_prompt=neg or None)
            show_image_result(data)
            history.add_record("text_to_image", args.quick, data.get("model",""), data)

def main_chat():
    """命令行入口：直接进入聊天模式"""
    import sys
    sys.argv = [sys.argv[0], "-c"]
    main()


def main_query():
    """命令行入口：查询未完成视频"""
    from query import main as qmain
    qmain()


if __name__ == "__main__":
    main()
