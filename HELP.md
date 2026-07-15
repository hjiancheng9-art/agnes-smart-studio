# CRUX Studio — 命令参考 (auto-generated)

共 57 个命令

## 创意生产

| 命令 | 说明 |
|------|------|
| `/showrun <目标>` | 视频生成管线（通过 Agnes Video API） |
| `/agnes <模式>` | Agnes 多模态生成 (t2i/i2i/t2v/i2v/pipeline) |
| `/video <描述>` | 快速生成视频（支持图生视频，可 --size --duration） |
| `/img <描述>` | 快速生成图片（支持图生图，可 --size） |
| `/vision <图> <问>` | 图片理解（智谱 GLM-4V-Flash 主视觉） |

## 对话

| 命令 | 说明 |
|------|------|
| `/help` | 显示本帮助（/help /all 完整列表） |
| `/status` | 系统健康状态 |
| `/vote on|off` | 多模型表决开关（复杂问题自动并行咨询多个AI） |
| `/model <别名|ID>` | 切换 AI 模型 (light/pro/deepseek/zhipu...) |
| `/thinking` | 深度思考模式 |
| `/code` | 代码助手模式（再输退出） |
| `/agent` | 智能体模式（加载 tools.json 外部工具） |
| `/tools` | 查看已注册的工具列表 |
| `/skill <cmd>` | 技能包管理 (list/load/mode/unload/create) |
| `/浏览器` | 加载浏览器操控技能 (等同于 /skill load browser-control) |
| `/clear` | 清空对话历史 |
| `/exit` | 退出聊天 |
| `/copy [N]` | 复制最近N条对话到剪贴板 (Ctrl+Y) |
| `/browser` | Browser Companion 网页生成开关（8平台） |
| `/palette [filter]` | Command palette — fuzzy search all commands |

## 任务工程

| 命令 | 说明 |
|------|------|
| `/plan <任务>` | 先规划再执行（自动拆解步骤 + 用户审批） |
| `/sub <任务>` | 启动子智能体处理子任务 |
| `/compress` | 压缩长对话历史为摘要 |
| `/team <类型>` | 智能体团队 (review/debug/feature) |
| `/project <cmd>` | 项目管理 (new/save/load/analyze) |
| `/deploy <目标>` | 一键部署 (vercel/netlify/github) |
| `/todo [路径]` | 扫描项目 TODO/FIXME/HACK |
| `/commit` | 从 git diff 自动生成 commit 消息 |
| `/changelog` | 从 git log 生成 CHANGELOG.md |
| `/refactor <旧> <新>` | 批量重命名/替换 |

## 诊断配置

| 命令 | 说明 |
|------|------|
| `/self <cmd>` | 自诊断 (check/files/health/fix/audit) |
| `/audit <pip|npm>` | 依赖安全审计 + 过期检测 |
| `/rules <cmd>` | 编码规范管理 (list/enable/create) |
| `/automate <cmd>` | 自动化定时任务 (add/list/remove) |
| `/permission <yolo|auto|manual>` | 切换权限模式 (YOLO/自动/手动) |
| `/tasks` | 查看后台任务状态 |
| `/provider <cmd>` | 切换模型供应商 (list/switch) |
| `/evolve` | 查看 Prompt 进化状态 |
| `/done [quick]` | 完成前验证 (pytest+ruff+pyright+git diff) |
| `/method [reset]` | 查看当前任务的方法论遵守状态 (A/B/C/D 分级 + Plan/基线/Worktree/TDD) |
| `/know <cmd>` | 浏览内置知识库 (methods/templates/domain) |
| `/health` | 工具质量评分 + 系统健康面板 |
| `/rollback` | 回滚最近一次代码修改 |
| `/trends [cost|tools|quality]` | 历史趋势分析（消费/工具健康/质量） |
| `/docs [help|agents|manifest|all]` | 从代码自动生成文档 |
| `/prompt-stats` | Prompt Lab 实验统计 |
| `/prompt-assign <变体ID>` | 指定 Prompt Lab 变体 |
| `/cost [budget <usd>|reset]` | 查看花费统计 / 设日预算 / 清零 |
| `/eval [json]` | 运行智能体质量基准测试 |
| `/extend <notebook|audio|browser|list>` | 切换扩展工具集（notebook/audio/browser） |
| `/trace [run_id|list]` | 查看执行轨迹，排查问题 |
| `/mcp <cmd>` | MCP 服务器管理 (list/add/remove/connect/disconnect/tools) |

## 工具

| 命令 | 说明 |
|------|------|
| `/tidy [deep]` | 整理根目录临时文件到 tmp/ 子目录 |

## 智能体转换

| 命令 | 说明 |
|------|------|
| `/trae-convert <agent.json>` | 导入 trae agent → CRUX skill.json |
| `/trae-export <skill.json> [output.json]` | 导出 CRUX skill → trae agent 格式 |
| `/trae-batch <input_dir> [output_dir]` | 批量转换 trae agents → skills |
| `/trae-new <name> [description]` | 手动创建 trae 风格 skill |

---
*83 tools, 99 skills, 241 core modules, 158 test files*