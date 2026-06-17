# Agnes Smart Studio — 智能体工具平台

AI 生图/生视频 + 智能体主脑，29 命令 + 8 Skill + 12 工具 + 3 供应商 + 视觉独立通道。

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
| `/code` | 编程助手（切换模式，再次输入退出） |
| `/agent` | 智能体模式（加载 tools.json，再次输入退出） |
| `/plan <任务>` | 先规划再执行 |
| `/team [review\|debug\|feature]` | 智能体团队 |
| `/skill load <name>` | 加载技能包 |
| `/provider switch <name>` | 切换模型供应商 (agnes/deepseek/siliconflow) |
| `/vision <图> <问>` | 图片理解（独立视觉通道，始终可用） |
| `/deploy [vercel\|netlify\|github]` | 一键部署 |

完整列表: 输入 `/help`

## 操作提示

- 多行输入: 输入 `"""` 进入，再输入 `"""` 发送
- Ctrl+C 中止当前运行，再按一次退出聊天
- /code 或 /agent 再次输入即退出该模式
- 视觉始终走 Agnes 独立通道，不受供应商切换影响

## 技能库 (29 个)

### 原创文案 (5)
`copywriting-master` `comic-drama-writer` `story-copywriter` `novel-writer` `script-writer`

### 原创工具 (10)
`cinematic-master` `creative-engine` `video-pipeline` `self-evolution` `prompt-engineering` `creative-thinking` `python-expert` `debug-master` `api-designer` `shell-master`

### 新烬龙V2 迁移 (14)
`prompt-director` `visual-director` `storyboard-director` `motion-director` `asset-manager` `qc-inspector` `delivery-handoff` `core-showrunner` `creative-leap-pro` `cinematic-keyframe` `i2v-motion-rules` `negative-prompt-rules` `model-routing` `recovery-playbooks`

### 新烬龙流影工坊 (旧版) 迁移 (5)
`gaming-action-engine` `ip-adaptation-guard` `world-building-engine` `publishing-packager` `actor-craft`

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
