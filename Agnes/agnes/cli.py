"""Agnes CLI — 命令行全功能客户端（中文版）。

用法:
  python -m agnes.cli <command> [options]

命令：
  chat          文本对话
  vision        图片对话（多模态）
  image         生成图片
  img2img       图生图
  video         生成视频
  video-status  查询视频生成状态
  models        列出模型
  interactive   交互模式（中文）（中文）

示例：
  python -m agnes.cli chat "你好"
  python -m agnes.cli vision "图里有什么" --image photo.jpg
  python -m agnes.cli image "赛博朋克猫" --save cat.png
  python -m agnes.cli img2img "让猫戴上帽子" --image cat.png
  python -m agnes.cli video "海浪拍打礁石" --wait --save wave.mp4
  python -m agnes.cli models
"""

import sys
import os
import argparse
import json
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agnes.client import (
    AgnesClient, AgnesConfig, AgnesError,
    ALL_IMAGE_SIZES, IMAGE_SIZES, CHAT_MODELS, IMAGE_MODELS, VIDEO_MODELS,
)


from agnes.config import load_env_into_os
load_env_into_os()

def main():
    parser = argparse.ArgumentParser(
        description="Agnes AI 平台命令行工具 — 对话 · 图片 · 视频",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python -m agnes.cli chat "你好，介绍一下自己"
  python -m agnes.cli vision "图片里有什么？" --image photo.jpg
  python -m agnes.cli image "赛博朋克猫" --size 1024x1024 --save cat.png
  python -m agnes.cli img2img "把猫变成动漫风格" --image cat.png
  python -m agnes.cli video "海浪拍打礁石" --wait --save wave.mp4
  python -m agnes.cli models
  python -m agnes.cli interactive
        """,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # ── Chat ──────────────────────────────────────────
    p = sub.add_parser("chat", help="文本对话",
        epilog="模型: " + ", ".join(CHAT_MODELS.keys()))
    p.add_argument("prompt", nargs="?", help="输入文本（留空则进入对话模式）")
    p.add_argument("-m", "--model", default="agnes-2.0-flash", help="模型 ID")
    p.add_argument("-s", "--system", help="系统提示词")
    p.add_argument("--temp", type=float, default=0.7, help="采样温度（0-2）")
    p.add_argument("--max-tokens", type=int, default=4096, help="最大输出 Token")
    p.add_argument("--thinking", action="store_true", help="启用深度思考（仅 agnes-2.0-flash）")
    p.add_argument("--stream", action="store_true", help="流式输出")

    # ── Vision ────────────────────────────────────────
    p = sub.add_parser("vision", help="图片对话（多模态）",
        epilog="需要 agnes-2.0-flash 模型")
    p.add_argument("prompt", nargs="?", help="关于图片的问题")
    p.add_argument("--image", required=True, help="图片路径或 URL")
    p.add_argument("-m", "--model", default="agnes-2.0-flash")

    # ── Image ─────────────────────────────────────────
    p = sub.add_parser("image", aliases=["img"], help="生成图片",
        epilog="常用尺寸：1024×768, 1024×1024, 768×1024, 2048×2048")
    p.add_argument("prompt", help="图片描述文字")
    p.add_argument("-m", "--model", default="agnes-image-2.0-flash",
                   choices=list(IMAGE_MODELS.keys()))
    p.add_argument("-s", "--size", default="1024x768", help="尺寸（宽×高，必须为 16 的倍数）")
    p.add_argument("-n", type=int, default=1, help="生成数量")
    p.add_argument("--save", help="保存路径")
    p.add_argument("--b64", action="store_true", help="输出 Base64 编码而非 URL")
    p.add_argument("--seed", type=int, help="随机种子")
    p.add_argument("--list-sizes", action="store_true", help="列出所有可用尺寸")

    # ── Img2Img ───────────────────────────────────────
    p = sub.add_parser("img2img", help="图生图 / 图片编辑")
    p.add_argument("prompt", help="编辑描述")
    p.add_argument("--image", required=True, nargs="+", help="参考图片路径或 URL（可多个）")
    p.add_argument("-m", "--model", default="agnes-image-2.1-flash",
                   choices=list(IMAGE_MODELS.keys()))
    p.add_argument("-s", "--size", default="1024x768", help="输出尺寸")
    p.add_argument("--save", help="保存路径")

    # ── Video ─────────────────────────────────────────
    p = sub.add_parser("video", help="生成视频")
    p.add_argument("prompt", help="视频描述")
    p.add_argument("-m", "--model", default="agnes-video-v2.0")
    p.add_argument("--image", help="起始图路径或 URL（图生视频）")
    p.add_argument("-W", "--width", type=int, default=1152, help="宽度")
    p.add_argument("-H", "--height", type=int, default=768, help="高度")
    p.add_argument("--frames", type=int, help="总帧数（8n+1，最大 441）")
    p.add_argument("--fps", type=int, default=24, help="帧率")
    p.add_argument("--steps", type=int, help="推理步数")
    p.add_argument("--seed", type=int, help="随机种子")
    p.add_argument("--negative", help="负面提示词")
    p.add_argument("--no-wait", action="store_true", help="不等待完成（仅创建任务）")
    p.add_argument("--save", help="保存路径")
    p.add_argument("--poll", type=int, default=5, help="轮询间隔（秒）")

    # ── Video Status ──────────────────────────────────
    p = sub.add_parser("video-status", help="查询视频生成状态")
    p.add_argument("video_id", help="视频的 video_id")

    # ── Models ────────────────────────────────────────
    sub.add_parser("models", help="列出所有可用模型及能力")

    # ── Interactive ───────────────────────────────────
    sub.add_parser("interactive", aliases=["i", "shell"], help="交互模式（中文）")

    # ── Parse ──────────────────────────────────────────
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Handle --list-sizes
    if args.command in ("image", "img") and getattr(args, "list_sizes", False):
        print("可用图片尺寸：")
        for tier, sizes in IMAGE_SIZES.items():
            print(f"\n  {tier}:")
            for s in sizes:
                print(f"    {s}")
        return

    # Init client
    try:
        client = AgnesClient()
    except AgnesError as e:
        print(f"\n[错误] {e}\n")
        sys.exit(1)

    try:
        _dispatch(client, args)
    except AgnesError as e:
        print(f"\n[错误] {e}")
        if e.response:
            print(f"  响应: {json.dumps(e.response, ensure_ascii=False)[:300]}")
    except KeyboardInterrupt:
        print("\n已中断")
    except Exception as e:
        print(f"\n[未知错误] {type(e).__name__}: {e}")


def _dispatch(client: AgnesClient, args):
    cmd = args.command

    if cmd == "chat":
        if not args.prompt:
            _chat_loop(client, args)
        elif args.stream:
            _chat_stream(client, args)
        else:
            reply = client.chat_text(
                args.prompt, model=args.model,
                system=args.system, temperature=args.temp,
                max_tokens=args.max_tokens, thinking=args.thinking,
            )
            print(reply)

    elif cmd == "vision":
        image = args.image
        if not image.startswith(("http://", "https://", "data:")):
            image = client.image_to_base64(image)
        if not args.prompt:
            args.prompt = "请描述这张图片的内容"
        reply = client.chat_with_image(args.prompt, image, model=args.model)
        print(reply)

    elif cmd in ("image", "img"):
        images = client.generate_image(
            args.prompt, model=args.model, size=args.size,
            n=args.n, response_format="b64_json" if args.b64 else "url",
            seed=args.seed,
        )
        for i, img in enumerate(images):
            url = img.get("url", "")
            b64 = img.get("b64_json", "")
            if args.b64 and b64:
                print(f"  [{i+1}] base64 ({len(b64)} chars)")
            elif url:
                print(f"  [{i+1}] {url}")
                save_path = args.save
                if not save_path:
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    suffix = f"_{i}" if len(images) > 1 else ""
                    save_path = f"agnes_image_{ts}{suffix}.png"
                path = client.download_file(url, save_path)
                print(f"       💾 {path}")

    elif cmd == "img2img":
        urls = []
        for img_path in args.image:
            if img_path.startswith(("http://", "https://", "data:")):
                urls.append(img_path)
            else:
                urls.append(client.image_to_base64(img_path))
        images = client.generate_image(args.prompt, model=args.model, size=args.size, image_urls=urls)
        for img in images:
            url = img.get("url", "")
            print(f"  {url}")
            if args.save:
                client.download_file(url, args.save)
                print(f"  💾 {args.save}")
            elif url:
                ts = time.strftime("%Y%m%d_%H%M%S")
                path = client.download_file(url, f"agnes_img2img_{ts}.png")
                print(f"  💾 {path}")

    elif cmd == "video":
        image_url = None
        if args.image:
            image_url = args.image if args.image.startswith(("http://", "https://", "data:")) else client.image_to_base64(args.image)

        result = client.generate_video(
            args.prompt, model=args.model,
            image_url=image_url,
            width=args.width, height=args.height,
            num_frames=args.frames, frame_rate=args.fps,
            num_inference_steps=args.steps, seed=args.seed,
            negative_prompt=args.negative,
            wait=not args.no_wait,
            poll_interval=args.poll,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])

        video_url = result.get("url", "") or result.get("data", {}).get("url", "")
        if video_url and args.save:
            path = client.download_file(video_url, args.save)
            print(f"  💾 {path}")

    elif cmd == "video-status":
        result = client.get_video(args.video_id)
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])

    elif cmd == "models":
        models = client.list_models()
        print(f"{'模型 ID':<30} {'类型':<8} {'能力'}")
        print("-" * 70)
        for m in models:
            mid = m.get("id", "")
            mtype = client.get_model_type(mid)
            info = client.get_model_info(mid)
            caps = []
            if mtype == "chat":
                if info.get("vision"): caps.append("多模态")
                if info.get("tools"): caps.append("工具调用")
                if info.get("thinking"): caps.append("深度思考")
                if info.get("stream"): caps.append("流式")
                caps.append(f"{info.get('上下文',0)//1000}K 上下文")
            elif mtype == "image":
                caps.append(f"最大{info.get('max_size','?')}")
                if info.get("img2img"): caps.append("图生图")
            elif mtype == "video":
                caps.append("文生视频")
                if info.get("img2video"): caps.append("图生视频")
            print(f"  {mid:<30} {mtype:<8} {', '.join(caps)}")

    elif cmd in ("interactive", "i", "shell"):
        _interactive(client)


def _chat_loop(client: AgnesClient, args):
    """持续对话模式。"""
    print(f"Agnes 对话 ({args.model}) — 输入 quit 退出\n")
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})

    while True:
        try:
            user = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user:
            continue
        if user.lower() in ("quit", "exit", "q"):
            break

        messages.append({"role": "user", "content": user})
        resp = client.chat(messages, model=args.model, temperature=args.temp, max_tokens=args.max_tokens)
        reply = resp["choices"][0]["message"]["content"]
        messages.append({"role": "assistant", "content": reply})
        print(f"Agnes: {reply}\n")


def _chat_stream(client: AgnesClient, args):
    """流式输出模式。"""
    import requests
    body = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "temperature": args.temp,
        "max_tokens": args.max_tokens,
        "stream": True,
    }
    resp = requests.post(
        f"{client.config.api_base}/chat/completions",
        headers=client._headers,
        json=body,
        stream=True,
        timeout=client.config.timeout,
    )
    for line in resp.iter_lines():
        if not line:
            continue
        line = line.decode()
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0].get("delta", {}).get("content", "")
                if delta:
                    print(delta, end="", flush=True)
            except Exception:
                pass
    print()


def _interactive(client: AgnesClient):
    """交互模式（中文）。"""
    print("""
╔═══════════════════════════════════════════╗
║         Agnes AI — 交互模式        ║
╠═══════════════════════════════════════════╣
║  chat <文字>      文本对话                ║
║  vision <问题>    图片对话         ║
║  image <描述>     生成图片               ║
║  img2img <描述>   图生图          ║
║  video <描述>     生成视频        ║
║  models           列出模型               ║
║  help / quit      帮助 / 退出                               ║
╚═══════════════════════════════════════════╝
""")
    while True:
        try:
            cmd = input("agnes> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cmd:
            continue
        if cmd.lower() in ("quit", "exit", "q"):
            break

        parts = cmd.split(maxsplit=1)
        act = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        try:
            if act == "help":
                print("chat | vision | image | img2img | video | models | quit")
            elif act == "chat" and rest:
                print(client.chat_text(rest))
            elif act == "vision":
                # vision --image <file> <prompt>
                import shlex
                try:
                    toks = shlex.split(rest)
                except Exception:
                    toks = rest.split()
                img_path = ""
                prompt = ""
                i = 0
                while i < len(toks):
                    if toks[i] == "--image" and i + 1 < len(toks):
                        img_path = toks[i + 1]
                        i += 2
                    else:
                        prompt += toks[i] + " "
                        i += 1
                prompt = prompt.strip()
                if not img_path:
                    print("  用法：vision --image <图片文件> <问题>")
                else:
                    img = img_path if img_path.startswith(("http://", "https://", "data:")) else client.image_to_base64(img_path)
                    if not prompt:
                        prompt = "请描述这张图片"
                    print(client.chat_with_image(prompt, img))
            elif act in ("image", "img") and rest:
                for img in client.generate_image(rest):
                    url = img.get("url", "")
                    if url:
                        print(f"  {url}")
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        client.download_file(url, f"agnes_image_{ts}.png")
                        print(f"  💾 agnes_image_{ts}.png")
            elif act == "img2img":
                import shlex
                try:
                    toks = shlex.split(rest)
                except Exception:
                    toks = rest.split()
                img_paths = []
                prompt = ""
                i = 0
                while i < len(toks):
                    if toks[i] == "--image" and i + 1 < len(toks):
                        img_paths.append(toks[i + 1])
                        i += 2
                    else:
                        prompt += toks[i] + " "
                        i += 1
                prompt = prompt.strip()
                if not img_paths or not prompt:
                    print("  用法：img2img <描述文字> --image <图片文件>")
                else:
                    urls = [p if p.startswith(("http://","https://","data:")) else client.image_to_base64(p) for p in img_paths]
                    for img in client.generate_image(prompt, image_urls=urls):
                        client.download_file(img["url"], f"agnes_img2img_{int(time.time())}.png")
                        print(f"  💾 已保存")
            elif act == "video":
                import shlex
                try:
                    toks = shlex.split(rest)
                except Exception:
                    toks = rest.split()
                prompt = rest
                wait = "--no-wait" not in rest
                if wait:
                    prompt = rest.replace("--no-wait", "").strip()
                if prompt:
                    result = client.generate_video(prompt, wait=wait)
                    if not wait:
                        print(f"  video_id: {result.get('video_id', '')}")
            elif act == "models":
                for m in client.list_models():
                    mid = m.get("id", "")
                    mtype = client.get_model_type(mid)
                    print(f"  {mid:<30} {mtype}")
            else:
                print(f"  未知命令： {act}。输入 help 查看帮助")
        except AgnesError as e:
            print(f"  [错误] {e}")
        except Exception as e:
            print(f"  [错误] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
