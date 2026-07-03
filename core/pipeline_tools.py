"""一键流视频生成智能体 — 管道工具定义与执行器

Showrunner 总控脑调度这些工具完成端到端视频生产。
工具分为两类：
  - 思考型：由 CRUX 直接通过推理完成（分类、决策、文案重创、拆分镜等）
  - 执行型：需要实际代码操作（提取关键帧、保存文件、调用 API 等）
"""

import json
import re
import subprocess
from pathlib import Path

import httpx

__all__ = [
    "EXECUTOR_MAP",
    "MANIFEST_DIR",
    "OUTPUT_ROOT",
    "PIPELINE_TOOLS",
    "execute_check_file",
    "execute_decompose_to_storyboard",
    "execute_dependency_graph",
    "execute_extract_keyframes",
    "execute_fetch_url",
    "execute_list_files",
    "execute_mark_asset_ok",
    "execute_regenerate_asset",
    "execute_save_manifest",
]

# ── 项目输出根目录 ──
OUTPUT_ROOT = Path(__file__).parent.parent / "output"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# ── subprocess 安全封装（Windows GBK 编码防御）──


def _run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run 的安全封装，委托给 run_subprocess"""
    from core.mcp_servers._mcp_utils import run_subprocess as _rs
    kwargs.setdefault("timeout", 120)
    return _rs(cmd, **kwargs)


# ============================================================
#  管道工具定义（OpenAI function calling 格式）
# ============================================================

PIPELINE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "extract_video_keyframes",
            "description": "用 ffmpeg 场景检测从本地视频提取关键帧。自动找场景切换点（而非均匀采样），智能补密稀疏镜头。返回帧路径+时间区间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "本地视频文件的完整路径"},
                    "max_frames": {"type": "integer", "description": "最多提取帧数，默认 12", "default": 12},
                },
                "required": ["video_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_project_manifest",
            "description": "将当前项目的资产清单、分镜脚本、文案等内容保存为结构化 JSON 文件，用于生产进度跟踪和恢复。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "项目名称，用于创建输出目录"},
                    "manifest": {
                        "type": "object",
                        "description": "项目清单 JSON 对象，包含 phase/stage/assets/shots 等字段",
                    },
                },
                "required": ["project_name", "manifest"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_file_exists",
            "description": "检查指定文件路径是否存在，用于验证资产是否已生成或导入。",
            "parameters": {
                "type": "object",
                "properties": {"file_path": {"type": "string", "description": "要检查的文件路径"}},
                "required": ["file_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_project_files",
            "description": "列出当前项目的输出目录中的所有文件，用于进度检查。",
            "parameters": {
                "type": "object",
                "properties": {"project_name": {"type": "string", "description": "项目名称"}},
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url_content",
            "description": "获取在线 URL 的内容信息，用于处理视频链接类型的输入。返回页面标题、描述和可用的媒体信息。",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "要获取内容的在线 URL"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "regenerate_asset",
            "description": "重做项目中指定的单个资产（关键帧/角色/场景等），自动将依赖它的下游资产标记为blocked。不会影响其他不相关的资产和视频段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "项目名称"},
                    "asset_id": {"type": "string", "description": "要重做的资产ID，如 kf-03 或 char-01"},
                    "new_params": {"type": "string", "description": '新参数JSON，如 {"prompt": "偏暖色调"} 或 {}'},
                },
                "required": ["project_name", "asset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "project_dependency_graph",
            "description": "查看项目中所有资产的依赖关系图，包括每个节点的状态(done/pending/blocked/needs_redo)和父子关系。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "项目名称"},
                },
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_asset_ok",
            "description": "用户确认某个资产满意后，将其标记为done，并自动解除依赖它的下游blocked状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "项目名称"},
                    "asset_id": {"type": "string", "description": "资产ID"},
                },
                "required": ["project_name", "asset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "decompose_to_storyboard",
            "description": "将文案文本保存为项目清单的脚本字段，为后续拆资产/分镜准备数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "项目名称"},
                    "script_text": {"type": "string", "description": "完整文案文本"},
                },
                "required": ["project_name", "script_text"],
            },
        },
    },
]

# ============================================================
#  工具执行器
# ============================================================

# ── 视频分析常量（对齐新烬龙V2）──

_SENSITIVITY_TARGET_MAP = {
    # sensitivity → ideal shot duration (seconds per shot)
    85: 1.2,
    70: 1.45,
    55: 1.7,
    35: 1.85,
}
_DEFAULT_IDEAL_SHOT_SEC = 2.35
_SCENE_CANDIDATES = [0.3, 0.195, 0.135, 0.096, 0.16, 0.1, 0.075, 0.065, 0.06, 0.055, 0.04]
_MAX_OUTPUT_WIDTH = 960


def _probe_duration(video_path: str) -> float | None:
    """用 ffprobe 获取视频时长（秒）"""
    probe = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        timeout=15,
    )
    if probe.returncode != 0:
        return None
    try:
        return float(probe.stdout.strip())
    except (ValueError, TypeError):
        return None


def _detect_scene_cuts(video_path: str, threshold: float = 0.3) -> list[float]:
    """用 ffmpeg scene detect 找到场景切换时间点"""
    fps = 2.0  # 1/0.5s sample interval
    f = f"fps=fps={fps},select='gt(scene,{threshold})',showinfo"
    r = _run(["ffmpeg", "-hide_banner", "-i", video_path, "-filter:v", f, "-f", "null", "-"], timeout=60)
    text = (r.stdout or "") + "\n" + (r.stderr or "")
    import re

    times = []
    for m in re.finditer(r"pts_time:([0-9.]+)", text):
        try:
            t = float(m.group(1))
            if t > 0:
                times.append(t)
        except ValueError:
            pass
    return sorted({round(t, 3) for t in times})


def _build_shot_ranges(cut_times: list[float], duration: float, min_shot: float = 1.0) -> list[dict]:
    """把场景切换点转化为镜头区间"""
    valid = [t for t in cut_times if t > min_shot and t < duration - 0.1]
    boundaries = [0.0]
    for t in valid:
        if t - boundaries[-1] >= min_shot:
            boundaries.append(t)
    if duration - boundaries[-1] < min_shot and len(boundaries) > 1:
        boundaries.pop()
    boundaries.append(duration)
    return [
        {
            "id": i + 1,
            "startTime": round(boundaries[i], 3),
            "endTime": round(boundaries[i + 1], 3),
            "duration": round(max(0, boundaries[i + 1] - boundaries[i]), 3),
            "keyTime": round(boundaries[i] + max(0.08, (boundaries[i + 1] - boundaries[i]) / 2), 3),
        }
        for i in range(len(boundaries) - 1)
    ]


def _paced_ranges(duration: float, count: int) -> list[dict]:
    """均匀分镜（场景检测失败时的回退策略）"""
    c = max(1, count)
    step = duration / c
    return [
        {
            "id": i + 1,
            "startTime": round(i * step, 3),
            "endTime": round(duration if i == c - 1 else (i + 1) * step, 3),
            "duration": round(step, 3),
            "keyTime": round(i * step + step / 2, 3),
        }
        for i in range(c)
    ]


def _densify_ranges(ranges: list[dict], target: int, min_shot: float = 0.5) -> list[dict]:
    """镜头不够时，把长镜头拆分为多个 paced beat"""
    if len(ranges) >= target:
        return [dict(r, id=i + 1) for i, r in enumerate(ranges)]
    needed = target - len(ranges)
    parts = [1] * len(ranges)
    while needed > 0:
        best_i, best_score = -1, -1
        for i, r in enumerate(ranges):
            dur = r.get("duration", 0)
            if dur / (parts[i] + 1) < min_shot:
                continue
            score = dur / parts[i]
            if score > best_score:
                best_i, best_score = i, score
        if best_i < 0:
            break
        parts[best_i] += 1
        needed -= 1
    nid = 1
    result = []
    for i, r in enumerate(ranges):
        for j in range(parts[i]):
            s = r["startTime"] + j * r["duration"] / parts[i]
            e = r["startTime"] + (j + 1) * r["duration"] / parts[i]
            result.append(
                {
                    "id": nid,
                    "startTime": round(s, 3),
                    "endTime": round(e, 3),
                    "duration": round(max(0.08, e - s), 3),
                    "keyTime": round(s + (e - s) / 2, 3),
                    "parentRangeId": r.get("id"),
                }
            )
            nid += 1
    return result


def _target_shots(duration: float, sensitivity: int = 50) -> int:
    """根据时长和敏感度计算目标镜头数"""
    if duration <= 0:
        return 1
    ideal = _DEFAULT_IDEAL_SHOT_SEC
    for threshold, val in sorted(_SENSITIVITY_TARGET_MAP.items(), reverse=True):
        if sensitivity >= threshold:
            ideal = val
            break
    raw = max(1, round(duration / ideal))
    min_s = 1 if duration < 8 else 4 if duration < 15 else 10 if duration < 45 else 16
    max_s = 24 if duration <= 45 else 36 if duration <= 90 else 60
    return min(max_s, max(min_s, raw))


def execute_extract_keyframes(video_path: str, max_frames: int = 12, interval_seconds: float | None = None) -> str:
    """从视频中提取关键帧（对齐新烬龙V2场景检测策略）

    流程：场景检测 → 自适应阈值搜索 → 镜头补密 → ffmpeg 提取

    如果 ffmpeg 不可用，返回错误提示。
    """
    video = Path(video_path)
    if not video.exists():
        return json.dumps({"error": f"视频文件不存在: {video_path}", "success": False}, ensure_ascii=False)

    # 检查 ffmpeg
    try:
        _run(["ffmpeg", "-version"], timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return json.dumps(
            {"error": "未找到 ffmpeg", "success": False, "hint": "winget install ffmpeg 或 brew install ffmpeg"},
            ensure_ascii=False,
        )

    # 1. 获取时长
    duration = _probe_duration(str(video))
    if not duration or duration <= 0:
        return json.dumps({"error": "无法获取视频时长", "success": False}, ensure_ascii=False)

    # 2. 场景检测 + 自适应阈值
    sensitivity = 50
    target = min(_target_shots(duration, sensitivity), max_frames or 12)
    best_ranges, best_strategy = [], "paced_fallback"

    for th in _SCENE_CANDIDATES[:5]:  # 尝试前5个阈值
        cuts = _detect_scene_cuts(str(video), th)
        ranges = _build_shot_ranges(cuts, duration)[: target * 2]
        if ranges:
            best_ranges = ranges
            best_strategy = f"scene_threshold_{th}"
            # 接近目标镜头数就行
            if abs(len(ranges) - target) <= max(1, target // 3):
                break

    # 3. 失败回退 → 均匀分镜
    if not best_ranges:
        best_ranges = _paced_ranges(duration, target)
        best_strategy = "paced_fallback"

    # 4. 镜头不够 → 补密
    if len(best_ranges) < target:
        best_ranges = _densify_ranges(best_ranges, target)
        best_strategy += "_densified"

    # 5. 截取到目标帧数
    best_ranges = best_ranges[:target]

    # 6. ffmpeg 提取每一帧
    project = video.stem.replace(" ", "_")
    out_dir = OUTPUT_ROOT / "keyframes" / project
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    for r in best_ranges:
        fname = f"keyframe-{r['id']:03d}.jpg"
        out_path = out_dir / fname
        _run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(r["keyTime"]),
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                f"scale={_MAX_OUTPUT_WIDTH}:-2",
                "-q:v",
                "2",
                str(out_path),
            ],
            timeout=30,
        )
        if out_path.exists() and out_path.stat().st_size > 100:
            frames.append(
                {
                    "id": r["id"],
                    "path": str(out_path),
                    "keyTime": r["keyTime"],
                    "startTime": r.get("startTime", 0),
                    "endTime": r.get("endTime", 0),
                    "duration": r.get("duration", 0),
                }
            )

    return json.dumps(
        {
            "success": True,
            "video_path": str(video),
            "duration_seconds": round(duration, 1),
            "strategy": best_strategy,
            "frame_count": len(frames),
            "target_shots": target,
            "sensitivity": sensitivity,
            "frames": frames,
        },
        ensure_ascii=False,
    )


def execute_save_manifest(project_name: str, manifest: dict) -> str:
    """保存项目清单"""
    safe_name = project_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    out_dir = OUTPUT_ROOT / "projects" / safe_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # 添加时间戳
    from datetime import datetime

    manifest["saved_at"] = datetime.now().isoformat()
    manifest["project_name"] = project_name

    file_path = out_dir / "manifest.json"
    file_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return json.dumps(
        {"success": True, "project_name": project_name, "manifest_path": str(file_path), "output_dir": str(out_dir)},
        ensure_ascii=False,
    )


def execute_check_file(file_path: str) -> str:
    """检查文件是否存在"""
    p = Path(file_path)
    exists = p.exists()
    result = {
        "exists": exists,
        "path": str(p.absolute()),
        "is_file": p.is_file() if exists else False,
    }
    if exists and p.is_file():
        result["size_bytes"] = p.stat().st_size
        result["extension"] = p.suffix
    return json.dumps(result, ensure_ascii=False)


def execute_list_files(project_name: str) -> str:
    """列出项目文件"""
    safe_name = project_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    out_dir = OUTPUT_ROOT / "projects" / safe_name

    if not out_dir.exists():
        return json.dumps({"project_name": project_name, "exists": False, "files": []}, ensure_ascii=False)

    files = []
    for f in sorted(out_dir.rglob("*")):
        if f.is_file():
            files.append({"path": str(f.relative_to(out_dir)), "size_bytes": f.stat().st_size, "extension": f.suffix})

    return json.dumps(
        {"project_name": project_name, "exists": True, "total_files": len(files), "files": files}, ensure_ascii=False
    )


def execute_fetch_url(url: str) -> str:
    """获取 URL 内容信息"""
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=15)
        content_type = resp.headers.get("content-type", "")

        result = {
            "url": str(resp.url),
            "status_code": resp.status_code,
            "content_type": content_type,
            "content_length": len(resp.content),
            "is_video": any(t in content_type for t in ["video/", "application/octet-stream"]),
            "is_html": "text/html" in content_type,
        }

        # 如果是 HTML 页面，尝试提取标题
        if result["is_html"]:
            text = resp.text[:5000]
            title_match = re.search(r"<title>(.*?)</title>", text, re.IGNORECASE)
            if title_match:
                result["page_title"] = title_match.group(1).strip()

            # 提取 meta description
            desc_match = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', text, re.IGNORECASE
            )
            if desc_match:
                result["page_description"] = desc_match.group(1).strip()

        return json.dumps(result, ensure_ascii=False)

    except (httpx.HTTPError, OSError) as e:
        return json.dumps({"url": url, "error": str(e), "success": False}, ensure_ascii=False)


# ============================================================
#  文案→分镜自动拆解工具
# ============================================================


def execute_decompose_to_storyboard(project_name: str, script_text: str) -> str:
    """将文案文本保存为项目清单的脚本字段，为后续拆资产/分镜准备数据。

    实际解析和分镜生成由 CRUX LLM 推理完成；
    本工具将脚本持久化到 manifest，使管道可恢复。

    Args:
        project_name: 项目名称
        script_text: 完整文案文本（由用户提供或 CRUX 重创生成）
    """
    safe = project_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    out = MANIFEST_DIR / safe
    out.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(project_name) or {
        "project_name": project_name,
        "phase": "decompose",
        "stage": "script_locked",
        "assets": {},
        "keyframes": [],
        "shots": [],
        "video_segments": [],
    }

    manifest["script"] = script_text
    manifest["phase"] = "decompose"
    manifest["stage"] = "script_locked"
    _save_manifest(project_name, manifest)

    char_count = len(script_text)
    return json.dumps(
        {
            "success": True,
            "project_name": project_name,
            "script_length": char_count,
            "message": f"文案已锁定（{char_count}字）。下一步：基于文案拆资产/分镜。",
            "hint": "请分析文案中提取：角色(character)/场景(scene)/道具(prop)/载具(vehicle)，然后生成分镜列表(shots)。",
        },
        ensure_ascii=False,
    )


# ============================================================
#  资产依赖追踪系统
# ============================================================

MANIFEST_DIR = OUTPUT_ROOT / "projects"


def _load_manifest(project_name: str) -> dict | None:
    """加载项目清单"""
    safe = project_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    mf = MANIFEST_DIR / safe / "manifest.json"
    if mf.exists():
        try:
            return json.loads(mf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _save_manifest(project_name: str, manifest: dict):
    """保存项目清单"""
    safe = project_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    out = MANIFEST_DIR / safe
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def execute_regenerate_asset(project_name: str, asset_id: str, new_params: str = "{}") -> str:
    """重做单个资产，自动将下游标记为 blocked。

    Args:
        project_name: 项目名称
        asset_id: 要重做的资产 ID（如 "kf-03"、"char-01"）
        new_params: 新参数 JSON（如 {"prompt": "偏暖色调..."}）
    """
    manifest = _load_manifest(project_name)
    if not manifest:
        return json.dumps({"error": f"项目不存在: {project_name}", "success": False}, ensure_ascii=False)

    try:
        params = json.loads(new_params) if isinstance(new_params, str) else (new_params or {})
    except json.JSONDecodeError:
        params = {}

    assets = manifest.get("assets", {})
    if asset_id not in assets:
        # 搜索关键帧和资产列表
        all_ids = list(assets.keys())
        for key in ("keyframes", "shots", "video_segments"):
            for item in manifest.get(key, []):
                if isinstance(item, dict) and item.get("id") == asset_id:
                    all_ids.append(asset_id)
        return json.dumps(
            {
                "error": f"未找到资产: {asset_id}",
                "available_ids": all_ids[:20],
                "success": False,
            },
            ensure_ascii=False,
        )

    node = assets[asset_id]
    node["status"] = "needs_redo"
    if params:
        node["params_update"] = params

    # 标记所有下游为 blocked
    blocked = []
    depended_by = node.get("depended_by", [])
    for dep_id in depended_by:
        if dep_id in assets:
            assets[dep_id]["status"] = "blocked"
            blocked.append(dep_id)
        # 也检查关键帧和视频段
        for key in ("keyframes", "shots", "video_segments"):
            for item in manifest.get(key, []):
                if isinstance(item, dict) and item.get("id") == dep_id:
                    item["status"] = "blocked"
                    if dep_id not in blocked:
                        blocked.append(dep_id)

    manifest["assets"] = assets
    _save_manifest(project_name, manifest)

    return json.dumps(
        {
            "success": True,
            "asset_id": asset_id,
            "new_status": "needs_redo",
            "blocked_downstream": blocked,
            "message": f"资产 {asset_id} 已标记重做。{len(blocked)} 个下游资产已标记 blocked: {blocked}",
            "hint": "重新生成后自动解除 blocked 状态。其他不相关的资产和视频段不受影响。",
        },
        ensure_ascii=False,
    )


def execute_dependency_graph(project_name: str) -> str:
    """返回项目依赖图"""
    manifest = _load_manifest(project_name)
    if not manifest:
        return json.dumps({"error": f"项目不存在: {project_name}", "success": False}, ensure_ascii=False)

    assets = manifest.get("assets", {})
    nodes = []
    for aid, node in assets.items():
        nodes.append(
            {
                "id": aid,
                "type": node.get("type", "unknown"),
                "status": node.get("status", "unknown"),
                "path": node.get("path", ""),
                "depends_on": node.get("depends_on", []),
                "depended_by": node.get("depended_by", []),
            }
        )

    # 也包含关键帧和视频段
    for key in ("keyframes", "shots", "video_segments"):
        for item in manifest.get(key, []):
            if isinstance(item, dict):
                nodes.append(
                    {
                        "id": item.get("id", ""),
                        "type": key.rstrip("s"),
                        "status": item.get("status", "unknown"),
                        "path": item.get("path", ""),
                        "depends_on": item.get("depends_on", []),
                        "depended_by": item.get("depended_by", []),
                        "duration": item.get("duration", 0),
                    }
                )

    return json.dumps(
        {
            "success": True,
            "project_name": project_name,
            "total_nodes": len(nodes),
            "nodes": nodes,
            "status_summary": {s: sum(1 for n in nodes if n["status"] == s) for s in {n["status"] for n in nodes}},
        },
        ensure_ascii=False,
    )


def execute_mark_asset_ok(project_name: str, asset_id: str) -> str:
    """用户确认资产满意，标记 done，解除下游 blocked"""
    manifest = _load_manifest(project_name)
    if not manifest:
        return json.dumps({"error": f"项目不存在: {project_name}", "success": False}, ensure_ascii=False)

    assets = manifest.get("assets", {})
    if asset_id not in assets:
        return json.dumps({"error": f"未找到资产: {asset_id}", "success": False}, ensure_ascii=False)

    assets[asset_id]["status"] = "done"
    unblocked = []
    depended_by = assets[asset_id].get("depended_by", [])
    for dep_id in depended_by:
        if dep_id in assets:
            # 只有所有依赖都 done，才解除 blocked
            dep_node = assets[dep_id]
            deps = dep_node.get("depends_on", [])
            all_done = all(assets.get(d, {}).get("status") == "done" for d in deps)
            if all_done and dep_node["status"] == "blocked":
                dep_node["status"] = "pending"
                unblocked.append(dep_id)

    _save_manifest(project_name, manifest)

    return json.dumps(
        {
            "success": True,
            "asset_id": asset_id,
            "status": "done",
            "unblocked": unblocked,
            "message": f"资产 {asset_id} 已确认。{len(unblocked)} 个下游资产已解除 blocked: {unblocked}",
        },
        ensure_ascii=False,
    )


# ============================================================
#  工具名称 → 执行函数 映射表
# ============================================================

EXECUTOR_MAP = {
    "extract_video_keyframes": lambda **kw: execute_extract_keyframes(
        video_path=kw.get("video_path", ""),
        max_frames=kw.get("max_frames", 12),
        interval_seconds=kw.get("interval_seconds"),
    ),
    "save_project_manifest": lambda **kw: execute_save_manifest(
        project_name=kw.get("project_name", "untitled"), manifest=kw.get("manifest", {})
    ),
    "check_file_exists": lambda **kw: execute_check_file(file_path=kw.get("file_path", "")),
    "list_project_files": lambda **kw: execute_list_files(project_name=kw.get("project_name", "")),
    "fetch_url_content": lambda **kw: execute_fetch_url(url=kw.get("url", "")),
    "decompose_to_storyboard": lambda **kw: execute_decompose_to_storyboard(
        project_name=kw.get("project_name", ""),
        script_text=kw.get("script_text", ""),
    ),
    "regenerate_asset": lambda **kw: execute_regenerate_asset(
        project_name=kw.get("project_name", ""),
        asset_id=kw.get("asset_id", ""),
        new_params=kw.get("new_params", "{}"),
    ),
    "project_dependency_graph": lambda **kw: execute_dependency_graph(project_name=kw.get("project_name", "")),
    "mark_asset_ok": lambda **kw: execute_mark_asset_ok(
        project_name=kw.get("project_name", ""),
        asset_id=kw.get("asset_id", ""),
    ),
}
