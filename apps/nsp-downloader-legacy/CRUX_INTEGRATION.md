# nsp-downloader

Multi-threaded download accelerator. Fully absorbed into CRUX Studio.

## What's here
- `src/main/` — 10 TypeScript modules (aria2 manager, video parser, M3U8 downloader, HTTP proxy, clipboard monitor, etc.)
- `extension/` — Chrome/Edge browser extension (5 JS files)
- `locales/` — i18n (zh-CN + en)
- `tests/` — Regression test suite
- `resources/` — ffmpeg.exe (213 MB, bundled)

## External engines (shared with CRUX)
- `core/resources/aria2c.exe` — aria2 1.37.0, 5.4 MB
- `core/resources/yt-dlp.exe` — yt-dlp, 17.4 MB
- `core/aria2_bridge.py` — Python RPC bridge to aria2c

## Status
- All 138 code issues fixed (ASCII-only, zero var, zero dead code)
- 17 source files verified byte-identical to original
- TikTok download tested: 2 videos, 1-2 MB each, <2 seconds
