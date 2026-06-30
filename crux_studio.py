#!/usr/bin/env python3
"""CRUX Studio main entry point"""

import asyncio
import sys
from pathlib import Path

import core.encoding as _enc
_enc.setup()

from ui.theme import COLORS, console

# ── 必须在任何异步操作之前应用 nest_asyncio ──
# 解决 prompt_toolkit / Playwright / edge-tts 等库
# asyncio.run() 在已有运行事件循环时抛出 RuntimeError 的问题
try:
    import nest_asyncio

    nest_asyncio.apply()
except (ImportError, OSError, RuntimeError):
    # nest_asyncio 缺失或损坏（如 .so 与 Python 版本不兼容）时降级，
    # 后续 async 调用仍能通过 asyncio.run() / asyncio.new_event_loop() 工作
    import logging
    logging.getLogger("crux").debug("nest_asyncio unavailable, continuing")

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Clear stale bytecode cache to prevent old .pyc from shadowing source changes
for _d in ROOT.rglob("__pycache__"):
    try:
        for _f in _d.iterdir():
            _f.unlink()
    except OSError:
        pass

from core.config import SETTINGS

# Clean up stale error file from previous crashed sessions
_stale_err = ROOT / "output" / "last_error.txt"
if _stale_err.exists():
    _stale_err.unlink()


def main():
    # ── 子命令预处理 ──────────────────────────────────────
    # 支持 crux gen|video|chat|query|check|version 子命令，
    # 同时完全保留 -q/-v/-c/-p/--video-id 等短选项（向后兼容所有 bat/sh 脚本）。
    # 子命令会被翻译成等价的 argv flags，然后走下面的 argparse 流程。
    _SUBCOMMANDS = {
        "gen": lambda rest: ["-q", *rest],  # crux gen "猫" → -q "猫"
        "image": lambda rest: ["-q", *rest],  # 别名
        "video": lambda rest: ["-q", *rest, "-v"],  # crux video "海边" → -q "海边" -v
        "chat": lambda rest: ["-c", *rest],
        "pipeline": lambda rest: ["-q" if rest else "", "-p", *rest] if rest else ["-p", *rest],
        "query": lambda rest: ["--video-id", *rest],  # crux query <id> → --video-id <id>
        "check": lambda rest: ["--check", *rest],
    }

    if len(sys.argv) >= 2 and sys.argv[1] in _SUBCOMMANDS:
        sub = sys.argv[1]
        rest = sys.argv[2:]
        if sub == "pipeline" and rest:
            sys.argv = [sys.argv[0], "-q", rest[0], "-p", *rest[1:]]
        else:
            sys.argv = [sys.argv[0], *_SUBCOMMANDS[sub](rest)]
    elif len(sys.argv) >= 2 and sys.argv[1] in ("version", "--version", "-V"):
        # crux version — 不需要 API Key，直接打印并退出
        from core.version import __version__

        print(f"CRUX Studio v{__version__}")
        sys.exit(0)
    elif len(sys.argv) >= 2 and sys.argv[1] in ("init", "login"):
        # crux init / crux login — 写全局 ~/.crux/auth.json，对标 codex 首次引导。
        # 不需要 API Key（这就是配置它的命令），独立处理直接退出。
        _run_init()
        sys.exit(0)
    elif len(sys.argv) >= 2 and sys.argv[1] == "mcp-serve":
        # crux mcp-serve — 启动 MCP server（stdio JSON-RPC），让 CRUX 作为
        # 与 codex/claude/codebuddy 对等的第四象被调用。绕过 API Key 强制校验
        # （server 自己从 config / auth.json 读取，与 init/version 同为早退分支）。
        # 程序化调用，不进 REPL，不出现在 launcher 菜单里。
        from core.mcp_server import run_mcp_server

        run_mcp_server(sys.argv[2:])
        sys.exit(0)
    elif len(sys.argv) >= 2 and sys.argv[1] == "mcp-bridge":
        # crux mcp-bridge — 启动 Claude Code MCP Bridge（让 CRUX 获得软件工程工具）
        from core.claude_mcp_bridge import main as bridge_main

        bridge_main()
        sys.exit(0)

    if not SETTINGS.api_key:
        print("错误: 未设置 CRUX_API_KEY（兼容 AGNES_API_KEY）")
        print("  解决: 运行  crux init    写入全局配置（一次配置，任意目录可用）")
        print("  或:   在当前目录建 .env 文件，加 CRUX_API_KEY=你的key")
        print("  或:   设系统环境变量 CRUX_API_KEY")
        sys.exit(1)

    import argparse

    p = argparse.ArgumentParser(description="CRUX Studio — code/create/deploy")
    p.add_argument("--check", action="store_true", help="启动前运行健康检查并退出")
    p.add_argument("-c", "--chat", action="store_true", help="进入 CRUX 编程助手（支持 /制片 切换视频模式）")
    p.add_argument("-q", "--quick", type=str, help="快速模式描述")
    p.add_argument("-v", "--video", action="store_true", help="生成视频")
    p.add_argument("-p", "--pipeline", action="store_true", help="一站式流水线")
    p.add_argument("--no-enhance", action="store_true", help="禁用Prompt增强")
    p.add_argument("--size", type=str, default="1024x768")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--submit-only", action="store_true", help="仅提交任务，不等待结果（返回video_id）")
    p.add_argument("--video-id", type=str, default=None, help="查询指定视频状态（必须使用 video_id）")
    p.add_argument("--menu", action="store_true", help="显示功能菜单（旧版交互界面）")
    p.add_argument("--timeout", type=float, default=None, help="视频轮询超时秒数（默认120）")
    p.add_argument("--steps", type=int, default=40, help="视频推理步数(20-50，默认40，越高质量越好)")
    p.add_argument("--num-frames", type=int, default=None, help="视频帧数(8n+1, 如81/121/161/241/441)")
    p.add_argument("--frame-rate", type=int, default=None, help="视频帧率(默认24)")
    p.add_argument(
        "--creative", "--leap", action="store_true", help="启用创意飞跃模式（运用超越常人的思维方法生成突破性创意）"
    )
    p.add_argument(
        "--methods", type=str, default=None, help="指定创意方法（逗号分隔），如：cross_domain_graft,anti_pattern"
    )
    args = p.parse_args()

    # ── 健康检查 ──
    if args.check:
        from core.startup_checks import print_report, run_all

        results = run_all()
        print_report(results, show_ok=True)
        failures = [msg for _, ok, msg in results if not ok]
        if failures:
            print(f"\n  {len(failures)} check(s) failed")
            sys.exit(1)
        else:
            print("\n  所有检查通过")
            sys.exit(0)

    if args.video_id:
        # 清洗 litellm 包装的 video_id
        from engines.video import _clean_video_id

        args.video_id = _clean_video_id(args.video_id)
        _check_task(args)
    elif args.chat:
        # ── 快速启动检查（仅本地，不阻塞网络）──
        try:
            import core.startup_checks as _sc
            from core.startup_checks import critical_failures, print_report, run_all

            # 跳过慢速网络检查（chat 模式不需要等 API 响应）
            _sc._check_api_connectivity = lambda: None
            results = run_all()
            crit = critical_failures(results)
            if crit:
                console.print("\n  [bold {}]=== Startup check found issues ===[/]".format(COLORS["error"]))
                print_report(results, show_ok=False)
                console.print("  [{}]Run: crux check[/]\n".format(COLORS["warning"]))
            else:
                # 只在有 warning 时才输出
                warnings = [(c, m) for c, ok, m in results if not ok]
                if warnings:
                    for _cat, msg in warnings:
                        console.print("  [{}]![/] {}".format(COLORS["warning"], msg))
        except (ImportError, AttributeError, OSError):
            pass

        from ui.cli import CruxCLI

        try:
            with CruxCLI() as cli:
                try:
                    asyncio.run(cli._chat_layout())
                except (OSError, RuntimeError, ValueError, ImportError):
                    import traceback

                    err = traceback.format_exc()
                    print(err, file=sys.stderr)
                    err_path = ROOT / "output" / "last_error.txt"
                    err_path.parent.mkdir(parents=True, exist_ok=True)
                    err_path.write_text(err, encoding="utf-8")
        except (OSError, RuntimeError, ValueError, ImportError):
            import traceback

            err = traceback.format_exc()
            print(err, file=sys.stderr)
            err_path = ROOT / "output" / "last_error.txt"
            err_path.parent.mkdir(parents=True, exist_ok=True)
            err_path.write_text(err, encoding="utf-8")
    elif args.quick:
        _quick(args)
    elif args.menu:
        # 旧版功能菜单（--menu 触发）
        from ui.cli import CruxCLI

        try:
            with CruxCLI() as cli:
                cli.run()
        except (OSError, RuntimeError, ValueError, ImportError):
            import traceback

            err = traceback.format_exc()
            print(err, file=sys.stderr)
            err_path = ROOT / "output" / "last_error.txt"
            err_path.parent.mkdir(parents=True, exist_ok=True)
            err_path.write_text(err, encoding="utf-8")
    else:
        # 默认入口：直接进入 Chat 模式
        from ui.cli import CruxCLI

        try:
            with CruxCLI() as cli:
                try:
                    asyncio.run(cli._chat_layout())
                except (OSError, RuntimeError, ValueError, ImportError):
                    import traceback

                    err = traceback.format_exc()
                    print(err, file=sys.stderr)
                    err_path = ROOT / "output" / "last_error.txt"
                    err_path.parent.mkdir(parents=True, exist_ok=True)
                    err_path.write_text(err, encoding="utf-8")
        except (OSError, RuntimeError, ValueError, ImportError):
            import traceback

            err = traceback.format_exc()
            print(err, file=sys.stderr)
            err_path = ROOT / "output" / "last_error.txt"
            err_path.parent.mkdir(parents=True, exist_ok=True)
            err_path.write_text(err, encoding="utf-8")


def _check_task(args):
    """查询视频任务状态"""
    from core.client import CruxClient
    from ui.display import show_info, show_success, show_video_result, show_warning

    with CruxClient() as client:
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
                from datetime import datetime

                from core.config import OUTPUT_DIR

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                local_path = str(OUTPUT_DIR / "videos" / f"vid_{ts}.mp4")
                try:
                    client.download_video(video_url, local_path)
                    show_success(f"已下载: {local_path}")
                except RuntimeError as e:
                    show_warning(f"下载失败: {e}")
            show_video_result({"url": video_url, "local_path": local_path, "video_id": video_id})
        elif status == "failed":
            from ui.display import show_error

            show_error(f"视频生成失败: {data.get('error', '未知错误')}")
        else:
            show_info(f"状态: {status} | 进度: {progress:.0f}%")
            if status in ("processing", "in_progress", "pending", "queued"):
                show_info(f"使用 --video-id {video_id} 可再次查询，或加 --timeout 等待完成")


def _quick(args):
    from core.brain import SmartBrain
    from core.client import ContentPolicyError, CruxClient
    from engines.text_to_image import TextToImageEngine
    from engines.video import VideoEngine
    from engines.pipeline.workflows import PipelineOrchestrator
    from ui.display import show_image_result, show_info, show_pipeline_result, show_video_result, show_warning
    from utils import history

    with CruxClient() as client:
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
                    args.quick,
                    enhance=enhance,
                    submit_only=args.submit_only,
                    num_frames=nf,
                    frame_rate=fps,
                    num_inference_steps=args.steps,
                    timeout=timeout,
                )
            except ContentPolicyError as e:
                show_warning(str(e))
                sys.exit(0)
            if args.submit_only:
                vid_result = result.get("video", {})
                display_id = vid_result.get("video_id", "N/A")
                show_info(f"视频任务已提交! ID: {display_id}")
                query_id = vid_result.get("video_id", "")
                if query_id:
                    show_info(f"使用以下命令查询: crux query {query_id}")
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
                    prompt=vid_prompt,
                    seed=args.seed,
                    negative_prompt=neg or None,
                    num_frames=nf,
                    frame_rate=fps,
                    num_inference_steps=args.steps,
                )
                display_id = data.get("video_id", "N/A")
                show_info(f"任务已提交! ID: {display_id}")
                query_id = data.get("video_id", "")
                if query_id:
                    show_info(f"使用以下命令查询: crux query {query_id}")
                else:
                    show_warning("未返回 video_id，请检查任务响应")
                history.add_record("text_to_video", args.quick, "agnes-video-v2.0", data)
            else:
                show_info("生成视频...")

                def on_p(status, progress, data):
                    print(f"\r  [{status}] {progress:.0f}%", end="", flush=True)

                data = VideoEngine(client).text_to_video(
                    prompt=vid_prompt,
                    negative_prompt=neg or None,
                    seed=args.seed,
                    num_frames=nf,
                    frame_rate=fps,
                    num_inference_steps=args.steps,
                    on_progress=on_p,
                    timeout=timeout,
                )
                print()
                if data.get("status") == "timeout":
                    show_warning(f"超时({timeout}s)，当前进度 {data.get('progress', 0):.0f}%")
                    query_id = data.get("video_id", "")
                    if query_id:
                        show_info(f"使用以下命令继续等待: crux query {query_id} --watch")
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
                prompt=img_prompt, size=args.size, seed=args.seed, negative_prompt=neg or None
            )
            show_image_result(data)
            history.add_record("text_to_image", args.quick, data.get("model", ""), data)


def _run_init():
    """crux init / crux login — 写全局 ~/.crux/auth.json。

    对标 codex 首次运行引导：一次配置，任意目录敲 crux 都能用。
    交互式读取 API Key（不在命令行明文回显，避免 shell history 泄露）。
    """
    from core.config import AUTH_FILE, SETTINGS, save_global_auth

    print()
    print("  CRUX 全局配置初始化")
    print(f"  将写入: {AUTH_FILE}")
    print("  (此文件存 API Key，仅本机可读，配置后任意目录均可启动 crux)")
    print()

    # 预填：已有 key 时显示尾号，回车保留
    existing = SETTINGS.api_key
    if existing:
        print(f"  当前已配置 key: ...{existing[-8:]}")
        key = input("  输入新 CRUX_API_KEY (回车保留现有): ").strip()
        if not key:
            key = existing
    else:
        key = input("  请输入 CRUX_API_KEY: ").strip()

    if not key:
        print("  未输入 key，已取消。")
        return

    base_url = input("  CRUX_BASE_URL (回车用默认 https://apihub.agnes-ai.com/v1): ").strip()
    base_url = base_url or "https://apihub.agnes-ai.com/v1"

    try:
        path = save_global_auth(key, base_url)
    except OSError as e:
        print(f"  写入失败: {e}")
        return

    print()
    print(f"  ✓ 已保存到 {path}")
    print("  ✓ 现在在任意目录敲 crux 都能用。")
    print()


def main_chat():
    """命令行入口：直接进入 CRUX 编程助手"""
    import sys

    sys.argv = [sys.argv[0], "-c"]
    main()


def main_query():
    """命令行入口：查询未完成视频"""
    from query import main as qmain

    qmain()


if __name__ == "__main__":
    main()
