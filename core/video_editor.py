"""视频编辑引擎 — ffmpeg 封装（引擎级视频后处理）

提供 5 个工具：
- video_concat: 多段视频拼接
- video_trim: 剪辑指定片段
- composite_overlay: 叠加字幕/水印/画中画
- video_speed: 变速（快放/慢放）
- render_final: 多段视频+音频+转场一键成片

所有工具输出到 output/videos/ 目录。
"""

import contextlib
import json
import subprocess
import tempfile
from pathlib import Path

__all__ = [
    "OUTPUT_ROOT",
    "VIDEO_EDITOR_EXECUTOR_MAP",
    "VIDEO_EDITOR_TOOL_DEFS",
    "VIDEO_OUT",
    "execute_composite_overlay",
    "execute_render_final",
    "execute_video_concat",
    "execute_video_speed",
    "execute_video_trim",
]

OUTPUT_ROOT = Path(__file__).parent.parent / "output"
VIDEO_OUT = OUTPUT_ROOT / "videos"
VIDEO_OUT.mkdir(parents=True, exist_ok=True)


def _run(cmd: list, timeout: int = 300, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run 安全封装（委托给 run_subprocess）"""
    from core.mcp_servers._mcp_utils import run_subprocess as _rs

    return _rs(cmd, timeout=timeout, **kwargs)


def _check_ffmpeg() -> str | None:
    """检查 ffmpeg 是否可用，返回错误文本或 None"""
    try:
        r = _run(["ffmpeg", "-version"], timeout=5)
        if r.returncode != 0:
            return "ffmpeg 不可用，请安装: winget install ffmpeg"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "未找到 ffmpeg，请安装: winget install ffmpeg"
    return None


def _safe_output_path(prefix: str, ext: str = ".mp4") -> str:
    """生成唯一输出路径"""
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    i = 0
    while True:
        suffix = f"_{i}" if i else ""
        p = VIDEO_OUT / f"{prefix}_{ts}{suffix}{ext}"
        if not p.exists():
            return str(p)
        i += 1


# ============================================================
#  工具1: video_concat — 多段视频拼接
# ============================================================


def execute_video_concat(video_paths: str, project_name: str = "") -> str:
    """将多个视频文件按顺序拼接为一段视频。

    所有视频会被转码为统一的 H.264/AAC 格式。

    Args:
        video_paths: JSON 数组字符串，如 '["path1.mp4","path2.mp4"]'
        project_name: 可选项目名，用于输出文件命名
    """
    err = _check_ffmpeg()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    try:
        paths = json.loads(video_paths) if isinstance(video_paths, str) else video_paths
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"error": "video_paths 必须是 JSON 数组字符串", "success": False}, ensure_ascii=False)

    if not paths or len(paths) < 2:
        return json.dumps({"error": "至少需要 2 个视频文件进行拼接", "success": False}, ensure_ascii=False)

    # 验证文件存在
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        return json.dumps({"error": f"以下文件不存在: {missing}", "success": False}, ensure_ascii=False)

    # 生成 concat file list
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in paths:
            f.write(f"file '{Path(p).absolute().as_posix()}'\n")
        concat_list = f.name

    prefix = project_name or "concat"
    out_path = _safe_output_path(prefix.replace(" ", "_"))

    try:
        r = _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_list,
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                out_path,
            ],
            timeout=600,
        )
        if r.returncode != 0:
            err_msg = (r.stderr or "")[-500:]
            return json.dumps({"error": f"拼接失败: {err_msg}", "success": False}, ensure_ascii=False)
    finally:
        Path(concat_list).unlink(missing_ok=True)

    size = Path(out_path).stat().st_size
    return json.dumps(
        {
            "success": True,
            "output_path": out_path,
            "input_count": len(paths),
            "file_size_mb": round(size / 1024 / 1024, 2),
            "message": f"已拼接 {len(paths)} 段视频 → {out_path}",
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具2: video_trim — 剪辑指定片段
# ============================================================


def execute_video_trim(
    video_path: str, start_seconds: float = 0, end_seconds: float = -1, project_name: str = ""
) -> str:
    """剪辑视频的指定时间段。

    Args:
        video_path: 本地视频路径
        start_seconds: 开始时间（秒）
        end_seconds: 结束时间（秒），-1 表示到结尾
        project_name: 可选项目名
    """
    err = _check_ffmpeg()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    vp = Path(video_path)
    if not vp.exists():
        return json.dumps({"error": f"视频文件不存在: {video_path}", "success": False}, ensure_ascii=False)

    # 获取时长
    probe = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(vp),
        ],
        timeout=15,
    )
    duration = 0
    with contextlib.suppress(ValueError):
        duration = float(probe.stdout.strip())

    if end_seconds <= 0:
        end_seconds = duration

    if start_seconds < 0 or start_seconds >= duration:
        return json.dumps(
            {"error": f"起始时间 {start_seconds}s 不合法（时长 {duration:.1f}s）", "success": False}, ensure_ascii=False
        )

    prefix = project_name or vp.stem
    out_path = _safe_output_path(f"{prefix}_trim")

    r = _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(start_seconds),
            "-to",
            str(end_seconds),
            "-i",
            str(vp),
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            out_path,
        ],
        timeout=600,
    )

    if r.returncode != 0:
        err_msg = (r.stderr or "")[-500:]
        return json.dumps({"error": f"剪辑失败: {err_msg}", "success": False}, ensure_ascii=False)

    size = Path(out_path).stat().st_size
    return json.dumps(
        {
            "success": True,
            "output_path": out_path,
            "start_seconds": start_seconds,
            "end_seconds": end_seconds,
            "clip_duration_s": round(end_seconds - start_seconds, 1),
            "file_size_mb": round(size / 1024 / 1024, 2),
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具3: composite_overlay — 画中画/叠加字幕/叠加水印
# ============================================================


def execute_composite_overlay(
    video_path: str,
    overlay_type: str = "subtitle",
    overlay_text: str = "",
    image_path: str = "",
    position: str = "bottom-center",
    project_name: str = "",
) -> str:
    """在视频上叠加文字字幕或图片水印/画中画。

    Args:
        video_path: 本地视频路径
        overlay_type: "subtitle" 叠加文字 / "watermark" 图片水印 / "pip" 画中画
        overlay_text: 要叠加的文字内容（subtitle 模式）
        image_path: 图片路径（watermark/pip 模式）
        position: 位置: top-left/top-center/top-right/center/bottom-left/bottom-center/bottom-right
        project_name: 可选项目名
    """
    err = _check_ffmpeg()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    vp = Path(video_path)
    if not vp.exists():
        return json.dumps({"error": f"视频文件不存在: {video_path}", "success": False}, ensure_ascii=False)

    # 位置 → drawtext x:y 或 overlay x:y
    # 默认 1920x1080 坐标系
    POS_MAP = {
        "top-left": ("10", "10"),
        "top-center": ("(w-text_w)/2", "10"),
        "top-right": ("(w-text_w)-10", "10"),
        "center": ("(w-text_w)/2", "(h-text_h)/2"),
        "bottom-left": ("10", "(h-text_h)-10"),
        "bottom-center": ("(w-text_w)/2", "(h-text_h)-10"),
        "bottom-right": ("(w-text_w)-10", "(h-text_h)-10"),
    }
    pos_x, pos_y = POS_MAP.get(position, POS_MAP["bottom-center"])

    out_path = _safe_output_path(vp.stem + "_overlay")

    if overlay_type == "subtitle" and overlay_text:
        # 用 drawtext 滤镜叠加文字
        # 转义特殊字符
        safe_text = overlay_text.replace("'", "\\'").replace(":", "\\:")
        vf = (
            f"drawtext=text='{safe_text}':fontcolor=white:fontsize=28:"
            f"box=1:boxcolor=black@0.5:boxborderw=10:"
            f"x={pos_x}:y={pos_y}:fontfile=/Windows/Fonts/msyh.ttc"
        )
        r = _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(vp),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                out_path,
            ],
            timeout=300,
        )
    elif overlay_type in ("watermark", "pip") and image_path:
        ip = Path(image_path)
        if not ip.exists():
            return json.dumps({"error": f"叠加图片不存在: {image_path}", "success": False}, ensure_ascii=False)
        # 图片叠加
        ol_x = {
            "top-left": "10",
            "top-right": "W-w-10",
            "bottom-left": "10",
            "bottom-right": "W-w-10",
            "center": "(W-w)/2",
            "top-center": "(W-w)/2",
            "bottom-center": "(W-w)/2",
        }.get(position, "W-w-10")
        ol_y = {
            "top-left": "10",
            "top-right": "10",
            "top-center": "10",
            "bottom-left": "H-h-10",
            "bottom-right": "H-h-10",
            "bottom-center": "H-h-10",
            "center": "(H-h)/2",
        }.get(position, "H-h-10")
        r = _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(vp),
                "-i",
                str(ip),
                "-filter_complex",
                f"[1:v]scale=iw*0.3:ih*0.3[ol];[0:v][ol]overlay={ol_x}:{ol_y}",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                out_path,
            ],
            timeout=300,
        )
    else:
        return json.dumps({"error": f"不支持的叠加类型: {overlay_type}", "success": False}, ensure_ascii=False)

    if r.returncode != 0:
        err_msg = (r.stderr or "")[-500:]
        return json.dumps({"error": f"叠加失败: {err_msg}", "success": False}, ensure_ascii=False)

    return json.dumps(
        {
            "success": True,
            "output_path": out_path,
            "overlay_type": overlay_type,
            "position": position,
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具4: video_speed — 变速
# ============================================================


def execute_video_speed(video_path: str, speed: float = 1.0, project_name: str = "") -> str:
    """调整视频播放速度。

    Args:
        video_path: 本地视频路径
        speed: 速度倍率，0.25=4倍慢放, 0.5=2倍慢放, 1.0=原速, 2.0=2倍快放, 4.0=4倍快放
        project_name: 可选项目名
    """
    err = _check_ffmpeg()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    vp = Path(video_path)
    if not vp.exists():
        return json.dumps({"error": f"视频文件不存在: {video_path}", "success": False}, ensure_ascii=False)

    if speed <= 0:
        return json.dumps({"error": "速度倍率必须大于 0", "success": False}, ensure_ascii=False)

    prefix = project_name or vp.stem
    label = f"{speed}x".replace(".", "p")
    out_path = _safe_output_path(f"{prefix}_speed_{label}")

    # setpts 控制视频速度, atempo 控制音频速度
    v_pts = f"setpts={1 / speed}*PTS"
    # atempo 只能在 0.5-2.0 范围内，需要链式
    if 0.5 <= speed <= 2.0:
        a_tempo = f"atempo={speed}"
    elif speed < 0.5:
        # 链式 atempo (每段最多 2.0)
        a_tempo = f"atempo={speed * 2},atempo=0.5"
    else:
        a_tempo = f"atempo={speed / 2},atempo=2.0"

    r = _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(vp),
            "-filter_complex",
            f"[0:v]{v_pts}[v];[0:a]{a_tempo}[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            out_path,
        ],
        timeout=600,
    )

    if r.returncode != 0:
        err_msg = (r.stderr or "")[-500:]
        return json.dumps({"error": f"变速失败: {err_msg}", "success": False}, ensure_ascii=False)

    return json.dumps(
        {
            "success": True,
            "output_path": out_path,
            "speed": speed,
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具5: render_final — 多段视频+音频+转场一键成片
# ============================================================


def execute_render_final(
    video_segments: str,
    audio_path: str = "",
    transitions: str = "fade",
    bgm_path: str = "",
    project_name: str = "final",
) -> str:
    """将多个视频片段 + 音频 + 转场效果合成为最终成片。

    Args:
        video_segments: JSON 数组字符串，每个元素 {"path": "x.mp4", "duration": 5.0}
        audio_path: 旁白/配音音频文件路径
        transitions: 转场类型: "fade" 淡入淡出 / "dissolve" 交叉溶解 / "none" 无转场
        bgm_path: 背景音乐文件路径（可选）
        project_name: 项目名，用于输出命名
    """
    err = _check_ffmpeg()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    try:
        segments = json.loads(video_segments) if isinstance(video_segments, str) else video_segments
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"error": "video_segments 必须是 JSON 数组", "success": False}, ensure_ascii=False)

    if not segments:
        return json.dumps({"error": "video_segments 不能为空", "success": False}, ensure_ascii=False)

    # 验证文件
    for seg in segments:
        p = seg.get("path", "")
        if not p or not Path(p).exists():
            return json.dumps({"error": f"片段文件不存在: {p}", "success": False}, ensure_ascii=False)

    # 检查音频文件
    has_narration = audio_path and Path(audio_path).exists()
    has_bgm = bgm_path and Path(bgm_path).exists()

    out_path = _safe_output_path(project_name.replace(" ", "_"))

    if len(segments) == 1 and transitions == "none" and not has_narration and not has_bgm:
        # 最简单情况：直接复制 + 可选音频叠加
        seg_path = segments[0]["path"]
        cmd = ["ffmpeg", "-y", "-i", seg_path]
        if has_narration:
            cmd += ["-i", audio_path]
            cmd += [
                "-c:v",
                "copy",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                out_path,
            ]
        else:
            cmd += ["-c:v", "copy", "-c:a", "copy", out_path]
        r = _run(cmd, timeout=300)
    else:
        # 多段拼接 + 可选转场 + 音频混合
        # 步骤: 1) 拼接视频段（含转场）2) 混合音频
        concat_video = _safe_output_path("_temp_concat")

        # 先转码所有片段为统一格式 + 可选淡入淡出
        temp_segs = []
        for i, seg in enumerate(segments):
            tsp = _safe_output_path(f"_temp_seg_{i}")
            dur = seg.get("duration", 2.0)
            if transitions == "fade":
                fade_dur = min(0.5, dur / 4)
                r = _run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        seg["path"],
                        "-vf",
                        f"fade=in:0:d={fade_dur},fade=out:st={dur - fade_dur}:d={fade_dur}",
                        "-c:v",
                        "libx264",
                        "-crf",
                        "18",
                        "-preset",
                        "fast",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        tsp,
                    ],
                    timeout=120,
                )
            else:
                r = _run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        seg["path"],
                        "-c:v",
                        "libx264",
                        "-crf",
                        "18",
                        "-preset",
                        "fast",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        tsp,
                    ],
                    timeout=120,
                )
            if r.returncode == 0 and Path(tsp).exists():
                temp_segs.append(tsp)

        if not temp_segs:
            return json.dumps({"error": "所有片段预处理失败", "success": False}, ensure_ascii=False)

        # concat demuxer
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            for tsp in temp_segs:
                f.write(f"file '{Path(tsp).absolute().as_posix()}'\n")
            concat_list = f.name

        concat_video = _safe_output_path("_temp_video")
        r = _run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", concat_video], timeout=300
        )

        # 清理临时文件
        Path(concat_list).unlink(missing_ok=True)
        for tsp in temp_segs:
            Path(tsp).unlink(missing_ok=True)

        if r.returncode != 0:
            return json.dumps(
                {"error": f"视频拼接失败: {(r.stderr or '')[-300:]}", "success": False}, ensure_ascii=False
            )

        # 混合音频（旁白 + BGM）
        if has_narration or has_bgm:
            audio_inputs = []
            audio_maps = []
            filter_parts = []

            if has_narration:
                audio_inputs += ["-i", audio_path]
                audio_maps += ["-map", "1:a:0"]
                filter_parts.append("[1:a]volume=1.0[nar]")

            if has_bgm:
                idx = 2 if has_narration else 1
                audio_inputs += ["-i", bgm_path]
                audio_maps += ["-map", f"{idx}:a:0"]
                filter_parts.append(f"[{idx}:a]volume=0.3[bgm]")

            if has_narration and has_bgm:
                amix = "[nar][bgm]amix=inputs=2:duration=first:dropout_transition=2[outa]"
            elif has_narration:
                amix = "[nar]anull[outa]"
            else:
                amix = "[bgm]anull[outa]"

            af = ";".join(filter_parts) + ";" + amix
            cmd = (
                ["ffmpeg", "-y", "-i", concat_video]
                + audio_inputs
                + [
                    "-filter_complex",
                    af,
                    "-map",
                    "0:v:0",
                    "-map",
                    "[outa]",
                    "-c:v",
                    "libx264",
                    "-crf",
                    "18",
                    "-preset",
                    "medium",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-shortest",
                    "-movflags",
                    "+faststart",
                    out_path,
                ]
            )
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                concat_video,
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                out_path,
            ]

        r = _run(cmd, timeout=900)

        # 清理中间视频
        Path(concat_video).unlink(missing_ok=True)

        if r.returncode != 0:
            return json.dumps(
                {"error": f"最终渲染失败: {(r.stderr or '')[-300:]}", "success": False}, ensure_ascii=False
            )

    size = Path(out_path).stat().st_size
    return json.dumps(
        {
            "success": True,
            "output_path": out_path,
            "segment_count": len(segments),
            "transitions": transitions,
            "has_narration": has_narration,
            "has_bgm": has_bgm,
            "file_size_mb": round(size / 1024 / 1024, 2),
            "message": f"成片已输出: {out_path}",
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具定义（OpenAI function calling 格式）
# ============================================================

VIDEO_EDITOR_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "video_concat",
            "description": "将多段视频按顺序拼接成一段完整视频。所有片段会被转码为统一的H.264格式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_paths": {
                        "type": "string",
                        "description": 'JSON数组字符串，如 \'["a.mp4","b.mp4"]\'，按此顺序拼接',
                    },
                    "project_name": {"type": "string", "description": "可选项目名，用于输出文件命名"},
                },
                "required": ["video_paths"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "video_trim",
            "description": "剪辑视频的指定时间段。传入开始和结束秒数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件路径"},
                    "start_seconds": {"type": "number", "description": "开始时间（秒），默认0"},
                    "end_seconds": {"type": "number", "description": "结束时间（秒），-1=到结尾"},
                    "project_name": {"type": "string", "description": "可选项目名"},
                },
                "required": ["video_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "composite_overlay",
            "description": "在视频上叠加文字字幕或图片水印/画中画。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件路径"},
                    "overlay_type": {
                        "type": "string",
                        "description": "叠加类型: subtitle(文字字幕)/watermark(图片水印)/pip(画中画)",
                    },
                    "overlay_text": {"type": "string", "description": "字幕文字内容(subtitle模式)"},
                    "image_path": {"type": "string", "description": "叠加图片路径(watermark/pip模式)"},
                    "position": {
                        "type": "string",
                        "description": "位置: top-left/top-center/top-right/center/bottom-left/bottom-center/bottom-right",
                    },
                    "project_name": {"type": "string", "description": "可选项目名"},
                },
                "required": ["video_path", "overlay_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "video_speed",
            "description": "调整视频播放速度（快放/慢放）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "视频文件路径"},
                    "speed": {
                        "type": "number",
                        "description": "速度倍率: 0.25=4倍慢放, 0.5=2倍慢放, 1=原速, 2=2倍快放",
                    },
                    "project_name": {"type": "string", "description": "可选项目名"},
                },
                "required": ["video_path", "speed"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_final",
            "description": "将多个视频片段+音频+转场合成最终成片。这是制片管线的最后一步。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_segments": {
                        "type": "string",
                        "description": 'JSON数组，每个元素 {"path":"x.mp4","duration":5.0}',
                    },
                    "audio_path": {"type": "string", "description": "旁白/配音音频文件路径（可选）"},
                    "transitions": {
                        "type": "string",
                        "description": "转场: fade 淡入淡出 / dissolve 交叉溶解 / none 无",
                    },
                    "bgm_path": {"type": "string", "description": "背景音乐文件路径（可选）"},
                    "project_name": {"type": "string", "description": "项目名，用于输出命名"},
                },
                "required": ["video_segments"],
            },
        },
    },
]

# ============================================================
#  执行器映射
# ============================================================

VIDEO_EDITOR_EXECUTOR_MAP = {
    "video_concat": lambda **kw: execute_video_concat(
        video_paths=kw.get("video_paths", "[]"),
        project_name=kw.get("project_name", ""),
    ),
    "video_trim": lambda **kw: execute_video_trim(
        video_path=kw.get("video_path", ""),
        start_seconds=kw.get("start_seconds", 0),
        end_seconds=kw.get("end_seconds", -1),
        project_name=kw.get("project_name", ""),
    ),
    "composite_overlay": lambda **kw: execute_composite_overlay(
        video_path=kw.get("video_path", ""),
        overlay_type=kw.get("overlay_type", "subtitle"),
        overlay_text=kw.get("overlay_text", ""),
        image_path=kw.get("image_path", ""),
        position=kw.get("position", "bottom-center"),
        project_name=kw.get("project_name", ""),
    ),
    "video_speed": lambda **kw: execute_video_speed(
        video_path=kw.get("video_path", ""),
        speed=kw.get("speed", 1.0),
        project_name=kw.get("project_name", ""),
    ),
    "render_final": lambda **kw: execute_render_final(
        video_segments=kw.get("video_segments", "[]"),
        audio_path=kw.get("audio_path", ""),
        transitions=kw.get("transitions", "fade"),
        bgm_path=kw.get("bgm_path", ""),
        project_name=kw.get("project_name", "final"),
    ),
}
