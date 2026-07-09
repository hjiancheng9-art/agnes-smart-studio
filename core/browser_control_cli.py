#!/usr/bin/env python3
"""
browser-control CLI — 命令行一键操控 AI 平台
=============================================
用法:
    python -m core.browser_control send chatgpt "写一首诗"
    python -m core.browser_control send gemini "What is quantum computing?"
    python -m core.browser_control send kling "A cat walking on the moon"
    python -m core.browser_control list
    python -m core.browser_control read chatgpt
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.browser_control import list_platforms, read_from_ai, send_to_ai


def cmd_list():
    """列出所有平台"""
    platforms = list_platforms()
    print(f"{'平台':<12} {'URL'}")
    print("-" * 50)
    for name, url in platforms.items():
        print(f"{name:<12} {url}")


def cmd_send(platform: str, prompt: str, timeout: int = 240):
    """发送提示词并获取回复"""
    print(f"📤 发送到 {platform}...")
    print(f"📝 提示词: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print()

    result = send_to_ai(platform, prompt, timeout=timeout)

    if result["success"]:
        print("✅ 成功!")
        print("-" * 60)
        print(result["response"])
        print("-" * 60)
    else:
        print(f"❌ 失败: {result['error']}")
        if result["screenshot"]:
            print(f"📸 截图: {result['screenshot']}")

    return result


def cmd_read(platform: str, timeout: int = 60):
    """读取已打开页面的回复"""
    print(f"📖 读取 {platform} 回复...")
    response = read_from_ai(platform, timeout=timeout)
    if response:
        print(response)
    else:
        print("未获取到回复")
    return response


def main():
    parser = argparse.ArgumentParser(description="Browser Control CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="列出所有支持的 AI 平台")

    p_send = sub.add_parser("send", help="向 AI 平台发送提示词")
    p_send.add_argument("platform", choices=list(list_platforms().keys()))
    p_send.add_argument("prompt")
    p_send.add_argument("--timeout", type=int, default=240)

    p_read = sub.add_parser("read", help="读取平台回复")
    p_read.add_argument("platform", choices=list(list_platforms().keys()))
    p_read.add_argument("--timeout", type=int, default=60)

    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "send":
        cmd_send(args.platform, args.prompt, args.timeout)
    elif args.command == "read":
        cmd_read(args.platform, args.timeout)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
