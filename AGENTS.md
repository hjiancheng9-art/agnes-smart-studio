# Agnes Smart Studio — 智能体工具平台

AI 生图/生视频 + 智能体主脑，24 命令 + 8 Skill + 12 工具 + 3 供应商。

> 本文是目录，详情见 docs/。技能写作规范见 docs/authoring.md

## 快速导航

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 安装与快速开始 |
| [FAQ.md](FAQ.md) | 常见问题 |
| [docs/architecture.md](docs/architecture.md) | 架构设计 |
| [docs/skills.md](docs/skills.md) | 技能目录 |
| [docs/commands.md](docs/commands.md) | 命令参考 |
| [docs/authoring.md](docs/authoring.md) | 技能/工具写作规范 |
| [docs/tools.md](docs/tools.md) | 外部工具配置 |

## 核心命令

| 命令 | 功能 |
|------|------|
| `/code` | 编程助手（自动 pro+thinking） |
| `/agent` | 智能体模式（加载 tools.json） |
| `/plan <任务>` | 先规划再执行 |
| `/team [review\|debug\|feature]` | 智能体团队 |
| `/skill load <name>` | 加载技能包 |
| `/provider switch <name>` | 切换模型供应商 |
| `/deploy [vercel\|netlify\|github]` | 一键部署 |

完整列表: 输入 `/help`

## 技能库 (8 个)

`cinematic-master` `creative-engine` `video-pipeline` `self-evolution` `prompt-engineering` `creative-thinking` `python-expert` `debug-master`

## 品质门禁

```bash
python -c "import ast; ... "      # 全项目语法检查
python -m pytest tests/ -q        # 单元测试（如有）
python agnes_studio.py -c          # 聊天模式 → /self check → /self health
```

## 规范

- 插件名: 小写+连字符 (creative-engine)
- Skill 文件: JSON 格式，name/description/prompt 必填
- 不提交 secrets，不执行危险 git 操作
- 代码英文，注释可中文，文件 UTF-8
