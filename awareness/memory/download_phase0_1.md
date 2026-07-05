# 下载器改造 — Phase 0 + Phase 1 完成

## Phase 0：冻结 nsp-downloader ✅
- `core/nsp-downloader/LEGACY.md` — 状态冻结，不再新增核心能力
- 盘点嗅探规则、配置体系、依赖链
- 最终迁移目标：`apps/nsp-downloader-legacy/`

## Phase 1：Python 下载引擎 ✅

### 新增文件

| 文件 | 说明 |
|------|------|
| `core/download/models.py` | DownloadRequest / DownloadJob / DownloadKind / JobStatus |
| `core/download/engines/aria2_engine.py` | aria2 JSON-RPC 引擎 (addUri/tellStatus/pause/remove) |
| `core/download/engines/ffmpeg_engine.py` | ffmpeg HLS/M3U8 下载 + 进度解析 |
| `core/download/engines/ytdlp_engine.py` | yt-dlp DASH/复杂站点下载 + JSON 进度 |
| `core/download/manager.py` | DownloadManager — 引擎选择 + 任务排队 + 轮询 + 单例 |
| `tools/download_tool.py` | TUI 命令 `/download` / `/downloads` |

### 引擎选择策略

| URL 特征 | 引擎 |
|----------|------|
| `.mp4` `.zip` `.exe` 直链 | aria2 (多线程分片) |
| `.m3u8` | ffmpeg (copy 模式) |
| YouTube / Bilibili / DASH | yt-dlp |
| 其他 | aria2 兜底 |

### TUI 命令

| 命令 | 效果 |
|------|------|
| `/download <url>` | 自动检测类型 → 选择引擎 → 排队执行 |
| `/download <url> --name xxx.mp4` | 指定文件名 |
| `/download <url> --dir D:/Videos` | 指定输出目录 |
| `/downloads` | 显示所有下载任务列表 |

### 验证
- ✅ 9 个新文件编译通过
- ✅ 51 个现有测试全过
- ✅ 4 项 smoke test 通过

## 下一阶段 (Phase 2+)
- Phase 2: TUI 下载进度面板 (activity 实时进度)
- Phase 3: browser-companion 合并嗅探 detector
- Phase 4: 配置迁移 → `~/.crux/download/config.toml`
- Phase 5: Electron 变可选富客户端
