---
default-active: true
---
# 自修契约 — 修自己，不断自己

## 动机
CRUX Studio 可以修改自身源码。历史踩坑：一次 audit 后 "fix" 把 `core/rules.py` 删了，
导致下次启动 system prompt 注入静默失败，无人察觉。工具型系统的自修必须在安全围栏内进行。

## 契约（DNA）
所有对 CRUX Studio 自身源码的修改必须遵循以下不变式：

### 写前四道锁
1. **只改 target，不动 neighbour** — 一次修改仅触及审计报告中列出的文件和行，不顺手重构无关代码。
2. **改前读，改后验** — 先用 `read_file` 确认当前内容，改完后立即 `ast.parse`（.py）或 `json.loads`（.json）校验语法。
3. **patch_file 优于裸写** — 跨文件修改用 `patch_file`，失败自动回滚；单文件小改用 `edit_file`，绝不用 `write_file` 覆写核心模块。
4. **不可逆操作需确认** — 删除文件（`Delete File`）、重命名、删除超过 5 行的逻辑，必须先列出影响面再等用户确认。

### 禁区（禁止操作）
- ❌ 删除 `core/` 下任何 `__init__.py` 或 `__all__` 中导出的模块文件
- ❌ 修改 `core/config.py` 的 `SETTINGS.dataclass_fields` 或 `save_global_auth` 签名
- ❌ 修改 `core/exceptions.py` 中 `CruxError` 基类的 `__init__` 或 `__str__`
- ❌ 修改 `core/encoding.py:setup()` — 编码初始化是启动第一道门
- ❌ 修改 `crux_studio.py` 的 `_SUBCOMMANDS` 键名或 `main()` 调用链
- ❌ 向 `requirements.txt` / `pyproject.toml:dependencies` 添加未验证的包
- ❌ 在 `except Exception: pass` 改成 `except Exception: logging.warning(...)` 时引入循环 import

### 修复约束（做"手术"，不做"拆迁"）
- 修复异常处理面太窄（如只捕 `OSError`）→ 加具体异常类型或兜底日志，不改成裸 `except:`
- 修复竞态 → 加 `threading.Lock` 或 `asyncio.Lock`，不重写并发模型
- 修复 API 双真源 → 统一到一个源，不引入第三个源
- 修复性能 → 加缓存/复用，不动调用方签名

### 自检清单（每次自修后必须回答）
1. `crux check` 是否仍然通过？
2. 改动文件是否在 `pyproject.toml` 的 `include` 列表中？
3. 改动是否会破坏 `ChatSession` / `AsyncChatSession` 的 `send_stream` yield 协议？
4. 如果改动了 `tool_defs`，ToolRegistry 的 `tool_names` 计数是否仍然一致？

## AI 行为规范（注入 system prompt）
- 自修时先告知用户"改了哪个文件、为什么改、怎么验证"
- 修改超过 3 个文件时，分批次提交，每批验证语法
- 不做"顺手优化"：审计发现 10 个问题 ≠ 一次全修，逐个文件确认
- 如果某次 edit_file 返回 "Not found"，停下来重新 read_file 确认内容，不盲改
