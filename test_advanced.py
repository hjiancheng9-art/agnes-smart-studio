#!/usr/bin/env python3
"""
高级功能测试脚本
用法: python test_advanced.py [test_name]

可选参数:
  all        - 运行全部快速测试（默认）
  i2i        - 仅测试图生图
  i2v        - 仅测试图生视频（submit-only模式）
  multimodal - 仅测试多模态理解
  brain      - 仅测试智能大脑
  check ID   - 查询视频任务状态
"""
import sys, os
if os.name == "nt":
    os.system("chcp 65001 >nul 2>&1")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

from core.client import AgnesClient
from ui.display import show_info, show_success, show_error, show_warning, show_image_result, show_video_result

test = sys.argv[1] if len(sys.argv) > 1 else "all"


def test_i2i():
    """图生图 - 风格迁移测试"""
    show_info("图生图测试：先生成源图，再做风格迁移")

    from engines.text_to_image import TextToImageEngine
    t2i = TextToImageEngine(client)
    src = t2i.generate(
        prompt="a beautiful Japanese garden with a red bridge, koi pond, cherry blossoms, morning light",
        size="1024x576",
    )
    src_url = src["url"]
    show_success(f"源图已生成: {src['local_path']}")

    from engines.image_to_image import ImageToImageEngine
    i2i = ImageToImageEngine(client)

    r1 = i2i.style_transfer(
        prompt="transform this into a traditional Chinese ink wash painting, monochrome, elegant brushstrokes",
        image_url=src_url,
        size="1024x576",
    )
    show_success(f"水墨画风格: {r1['local_path']}")

    r2 = i2i.style_transfer(
        prompt="transform this into a cyberpunk neon-lit scene, purple and cyan lights, futuristic",
        image_url=src_url,
        size="1024x576",
    )
    show_success(f"赛博朋克风格: {r2['local_path']}")

    show_image_result(r2)
    return src_url


def test_i2v(src_url=None):
    """图生视频测试 - 使用submit-only模式，避免阻塞"""
    show_info("图生视频测试（submit-only模式）")

    if not src_url:
        from engines.text_to_image import TextToImageEngine
        t2i = TextToImageEngine(client)
        src = t2i.generate(
            prompt="a majestic eagle perched on a mountain cliff, dramatic sunset, cinematic",
            size="1152x648",
        )
        src_url = src["url"]
        show_success(f"源图已生成: {src['local_path']}")

    from engines.video import VideoEngine
    vid = VideoEngine(client)

    show_info("提交图生视频任务（不阻塞等待）...")
    result = vid.submit_only(
        prompt="the eagle spreads its wings and takes flight, camera slowly zooms out",
        image=src_url,
        width=1152,
        height=648,
        num_frames=81,
        frame_rate=24,
    )
    display_id = result.get('video_id', 'N/A')
    if not display_id or display_id == 'N/A':
        show_warning("未返回 video_id，请检查 API 响应")
        return result
    show_success(f"任务已提交! video_id: {display_id}")
    show_info(f"查询状态: python test_advanced.py check {display_id}")
    show_info(f"或: python agnes_studio.py --video-id {display_id}")
    return result


def test_i2v_wait(src_url=None, timeout=60.0):
    """图生视频测试 - 限时等待模式（可选，超时不会阻塞）"""
    show_info(f"图生视频测试（限时{timeout}秒等待）")

    if not src_url:
        from engines.text_to_image import TextToImageEngine
        t2i = TextToImageEngine(client)
        src = t2i.generate(
            prompt="a majestic eagle perched on a mountain cliff, dramatic sunset, cinematic",
            size="1152x648",
        )
        src_url = src["url"]
        show_success(f"源图已生成: {src['local_path']}")

    from engines.video import VideoEngine
    vid = VideoEngine(client)

    show_info(f"提交图生视频任务，限时{timeout}秒...")

    def on_progress(status, progress, data):
        print(f"\r  [{status}] {progress:.0f}%", end="", flush=True)

    result = vid.image_to_video(
        prompt="the eagle spreads its wings and takes flight",
        image_url=src_url,
        width=1152,
        height=648,
        num_frames=81,
        frame_rate=24,
        on_progress=on_progress,
        timeout=timeout,
    )
    print()

    if result.get("status") == "timeout":
        show_warning(f"超时({timeout}s)，当前进度 {result.get('progress', 0):.0f}%")
        query_id = result.get('video_id', '')
        show_info(f"查询: python test_advanced.py check {query_id}")
    else:
        show_video_result(result)
    return result


def test_multimodal():
    """多模态理解测试 - 用1.5-flash分析图片"""
    show_info("多模态理解测试（1.5-flash）")

    from engines.text_to_image import TextToImageEngine
    t2i = TextToImageEngine(client)
    src = t2i.generate(
        prompt="a cozy coffee shop interior with books, warm lighting, rain outside the window",
        size="1024x576",
    )
    src_url = src["url"]
    show_success(f"测试图已生成: {src['local_path']}")

    r = client.chat_multimodal(
        text="Please describe this image in detail, including the scene, colors, mood, and composition.",
        image_url=src_url,
        model="agnes-1.5-flash",
        max_tokens=500,
    )
    try:
        description = r["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        show_error(f"多模态API返回格式异常: {str(r)[:200]}")
        return None
    show_success(f"多模态理解结果 ({len(description)} 字符):")
    print(f"\n{description}\n")
    return description


def test_brain():
    """智能大脑测试 - 意图识别+Prompt增强"""
    show_info("智能大脑测试")
    from core.brain import SmartBrain
    brain = SmartBrain(client)

    tests = [
        "画一只赛博朋克风格的猫",
        "把这张照片变成油画风格",
        "帮我生成一段海边日落的视频",
        "这个图片里有什么？",
    ]
    for t in tests:
        r = brain.recognize_intent(t)
        print(f"  输入: {t}")
        print(f"    意图: {r.get('intent')} | 置信度: {r.get('confidence')}")
        print()

    r = brain.enhance_image_prompt("一只猫在窗台上")
    show_success(f"Prompt增强: {r.get('optimized_prompt', 'N/A')[:100]}...")

    r = brain.enhance_video_prompt("海边日落")
    show_success(f"视频Prompt增强: {r.get('optimized_prompt', 'N/A')[:100]}...")
    if r.get("negative_prompt"):
        print(f"  负向提示词: {r['negative_prompt'][:80]}")


def check_task(video_id: str):
    """查询视频任务状态（必须使用 video_id，禁止使用 task_id）"""
    show_info(f"查询 video_id: {video_id}...")
    try:
        data = client.check_video(video_id=video_id)
    except Exception as e:
        show_error(f"查询失败: {e}")
        return
    status = data.get("status", "unknown")
    progress = data.get("progress", 0)

    if status == "completed":
        show_success("视频已完成!")
        video_url = data.get("remixed_from_video_id", "") or data.get("video_url", "")
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
        show_video_result({"url": video_url, "local_path": local_path, "video_id": video_id})
    elif status == "failed":
        show_error(f"视频生成失败: {data.get('error', '未知错误')}")
    else:
        show_info(f"状态: {status} | 进度: {progress:.0f}%")
        show_info("稍后再次查询: python test_advanced.py check {video_id}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Agnes Smart Studio - 高级功能测试")
    print("=" * 60)

    with AgnesClient() as client:

        # check 模式: python test_advanced.py check VIDEO_ID
        # ⚠️ 必须使用 video_id 查询，task_id 会导致排队超过5分钟
        if test == "check" and len(sys.argv) > 2:
            query_val = sys.argv[2]
            check_task(query_val)
        elif test in ("all", "i2i"):
            print("\n>>> 测试1: 图生图")
            src_url = test_i2i()

            if test in ("all", "multimodal"):
                print("\n>>> 测试2: 多模态理解")
                test_multimodal()

            if test in ("all", "brain"):
                print("\n>>> 测试3: 智能大脑")
                test_brain()

            if test in ("all", "i2v"):
                print("\n>>> 测试4: 图生视频 (submit-only)")
                test_i2v(src_url)
        elif test == "multimodal":
            test_multimodal()
        elif test == "brain":
            test_brain()
        elif test == "i2v":
            test_i2v()
        elif test == "i2v-wait":
            # 限时等待模式: python test_advanced.py i2v-wait
            test_i2v_wait(timeout=60.0)
        else:
            print(f"未知测试: {test}")
            print("可用: all, i2i, i2v, i2v-wait, multimodal, brain, check VIDEO_ID")

        print("\n" + "=" * 60)
        print("  测试完成!")
        print("=" * 60)
