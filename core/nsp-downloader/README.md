# nsp-downloader

Multi-threaded download accelerator powered by aria2.

## Development

```bash
npm install
npm run dev
```

## Encoding Policy

- Source code (TS/TSX/JS/HTML/CSS) is **ASCII only** -- no Chinese characters directly in source files.
- All Chinese text lives in `locales/zh-CN.json` and is referenced via `t('key')`.
- All files use **UTF-8 without BOM**; `.editorconfig` enforces `charset = utf-8`.
- Run `npm run scan` before committing to check for garbled characters.