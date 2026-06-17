---
name: launcher-menu-improvements
overview: 修复 launcher.py 菜单的 7 个问题：消除冗余模式、更新过期描述、新增创意飞跃/供应商切换/自诊断入口、增强快速生成和视频查询功能。
todos:
  - id: update-modes-dict
    content: 更新 MODES 字典：修正模式 2 描述为 "29个命令"，替换模式 4 为「创意飞跃」、模式 5 为「工具诊断」，更新模式 3 描述
    status: completed
  - id: update-mode2-texts
    content: 更新 main 函数中模式 2 启动前的提示文字（"24 个命令" → "29 个命令"）
    status: completed
    dependencies:
      - update-modes-dict
  - id: enhance-mode3-advanced
    content: 增强模式 3 快速生成：在类型选择后增加 --no-enhance / --creative / --submit-only / --steps 高级选项询问
    status: completed
    dependencies:
      - update-modes-dict
  - id: add-mode4-creative-leap
    content: 实现新模式 4 创意飞跃：输入描述、选类型（图片/视频）、可选创意方法，组装 --creative 命令行启动
    status: completed
    dependencies:
      - update-modes-dict
  - id: add-mode5-self-diagnose
    content: 实现新模式 5 工具诊断：包含语法检查、健康度诊断、项目结构展示、供应商信息查看
    status: completed
    dependencies:
      - update-modes-dict
  - id: enhance-mode6-auto-find
    content: 增强模式 6 视频查询：新增自动查找未完成任务选项，导入 query.find_pending_tasks 展示可选任务列表
    status: completed
    dependencies:
      - update-modes-dict
  - id: verify-and-test
    content: 最终检查：确认所有 "24个命令" 文字已更新、旧模式 4/5 逻辑已移除、菜单编号 0-8 不变、代码无语法错误
    status: completed
    dependencies:
      - enhance-mode3-advanced
      - add-mode4-creative-leap
      - add-mode5-self-diagnose
      - enhance-mode6-auto-find
---

## 用户需求

完善 `launcher.py` 的启动菜单，修复 7 个已确认问题，并检查上次修改是否已到位。

## 上次修改检查结论

经 git log 确认，最近两次 commit（fb1d31e、8969297）均未涉及 `launcher.py`，上次菜单修改未落地，处于待完善状态。

## 核心修改

- **清理冗余模式**：模式 4（图生图）和模式 5（图生视频）与模式 1（交互菜单）启动命令完全相同，仅提示文字不同，需替换为有价值的新功能入口
- **更新过期描述**：模式 2 描述为 "24个命令"，实际 CLI 的 `_chat_help` 已支持 29 个命令
- **新增创意飞跃模式**：暴露 `--creative / --leap / --methods` 参数入口
- **新增工具诊断模式**：暴露 `/self check`（语法检查）、`/self health`（健康度）、`/self files`（项目结构）
- **增强快速生成**：模式 3 新增 `--no-enhance`、`--creative`、`--steps`、`--submit-only` 选项询问
- **增强视频查询**：模式 6 新增自动从 `history.json` 查找未完成任务的功能（复用 `query.py` 的 `find_pending_tasks`）
- **供应商入口**：在工具诊断模式中展示当前模型供应商（读取 `models.json`）

## 约束

- 保持 9 个菜单选项（0-8）数量不变
- 仅修改 `launcher.py` 一个文件
- 复用现有颜色常量、辅助函数和 launch 机制

## 技术栈

- Python 3.10+
- 标准库：subprocess / os / sys / json / pathlib / datetime
- 项目内模块引用：query.find_pending_tasks （用于视频自动查找）

## 实现方案

### 整体策略

在 `launcher.py` 单文件内完成所有修改，不新增文件。通过替换冗余模式、增强已有模式、新增辅助函数来实现功能完善。保持与现有 `MODES` 字典 + `show_menu()` + `main()` 主循环的架构一致。

### 关键设计决策

1. **模式 4/5 替换方案**：将无实际功能的「图生图」「图生视频」替换为「创意飞跃」和「工具诊断」。这两个模式均使用 `launch()` 或内联实现，不引入新的 CLI 启动路径。

2. **模式 6 增强**：通过 `from query import find_pending_tasks` 导入已有函数，在启动器中增加 "1.手动输入 / 2.自动查找" 二级选择，复用 `query.py` 的成熟逻辑。

3. **工具诊断（模式 5）内联实现**：不启动完整 CLI，而是直接在 launcher 进程内执行检查，速度更快、输出更简洁：

- 语法检查：`subprocess` 调用 `ast.parse`
- 健康度：检查 API Key / Python 版本 / 依赖 / 使用统计
- 项目结构：`os.walk` + 树状输出
- 供应商信息：读取 `models.json`

4. **模式 3 高级选项**：保持现有类型选择（图片/视频/流水线）流程，在确认类型后增加额外询问，默认值保持原有行为不变。

### 性能与可靠性

- 模式 6 的 `find_pending_tasks` 仅在用户选择自动查找时执行，不影响正常菜单加载
- 模式 5 的语法检查使用 `subprocess` 独立进程，避免污染当前进程状态
- 所有新增输入均有默认值，回车跳过保持向后兼容

## 目录结构

```
agnes-smart-studio/
├── launcher.py          # [MODIFY] 本次唯一修改文件
│   - MODES 字典更新（模式 2 描述修正，模式 4/5 替换）
│   - 新增辅助函数：ask_creative_options / ask_advanced_options / run_self_check / run_self_health / show_provider_info
│   - show_menu 更新显示
│   - main 主循环中模式 3/4/5/6 的处理逻辑重写
│   - 所有 "24个命令" 文本更新为 "29个命令"
├── query.py             # [REFERENCE] find_pending_tasks() 被模式 6 导入使用
├── models.json          # [REFERENCE] 被模式 5 读取供应商信息
└── agnes_studio.py      # [REFERENCE] 命令行参数参考
```

## 实现要点

### 模式 3（快速生成）增强

在用户选择类型后、输入描述前，增加 4 个可选询问（均为 y/N，回车保持默认）：

- 关闭 Prompt 增强？→ 添加 `--no-enhance`
- 创意飞跃模式？→ 添加 `--creative`，进一步询问 `--methods`
- 仅提交不等待？（视频/流水线）→ 添加 `--submit-only`
- 推理步数？（视频）→ 添加 `--steps <value>`

### 模式 4（创意飞跃）

- 输入描述 → 选择类型（图片/视频）→ 可选输入创意方法（逗号分隔）→ 组装 `-q "prompt" --creative [--methods ...] [-v]` 启动

### 模式 5（工具诊断）

- 打印子菜单（1-4）：语法检查 / 健康度 / 项目结构 / 供应商信息
- 语法检查：`subprocess.run(["python", "-c", "import ast; ast.parse(open(path).read())"], ...)` 遍历 .py 文件
- 健康度：直接读取 `.env` 和 `SETTINGS.api_key`，检查 Python 版本、导入依赖、读取 memory 统计
- 项目结构：`os.listdir` + 简单树状输出
- 供应商：`json.load(open("models.json"))` 读取 `providers` 和 `active`

### 模式 6（视频查询）增强

- 用户选择后先显示子选项：1.手动输入 video_id / 2.自动查找未完成任务
- 选 2 时：`from query import find_pending_tasks` → 展示找到的任务 → 用户选择 → 用 `--video-id` 启动查询