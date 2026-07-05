# LEGACY — nsp-downloader

**Status**: Frozen. Not accepting new features.

## 为什么冻结

nsp-downloader 原本是一个独立的 Electron 桌面下载器（Electron + TypeScript + React + Vite），被整体放入 `core/` 目录。经过评估，它不应该以独立应用的形式长期存在于 CRUX 内核中。

## 迁移方向

下载能力将被拆为三层，逐步融入 CRUX Studio：

| 层 | 目标位置 | 状态 |
|---|---------|------|
| 浏览器嗅探 | `core/browser-companion/extension/detectors/` | ✅ Phase 3 已完成 |
| Python 下载引擎 | `core/download/` + `tools/download_tool.py` | ✅ Phase 1-2 已完成 |
| 富 UI (Electron) | `apps/nsp-downloader-legacy/` | ✅ Phase 5 已完成 |
## 当前保留原因

## 当前保留原因

1. Electron UI 仍是可选的富下载客户端
2. 站点适配调试工具
3. 用户熟悉的桌面入口
4. 扩展配套页面

## 不再做的事

- ❌ 不再在 nsp-downloader 中新增核心下载能力
- ❌ 不再维护独立于 CRUX 的配置体系 (electron-store)
- ❌ 不再维护独立的 TUI/CLI 入口

## 仍然做的事

- ✅ 作为可选富客户端读取 CRUX 下载列表
- ✅ 存量用户过渡期使用
- ✅ 浏览器扩展嗅探器 — 直到合并到 browser-companion

## 盘点清单

- [x] Electron + TypeScript + React + Vite 桌面应用
- [x] Manifest V3 浏览器扩展 (extension/)
- [x] `nsp_service.py` — HTTP 桥接服务 (port 4377)
- [x] M3U8/MP4 嗅探规则 → 已迁移至 browser-companion
- [ ] 网盘 (阿里云盘/百度云盘) 适配器 → 保留在 legacy 中
- [x] electron-store 配置 → 已由 CRUX `core/download/config.py` 接管
- [x] ffmpeg/aria2 调用方式 → 已在 `core/download/` 重建
