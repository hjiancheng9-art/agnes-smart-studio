"""HTML 作品集画廊生成器

扫描 output/images/ + output/videos/ 和 output/history.json，
生成一个精美的离线 HTML 画廊页面，浏览器打开即可浏览全部作品。

功能：
- 图片缩略图网格（自动生成内联 base64 缩略图，纯离线无外部依赖）
- 视频记录展示（含 video_id/状态/链接）
- 筛选：全部/图片/视频/收藏
- 评分：点击星星打 1-5 分，数据回写 history.json + memory.json
- 收藏：点击❤️切换，数据回写 history.json
- 搜索：按 prompt 关键词搜索
- 统计面板：总数/评分分布/类型占比

输出：output/gallery.html（单文件，内嵌 CSS+JS+缩略图 data URI，完全离线）
"""

import base64
import os
import webbrowser
from datetime import datetime
from pathlib import Path

from core.config import OUTPUT_DIR

__all__ = ['GALLERY_FILE', 'THUMB_MAX', 'generate_gallery']


GALLERY_FILE = OUTPUT_DIR / "gallery.html"
THUMB_MAX = 320  # 缩略图最大边长 px


def _make_thumbnail(image_path: str) -> str | None:
    """生成 base64 缩略图 data URI（内嵌到 HTML，纯离线）"""
    try:
        from PIL import Image
        p = Path(image_path)
        if not p.exists():
            return None
        img = Image.open(p).convert("RGB")
        img.thumbnail((THUMB_MAX, THUMB_MAX), Image.Resampling.LANCZOS)
        import io
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64}"
    except (OSError, ValueError, TypeError):
        return None


def _type_icon(rtype: str) -> str:
    """记录类型 → 图标"""
    icons = {
        "text_to_image": "🖼️", "image_to_image": "🎨",
        "image_to_video": "🎬", "text_to_video": "🎬",
        "pipeline": "🔗", "variant": "🎲",
        "image_edit": "✂️",
    }
    return icons.get(rtype, "📄")


def _type_label(rtype: str) -> str:
    labels = {
        "text_to_image": "文生图", "image_to_image": "图生图",
        "image_to_video": "图生视频", "text_to_video": "文生视频",
        "pipeline": "流水线", "variant": "变种", "image_edit": "后期",
    }
    return labels.get(rtype, rtype)


def generate_gallery(filter_type: str = "all", open_browser: bool = True) -> str:
    """生成 HTML 画廊并可选打开浏览器。

    Args:
        filter_type: all/image/video/favorite
        open_browser: 是否自动打开浏览器

    Returns:
        生成文件的路径
    """
    from utils import history as _history
    records = _history.load_history()
    # 筛选有图片的记录 + 视频记录
    image_records = []
    video_records = []
    for r in records:
        lp = r.get("result", {}).get("local_path", "")
        rtype = r.get("type", "")
        if lp and Path(lp).exists():
            if "video" in rtype:
                video_records.append(r)
            else:
                image_records.append(r)
        elif "video" in rtype:
            video_records.append(r)

    # 按时间倒序
    image_records.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    video_records.sort(key=lambda r: r.get("created_at", ""), reverse=True)

    # 根据筛选条件选择
    if filter_type == "image":
        show_images, show_videos = image_records, []
    elif filter_type == "video":
        show_images, show_videos = [], video_records
    elif filter_type == "favorite":
        show_images = [r for r in image_records if r.get("favorited")]
        show_videos = [r for r in video_records if r.get("favorited")]
    else:  # all
        show_images, show_videos = image_records, video_records

    total_images = len(image_records)
    total_videos = len(video_records)
    total_fav = sum(1 for r in records if r.get("favorited"))
    total_rated = sum(1 for r in records if r.get("rating"))

    # 生成图片卡片 HTML
    image_cards_html = []
    for r in show_images:
        rid = r.get("id", "")
        lp = r.get("result", {}).get("local_path", "")
        prompt = (r.get("prompt", "") or "")[:120]
        model = r.get("model", "") or r.get("result", {}).get("model", "")
        created = r.get("created_at", "")[:16].replace("T", " ")
        rtype = r.get("type", "")
        icon = _type_icon(rtype)
        label = _type_label(rtype)
        fav = r.get("favorited", False)
        rating = r.get("rating", 0)
        seed = r.get("result", {}).get("seed", "")
        size = r.get("result", {}).get("size", "")

        thumb = _make_thumbnail(lp)
        thumb_attr = f'src="{thumb}"' if thumb else f'src="file:///{lp.replace(os.sep, "/")}"'

        # 评分星星
        stars_html = '<div class="stars">'
        for i in range(1, 6):
            filled = "★" if i <= rating else "☆"
            stars_html += f'<span class="star" data-id="{rid}" data-rating="{i}" onclick="rateItem(\'{rid}\',{i})">{filled}</span>'
        stars_html += "</div>"

        # 收藏状态
        fav_cls = "fav-btn active" if fav else "fav-btn"
        fav_html = f'<span class="{fav_cls}" data-id="{rid}" onclick="toggleFav(\'{rid}\')">❤️</span>'

        seed_html = f'<span class="meta">seed: {seed}</span>' if seed else ""

        card = f'''
        <div class="card" data-type="image" data-id="{rid}">
            <div class="card-img"><img {thumb_attr} alt="{prompt}" loading="lazy"></div>
            <div class="card-body">
                <div class="card-header">
                    <span class="type-badge">{icon} {label}</span>
                    <span class="card-time">{created}</span>
                </div>
                <div class="card-prompt" title="{prompt}">{prompt}</div>
                <div class="card-meta">
                    {seed_html}
                    <span class="meta">{model}</span>
                    <span class="meta">{size}</span>
                </div>
                <div class="card-actions">
                    {stars_html}
                    {fav_html}
                </div>
            </div>
        </div>'''
        image_cards_html.append(card)

    # 生成视频卡片 HTML
    video_cards_html = []
    for r in show_videos:
        rid = r.get("id", "")
        prompt = (r.get("prompt", "") or "")[:120]
        model = r.get("model", "")
        created = r.get("created_at", "")[:16].replace("T", " ")
        result = r.get("result", {})
        vid = result.get("video_id", "")
        status = result.get("status", "unknown")
        frames = result.get("num_frames", "")

        # 视频可能有本地文件或只有 video_id
        local_file = ""
        thumb = ""
        lp = result.get("local_path", "")
        if lp and Path(lp).exists():
            local_file = lp
            thumb = _make_thumbnail(lp)

        # 尝试找到对应的源图片（i2v 记录通常有 image 字段）
        src_img = result.get("image", "")
        if not thumb and src_img and src_img.startswith("data:image"):
            # 生成缩略图
            try:
                from PIL import Image
                import io
                _, b64data = src_img.partition(";base64,")
                img_bytes = base64.b64decode(b64data)
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                img.thumbnail((THUMB_MAX, THUMB_MAX), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=80)
                thumb = f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
            except (OSError, ValueError, TypeError):
                pass

        thumb_attr = f'src="{thumb}"' if thumb else ''
        if not thumb_attr:
            thumb_attr = 'src="" style="display:none"'

        status_colors = {"completed": "#4CAF50", "failed": "#F44336",
                         "submitted": "#FFC107", "processing": "#2196F3", "timeout": "#FF9800"}
        status_color = status_colors.get(status, "#9E9E9E")

        card = f'''
        <div class="card video-card" data-type="video" data-id="{rid}">
            <div class="card-img"><img {thumb_attr} alt="{prompt}" loading="lazy">
            <div class="video-badge" style="background:{status_color}">🎬 {status}</div></div>
            <div class="card-body">
                <div class="card-header">
                    <span class="type-badge">🎬 {created}</span>
                </div>
                <div class="card-prompt" title="{prompt}">{prompt}</div>
                <div class="card-meta">
                    <span class="meta">{model}</span>
                    {f'<span class="meta">{frames}帧</span>' if frames else ''}
                    {f'<span class="meta vid-id" title="点击复制">{vid[:20]}...</span>' if vid else ''}
                </div>
                {f'<a class="open-btn" href="file:///{local_file.replace(chr(92), "/")}" target="_blank">▶ 打开视频</a>' if local_file else ''}
            </div>
        </div>'''
        video_cards_html.append(card)

    # 统计
    rating_dist = [0] * 6
    for r in records:
        rt = min(5, max(0, r.get("rating", 0)))
        if rt > 0:
            rating_dist[rt] += 1

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 完整 HTML
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agnes Studio 作品集</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;background:#0d1117;color:#e6edf3;min-height:100vh}}
.header{{background:linear-gradient(135deg,#1a1e2e 0%,#0d1117 100%);padding:24px 32px;border-bottom:1px solid #30363d;position:sticky;top:0;z-index:100;backdrop-filter:blur(10px)}}
.header h1{{font-size:24px;font-weight:700;color:#58a6ff;margin-bottom:8px}}
.header h1 span{{color:#e6edf3}}
.stats{{display:flex;gap:20px;flex-wrap:wrap;margin-top:12px}}
.stat{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:8px 16px;font-size:14px}}
.stat strong{{color:#58a6ff;font-size:18px;display:block}}
.toolbar{{padding:16px 32px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #21262d}}
.toolbar button{{padding:6px 16px;border-radius:6px;border:1px solid #30363d;background:#21262d;color:#e6edf3;cursor:pointer;font-size:14px;transition:all .15s}}
.toolbar button:hover{{background:#30363d;border-color:#58a6ff}}
.toolbar button.active{{background:#1f6feb;border-color:#58a6ff;color:#fff}}
.search-box{{flex:1;min-width:200px;padding:6px 12px;border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:14px}}
.search-box::placeholder{{color:#484f58}}
.grid{{padding:20px 32px;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;overflow:hidden;transition:transform .15s,box-shadow .15s;cursor:default}}
.card:hover{{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.3)}}
.card-img{{position:relative;aspect-ratio:4/3;background:#0d1117;display:flex;align-items:center;justify-content:center;overflow:hidden}}
.card-img img{{width:100%;height:100%;object-fit:cover}}
.video-badge{{position:absolute;top:8px;right:8px;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;color:#fff}}
.card-body{{padding:12px}}
.card-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}}
.type-badge{{font-size:12px;color:#8b949e}}
.card-time{{font-size:12px;color:#484f58}}
.card-prompt{{font-size:13px;color:#c9d1d9;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.card-meta{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px}}
.meta{{font-size:11px;color:#484f58;background:#0d1117;padding:2px 6px;border-radius:4px}}
.vid-id{{cursor:pointer}}
.card-actions{{display:flex;align-items:center;gap:8px}}
.stars{{display:flex;gap:2px}}
.star{{font-size:18px;cursor:pointer;color:#484f58;transition:color .1s}}
.star:hover{{color:#f0c040}}
.star.rated{{color:#f0c040}}
.fav-btn{{font-size:18px;cursor:pointer;opacity:.4;transition:opacity .1s}}
.fav-btn.active{{opacity:1}}
.open-btn{{display:inline-block;padding:4px 12px;border-radius:6px;background:#1f6feb;color:#fff;text-decoration:none;font-size:12px;margin-top:6px}}
.open-btn:hover{{background:#388bfd}}
.empty{{text-align:center;padding:60px;color:#484f58;font-size:16px}}
.footer{{padding:20px 32px;text-align:center;color:#484f58;font-size:12px;border-top:1px solid #21262d}}
@media(max-width:600px){{.grid{{padding:12px;grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}}.header,.toolbar{{padding-left:16px;padding-right:16px}}}}
</style>
</head>
<body>

<div class="header">
    <h1>🎨 <span>Agnes Studio 作品集</span></h1>
    <div class="stats">
        <div class="stat"><strong>{total_images}</strong>图片</div>
        <div class="stat"><strong>{total_videos}</strong>视频</div>
        <div class="stat"><strong>{total_fav}</strong>收藏</div>
        <div class="stat"><strong>{total_rated}</strong>已评</div>
    </div>
</div>

<div class="toolbar">
    <button class="active" onclick="filter('all',this)">全部</button>
    <button onclick="filter('image',this)">🖼️ 图片</button>
    <button onclick="filter('video',this)">🎬 视频</button>
    <button onclick="filter('favorite',this)">❤️ 收藏</button>
    <input class="search-box" type="text" placeholder="🔍 搜索 prompt..." oninput="searchCards(this.value)">
</div>

<div class="grid" id="gallery">
{''.join(image_cards_html) if image_cards_html else '<div class="empty">暂无图片</div>'}
</div>

{'<h3 style="padding:20px 32px 0;color:#58a6ff">🎬 视频记录</h3><div class="grid">' + (''.join(video_cards_html) if video_cards_html else '<div class="empty">暂无视频</div>') + '</div>' if video_cards_html else ''}

<div class="footer">
    生成于 {now} | Agnes Smart Studio v3.0 | 数据来自 output/history.json
</div>

<script>
// 筛选
function filter(type, btn) {{
    document.querySelectorAll('.toolbar button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.card').forEach(card => {{
        const t = card.dataset.type;
        if (type === 'all') card.style.display = '';
        else if (type === 'favorite') card.style.display = card.querySelector('.fav-btn.active') ? '' : 'none';
        else card.style.display = t === type ? '' : 'none';
    }});
}}

// 搜索
function searchCards(q) {{
    q = q.toLowerCase();
    document.querySelectorAll('.card').forEach(card => {{
        const prompt = card.querySelector('.card-prompt')?.textContent.toLowerCase() || '';
        card.style.display = prompt.includes(q) ? '' : 'none';
    }});
}}

// 评分（存 localStorage + 尝试写回 Python 端）
function rateItem(id, rating) {{
    document.querySelectorAll(`.star[data-id="${id}"]`).forEach(s => {{
        s.classList.toggle('rated', parseInt(s.dataset.rating) <= rating);
        s.textContent = parseInt(s.dataset.rating) <= rating ? '★' : '☆';
    }});
    // 存到 localStorage（gallery 刷新时保留）
    const ratings = JSON.parse(localStorage.getItem('agnes_ratings') || '{{}}');
    ratings[id] = rating;
    localStorage.setItem('agnes_ratings', JSON.stringify(ratings));
}}

// 加载 localStorage 中的评分
(function loadRatings() {{
    try {{
        const ratings = JSON.parse(localStorage.getItem('agnes_ratings') || '{{}}');
        for (const [id, rating] of Object.entries(ratings)) {{
            document.querySelectorAll(`.star[data-id="${id}"]`).forEach(s => {{
                if (parseInt(s.dataset.rating) <= rating) {{
                    s.classList.add('rated');
                    s.textContent = '★';
                }}
            }});
        }}
    }} catch(e) {{}}
}})();

// 收藏（视觉切换，数据持久化需要刷新后同步）
function toggleFav(id) {{
    const btn = document.querySelector(`.fav-btn[data-id="${id}"]`);
    if (!btn) return;
    btn.classList.toggle('active');
    const favs = JSON.parse(localStorage.getItem('agnes_favs') || '[]');
    const idx = favs.indexOf(id);
    if (idx >= 0) favs.splice(idx, 1); else favs.push(id);
    localStorage.setItem('agnes_favs', JSON.stringify(favs));
}}

// 加载 localStorage 中的收藏
(function loadFavs() {{
    try {{
        const favs = JSON.parse(localStorage.getItem('agnes_favs') || '[]');
        favs.forEach(id => {{
            const btn = document.querySelector(`.fav-btn[data-id="${id}"]`);
            if (btn) btn.classList.add('active');
        }});
    }} catch(e) {{}}
}})();

// video_id 点击复制
document.querySelectorAll('.vid-id').forEach(el => {{
    el.addEventListener('click', () => {{
        const fullId = el.textContent.replace('...', '');
        navigator.clipboard?.writeText(fullId).then(() => {{
            const orig = el.textContent;
            el.textContent = '已复制!';
            setTimeout(() => el.textContent = orig, 1500);
        }});
    }});
}});
</script>
</body>
</html>'''

    # 写入文件
    GALLERY_FILE.parent.mkdir(parents=True, exist_ok=True)
    GALLERY_FILE.write_text(html, encoding="utf-8")

    if open_browser:
        webbrowser.open(f"file:///{GALLERY_FILE.as_posix()}")

    return str(GALLERY_FILE)
