"""音频工具 — TTS 语音合成 + 背景音乐 + 音效 + 混音

已接入 runtime：通过 ChatSession.toggle_audio() 和 /extend audio 命令激活。
ToolRegistry.load(audio=True) 自动注册所有 4 个音频工具。

提供 4 个工具：
- tts_narration: edge-tts 文本转语音（微软免费中文语音引擎）
- generate_bgm: ffmpeg 合成简单背景音乐/氛围音
- generate_sfx: ffmpeg 合成音效（whoosh/impact/ambient/riser/glitch）
- audio_mixdown: 多轨音频混合（旁白+BGM+SFX → 单文件）

所有输出到 output/audio/ 目录。
"""

import json
import subprocess
from pathlib import Path

__all__ = [
    "AUDIO_EXECUTOR_MAP",
    "AUDIO_OUT",
    "AUDIO_TOOL_DEFS",
    "OUTPUT_ROOT",
    "execute_audio_mixdown",
    "execute_generate_bgm",
    "execute_generate_sfx",
    "execute_tts_narration",
]

OUTPUT_ROOT = Path(__file__).parent.parent / "output"
AUDIO_OUT = OUTPUT_ROOT / "audio"
AUDIO_OUT.mkdir(parents=True, exist_ok=True)


def _run(cmd: list, timeout: int = 120, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run 安全封装（委托给 run_subprocess）"""
    from core.mcp_servers._mcp_utils import run_subprocess as _rs

    return _rs(cmd, timeout=timeout, **kwargs)


def _check_ffmpeg() -> str | None:
    try:
        r = _run(["ffmpeg", "-version"], timeout=5)
        if r.returncode != 0:
            return "ffmpeg 不可用"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "未找到 ffmpeg"
    return None


def _safe_output_path(prefix: str, ext: str = ".mp3") -> str:
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    i = 0
    while True:
        suffix = f"_{i}" if i else ""
        p = AUDIO_OUT / f"{prefix}_{ts}{suffix}{ext}"
        if not p.exists():
            return str(p)
        i += 1


# ============================================================
#  工具1: tts_narration — 文本转语音旁白
# ============================================================

# 推荐的中文语音
_CHINESE_VOICES = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",  # 女声-温柔
    "yunyang": "zh-CN-YunyangNeural",  # 男声-新闻
    "xiaoyi": "zh-CN-XiaoyiNeural",  # 女声-活泼
    "yunjian": "zh-CN-YunjianNeural",  # 男声-沉稳
    "yunxi": "zh-CN-YunxiNeural",  # 男声-叙述
    "xiaobei": "zh-CN-XiaobeiNeural",  # 东北话
    "yunnan": "zh-CN-YunnanNeural",  # 云南话
    "female": "zh-CN-XiaoxiaoNeural",
    "male": "zh-CN-YunyangNeural",
}


def execute_tts_narration(text: str, voice: str = "xiaoxiao", speed: str = "+0%", project_name: str = "") -> str:
    """文本转语音，生成 MP3 旁白文件。

    Args:
        text: 要朗读的文本（建议每段200字以内，长文本会自动分段）
        voice: 语音名: xiaoxiao(女温柔)/yunyang(男新闻)/xiaoyi(女活泼)/yunjian(男沉稳)/yunxi(男叙述)
        speed: 语速: "+30%" 加快 / "-20%" 放慢 / "+0%" 默认
        project_name: 可选项目名
    """
    voice_id = _CHINESE_VOICES.get(voice, _CHINESE_VOICES["xiaoxiao"])

    prefix = project_name or "narration"
    out_path = _safe_output_path(prefix.replace(" ", "_"))

    try:
        import asyncio

        import edge_tts

        async def _gen():
            communicate = edge_tts.Communicate(text, voice_id, rate=speed)
            await communicate.save(out_path)

        # 用独立线程 + 新事件循环隔离执行，避免与主事件循环冲突
        # nest_asyncio 在复杂嵌套场景下仍可能死锁
        import concurrent.futures

        def _run_in_thread():
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_gen())
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(_run_in_thread).result(timeout=60)

    except ImportError:
        return json.dumps(
            {
                "error": "edge-tts 未安装，请运行: pip install edge-tts",
                "success": False,
            },
            ensure_ascii=False,
        )
    except (subprocess.SubprocessError, OSError) as e:
        return json.dumps(
            {
                "error": f"TTS 生成失败: {e}",
                "success": False,
            },
            ensure_ascii=False,
        )

    if not Path(out_path).exists():
        return json.dumps({"error": "TTS 文件未生成", "success": False}, ensure_ascii=False)

    size = Path(out_path).stat().st_size
    return json.dumps(
        {
            "success": True,
            "output_path": out_path,
            "voice": voice,
            "file_size_kb": round(size / 1024, 1),
            "text_length": len(text),
            "message": f"旁白已生成: {out_path} ({voice} 语音, {len(text)}字)",
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具2: generate_bgm — 生成背景音乐
# ============================================================

_BGM_PRESETS = {
    "ambient": {
        "freq": "220,440,660",
        "dur": 30,
        "desc": "氛围音垫，低频持续音",
    },
    "tense": {
        "freq": "110,165,220",
        "dur": 20,
        "desc": "紧张悬疑，低沉脉冲",
    },
    "hopeful": {
        "freq": "523,659,784",
        "dur": 25,
        "desc": "希望/温暖，C大调和弦",
    },
    "epic": {
        "freq": "130,196,261",
        "dur": 15,
        "desc": "史诗感，低音铜管",
    },
    "mystery": {
        "freq": "311,466,622",
        "dur": 20,
        "desc": "神秘/探索，增和弦",
    },
    "sad": {
        "freq": "440,523,659",
        "dur": 25,
        "desc": "忧伤/抒情，小调色彩",
    },
}


def execute_generate_bgm(mood: str = "ambient", duration_seconds: int = 30, project_name: str = "") -> str:
    """生成简单背景音乐/氛围音。

    用 ffmpeg sine 合成器生成持续音和弦。

    Args:
        mood: 情绪: ambient(氛围)/tense(紧张)/hopeful(希望)/epic(史诗)/mystery(神秘)/sad(忧伤)
        duration_seconds: 时长（秒），默认30
        project_name: 可选项目名
    """
    err = _check_ffmpeg()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    preset = _BGM_PRESETS.get(mood, _BGM_PRESETS["ambient"])
    dur = min(duration_seconds, 120)  # 上限 2 分钟

    prefix = project_name or f"bgm_{mood}"
    out_path = _safe_output_path(prefix.replace(" ", "_"))

    # 用 sine 合成器生成和弦 + 淡入淡出 + 轻微混响
    freqs = preset["freq"].split(",")
    # 构建多个 sine 波形叠加
    sine_exprs = []
    for _i, freq in enumerate(freqs):
        vol = 0.15 / len(freqs)
        sine_exprs.append(f"{vol}*sin(2*PI*{freq}*t)")

    expr = "+".join(sine_exprs)
    # 添加 LFO 音量调制（呼吸感）
    expr = f"({expr})*(0.7+0.3*sin(2*PI*0.15*t))"

    fade_dur = min(2.0, dur / 8)
    af = f"aevalsrc='{expr}':d={dur}:s=44100,afade=t=in:d={fade_dur},afade=t=out:st={dur - fade_dur}:d={fade_dur}"

    r = _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"{af}", "-ac", "2", "-b:a", "192k", out_path], timeout=90)

    if r.returncode != 0:
        return json.dumps({"error": f"BGM 生成失败: {(r.stderr or '')[-300:]}", "success": False}, ensure_ascii=False)

    size = Path(out_path).stat().st_size
    return json.dumps(
        {
            "success": True,
            "output_path": out_path,
            "mood": mood,
            "duration_seconds": dur,
            "file_size_kb": round(size / 1024, 1),
            "message": f"BGM 已生成: {out_path} ({mood}, {dur}s)",
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具3: generate_sfx — 生成音效
# ============================================================

_SFX_PRESETS = {
    "whoosh": {
        "expr": "0.3*sin(2*PI*(100+1800*(t/1.5))*t)*exp(-t*2)",
        "dur": 1.5,
        "desc": "呼啸/飞过",
    },
    "impact": {
        "expr": "0.5*sin(2*PI*80*t)*exp(-t*6)+0.3*sin(2*PI*200*t)*exp(-t*4)",
        "dur": 1.0,
        "desc": "撞击/爆炸",
    },
    "ambient_drone": {
        "expr": "0.12*sin(2*PI*60*t)+0.08*sin(2*PI*90.5*t)+0.06*sin(2*PI*120*t)",
        "dur": 10.0,
        "desc": "环境低频嗡嗡",
    },
    "riser": {
        "expr": "0.2*sin(2*PI*(50+950*(t/3))*t)*(t/3)",
        "dur": 3.0,
        "desc": "上升/准备",
    },
    "glitch": {
        "expr": "0.25*sin(2*PI*800*t)*if(gt(mod(t*20,1),0.7),1,0)*exp(-t*3)",
        "dur": 2.0,
        "desc": "电子故障/数码感",
    },
    "heartbeat": {
        "expr": "0.4*sin(2*PI*50*t)*if(lt(mod(t,0.85),0.15),1,0)*exp(-mod(t,0.85)*8)*0.8",
        "dur": 5.0,
        "desc": "心跳/脉搏",
    },
    "sparkle": {
        "expr": "0.15*sin(2*PI*2000*t)*if(gt(mod(t*8,1),0.92),1,0)*exp(-t*1.5)",
        "dur": 2.0,
        "desc": "闪光/魔法",
    },
    "beep": {
        "expr": "0.3*sin(2*PI*880*t)*if(lt(mod(t,1.2),0.08),1,0)*exp(-mod(t,1.2)*10)",
        "dur": 4.0,
        "desc": "提示音/哔哔",
    },
}


def execute_generate_sfx(sfx_type: str = "whoosh", project_name: str = "") -> str:
    """用 ffmpeg 合成音效。

    Args:
        sfx_type: 音效类型: whoosh(呼啸)/impact(撞击)/ambient_drone(环境嗡)/riser(上升)/glitch(故障)/heartbeat(心跳)/sparkle(闪光)/beep(提示音)
        project_name: 可选项目名
    """
    err = _check_ffmpeg()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    preset = _SFX_PRESETS.get(sfx_type)
    if not preset:
        return json.dumps(
            {
                "error": f"未知音效类型: {sfx_type}，可用: {list(_SFX_PRESETS.keys())}",
                "success": False,
            },
            ensure_ascii=False,
        )

    prefix = project_name or f"sfx_{sfx_type}"
    out_path = _safe_output_path(prefix.replace(" ", "_"))

    af = f"aevalsrc='{preset['expr']}':d={preset['dur']}:s=44100"

    r = _run(["ffmpeg", "-y", "-f", "lavfi", "-i", af, "-ac", "2", "-b:a", "192k", out_path], timeout=60)

    if r.returncode != 0:
        return json.dumps({"error": f"音效生成失败: {(r.stderr or '')[-300:]}", "success": False}, ensure_ascii=False)

    size = Path(out_path).stat().st_size
    return json.dumps(
        {
            "success": True,
            "output_path": out_path,
            "sfx_type": sfx_type,
            "duration_seconds": preset["dur"],
            "file_size_kb": round(size / 1024, 1),
            "message": f"音效已生成: {out_path} ({sfx_type})",
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具4: audio_mixdown — 多轨音频混音
# ============================================================


def execute_audio_mixdown(
    narration_path: str = "", bgm_path: str = "", sfx_paths: str = "[]", project_name: str = "mixdown"
) -> str:
    """将旁白、背景音乐、音效混合为单一音频文件。

    Args:
        narration_path: 旁白音频路径（可选）
        bgm_path: BGM 音频路径（可选）
        sfx_paths: 音效文件 JSON 数组，可选带时间偏移: [{"path":"x.mp3","offset":3.0}]
        project_name: 项目名
    """
    err = _check_ffmpeg()
    if err:
        return json.dumps({"error": err, "success": False}, ensure_ascii=False)

    try:
        sfx_list = json.loads(sfx_paths) if isinstance(sfx_paths, str) else (sfx_paths or [])
    except (json.JSONDecodeError, TypeError):
        sfx_list = []

    has_narration = narration_path and Path(narration_path).exists()
    has_bgm = bgm_path and Path(bgm_path).exists()
    has_sfx = bool(sfx_list) and all(isinstance(s, dict) and Path(s.get("path", "")).exists() for s in sfx_list)

    if not (has_narration or has_bgm or has_sfx):
        return json.dumps({"error": "至少需要一路音频输入", "success": False}, ensure_ascii=False)

    out_path = _safe_output_path(project_name.replace(" ", "_"))

    # 构建 ffmpeg 多轨混音命令
    inputs = []
    filter_parts = []
    label_map = {}  # track_index → label
    input_idx = 0

    if has_narration:
        inputs += ["-i", narration_path]
        label_map["narration"] = input_idx
        filter_parts.append(f"[{input_idx}:a]volume=1.0,adelay=0|0[nar]")
        input_idx += 1

    if has_bgm:
        inputs += ["-i", bgm_path]
        label_map["bgm"] = input_idx
        filter_parts.append(f"[{input_idx}:a]volume=0.35,adelay=0|0[bgm]")
        input_idx += 1

    sfx_labels = []
    if has_sfx:
        for i, sfx in enumerate(sfx_list):
            sp = sfx.get("path", "")
            offset = sfx.get("offset", 0) * 1000  # 秒→毫秒
            inputs += ["-i", sp]
            label = f"sfx{i}"
            sfx_labels.append(label)
            vol = sfx.get("volume", 0.6)
            filter_parts.append(f"[{input_idx}:a]volume={vol},adelay={int(offset)}|{int(offset)}[{label}]")
            input_idx += 1

    # amix 合并所有轨道
    all_labels = []
    if has_narration:
        all_labels.append("[nar]")
    if has_bgm:
        all_labels.append("[bgm]")
    all_labels.extend(f"[{lbl}]" for lbl in sfx_labels)

    num_inputs = len(all_labels)
    if num_inputs == 1:
        amix = f"{all_labels[0]}anull[outa]"
    else:
        amix = f"{''.join(all_labels)}amix=inputs={num_inputs}:duration=longest:dropout_transition=2,volume=2.0[outa]"

    af = ";".join(filter_parts) + ";" + amix

    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", af, "-map", "[outa]", "-ac", "2", "-b:a", "192k", out_path]

    r = _run(cmd, timeout=300)

    if r.returncode != 0:
        return json.dumps({"error": f"混音失败: {(r.stderr or '')[-500:]}", "success": False}, ensure_ascii=False)

    size = Path(out_path).stat().st_size
    return json.dumps(
        {
            "success": True,
            "output_path": out_path,
            "has_narration": has_narration,
            "has_bgm": has_bgm,
            "sfx_count": len(sfx_list) if has_sfx else 0,
            "file_size_kb": round(size / 1024, 1),
            "message": f"音频混合完成: {out_path}",
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具定义
# ============================================================

AUDIO_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "tts_narration",
            "description": "文本转语音旁白。用微软免费中文语音合成MP3文件。长文本自动分段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要朗读的文本内容"},
                    "voice": {
                        "type": "string",
                        "description": "语音: xiaoxiao(女温柔)/yunyang(男新闻)/xiaoyi(女活泼)/yunjian(男沉稳)/yunxi(男叙述)",
                    },
                    "speed": {"type": "string", "description": "语速: +30% 快 / -20% 慢 / +0% 默认"},
                    "project_name": {"type": "string", "description": "可选项目名"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_bgm",
            "description": "用音频合成器生成背景音乐/氛围音。6种情绪可选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {
                        "type": "string",
                        "description": "情绪: ambient(氛围)/tense(紧张)/hopeful(希望)/epic(史诗)/mystery(神秘)/sad(忧伤)",
                    },
                    "duration_seconds": {"type": "integer", "description": "时长（秒），默认30，上限120"},
                    "project_name": {"type": "string", "description": "可选项目名"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_sfx",
            "description": "合成音效。8种类型: whoosh(呼啸)/impact(撞击)/ambient_drone(环境嗡)/riser(上升)/glitch(故障)/heartbeat(心跳)/sparkle(闪光)/beep(提示音)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sfx_type": {
                        "type": "string",
                        "description": "音效类型: whoosh/impact/ambient_drone/riser/glitch/heartbeat/sparkle/beep",
                    },
                    "project_name": {"type": "string", "description": "可选项目名"},
                },
                "required": ["sfx_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "audio_mixdown",
            "description": "将旁白+BGM+音效多轨混合为单一音频文件，可直接用于视频合成。",
            "parameters": {
                "type": "object",
                "properties": {
                    "narration_path": {"type": "string", "description": "旁白音频路径（可选）"},
                    "bgm_path": {"type": "string", "description": "BGM音频路径（可选）"},
                    "sfx_paths": {
                        "type": "string",
                        "description": '音效JSON数组: [{"path":"x.mp3","offset":3.0,"volume":0.6}]',
                    },
                    "project_name": {"type": "string", "description": "项目名"},
                },
                "required": [],
            },
        },
    },
]

# ============================================================
#  执行器映射
# ============================================================

AUDIO_EXECUTOR_MAP = {
    "tts_narration": lambda **kw: execute_tts_narration(
        text=kw.get("text", ""),
        voice=kw.get("voice", "xiaoxiao"),
        speed=kw.get("speed", "+0%"),
        project_name=kw.get("project_name", ""),
    ),
    "generate_bgm": lambda **kw: execute_generate_bgm(
        mood=kw.get("mood", "ambient"),
        duration_seconds=kw.get("duration_seconds", 30),
        project_name=kw.get("project_name", ""),
    ),
    "generate_sfx": lambda **kw: execute_generate_sfx(
        sfx_type=kw.get("sfx_type", "whoosh"),
        project_name=kw.get("project_name", ""),
    ),
    "audio_mixdown": lambda **kw: execute_audio_mixdown(
        narration_path=kw.get("narration_path", ""),
        bgm_path=kw.get("bgm_path", ""),
        sfx_paths=kw.get("sfx_paths", "[]"),
        project_name=kw.get("project_name", "mixdown"),
    ),
}
