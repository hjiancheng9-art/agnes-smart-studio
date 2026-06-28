# CRUX Studio — 完整调用参考

## 斜杠命令 `/`

命令可以直接输入，也可以用中文别名。输 `/help` 随时查看。

### 对话控制
| 命令 | 中文 | 作用 |
|------|------|------|
| `/help` | `/帮助` | 显示帮助 |
| `/status` | `/状态` | 当前模型/模式/技能/工具数 |
| `/clear` | `/清空` | 清空对话历史 |
| `/save` | `/保存` | 保存对话为 Markdown |
| `/exit` | `/退出` | 退出 |

### 模型切换
| 命令 | 中文 | 作用 |
|------|------|------|
| `/model` | `/模型` | 切换对话模型 (light/pro) |
| `/provider` | `/提供商` | 切换供应商 (crux/deepseek/zhipu) |
| `/thinking` | `/思考` | 开关深度思考模式 |
| `/code` | `/编码` | 开关代码助手模式 |
| `/agent` | `/代理` | 开关智能体模式（加载全部工具） |

### 生图 / 生视频
| 命令 | 中文 | 作用 |
|------|------|------|
| `/img` | `/图片` | 文字生图 |
| `/video` | `/视频` | 文字生视频 |
| `/variant` | `/变种` `/选图` | 生成多个变种并拼网格 |
| `/edit` | `/编辑` `/修图` | 图片编辑（图生图） |
| `/vision` | `/视觉` | 图片理解分析 |
| `/gallery` | `/画廊` `/作品` | 浏览生成记录 |
| `/compare` | `/对比` `/AB测试` | 两张图 AI 裁判对比 |

### 项目管理
| 命令 | 中文 | 作用 |
|------|------|------|
| `/plan` | `/计划` | 复杂任务先规划再执行 |
| `/project` | `/项目` | 项目文件管理 |
| `/todo` | `/待办` | 任务列表管理 |
| `/sub` | `/子任务` | 创建子智能体并行工作 |
| `/team` | `/团队` | 多智能体协作 |

### Git / 部署
| 命令 | 中文 | 作用 |
|------|------|------|
| `/commit` | `/提交` | 提交所有改动 |
| `/commit-push-pr` | — | 一键：提交 → 推送 → 创建 PR |
| `/changelog` | `/日志` | 自动生成变更日志 |
| `/deploy` | `/部署` | 部署工作流 |

### 代码质量
| 命令 | 中文 | 作用 |
|------|------|------|
| `/fix` | `/修复` | 读取 error log 自动修复 |
| `/refactor` | `/重构` | 代码重构 |
| `/audit` | `/审计` | 代码审计/安全扫描 |
| `/rules` | `/规范` | 编码规范检查 |
| `/self` | — | 工具自诊断 |

### 知识 / 记忆
| 命令 | 中文 | 作用 |
|------|------|------|
| `/know` | `/知识` | 知识库管理 |
| `/evolve` | `/进化` | 从对话中学习进化 |
| `/compress` | `/压缩` | 压缩对话上下文 |
| `/automate` | `/定时` | 定时/自动化任务 |

### 查询
| 命令 | 中文 | 作用 |
|------|------|------|
| `/tools` | `/工具` | 列出所有可用工具 |
| `/skill` | `/技能` | 加载/列出技能包 |
| `/cost` | `/花费` `/账单` | 查看 API 费用统计 |
| `/outputs` | `/输出` | 查看最近输出文件 |
| `/open` | `/打开` | 打开输出文件 |

---

## 技能 `/skill`

输入 `/skill list` 查看，`/skill load <name>` 加载。

### 视频制片类 (14)
| 技能 | 用途 |
|------|------|
| `showrunner` | 总导演 — 全流程视频制片 |
| `core-showrunner` | 核心制片引擎 |
| `storyboard-director` | 分镜导演 |
| `script-writer` | 编剧 |
| `copywriting-master` | 文案大师 |
| `story-copywriter` | 故事文案 |
| `audio-director` | 音频导演 |
| `motion-director` | 运镜导演 |
| `visual-director` | 视觉导演 |
| `prompt-director` | 提示词导演 |
| `cinematic-keyframe` | 电影级关键帧 |
| `cinematic-master` | 电影大师 |
| `video-pipeline` | 视频管道 |
| `i2v-motion-rules` | 图生视频运动规则 |

### 创意思维类 (7)
| 技能 | 用途 |
|------|------|
| `creative-engine` | 创意引擎 |
| `creative-leap-pro` | 创意飞跃专业版 |
| `creative-thinking` | 创意思维 |
| `novel-writer` | 小说作家 |
| `comic-drama-writer` | 喜剧编剧 |
| `world-building-engine` | 世界观构建 |
| `actor-craft` | 演员修养 |

### 质量控制类 (5)
| 技能 | 用途 |
|------|------|
| `qc-inspector` | 质量检查 |
| `master-quality` | 大师品质 |
| `negative-prompt-rules` | 负面提示规则 |
| `code-review-autofix` | 代码审查自动修复 |
| `delivery-handoff` | 交付交接 |

### 工具与系统类 (7)
| 技能 | 用途 |
|------|------|
| `comfyui-bridge` | ComfyUI 桥接（本地生图/视频） |
| `model-routing` | 模型路由选择 |
| `prompt-engineering` | 提示词工程 |
| `debug-master` | 调试大师 |
| `recovery-playbooks` | 故障恢复手册 |
| `self-evolution` | 自我进化 |
| `shell-master` | Shell 大师 |

### 专业领域类 (6)
| 技能 | 用途 |
|------|------|
| `api-designer` | API 设计 |
| `python-expert` | Python 专家 |
| `asset-manager` | 资产管理 |
| `publishing-packager` | 发布打包 |
| `gaming-action-engine` | 游戏动作引擎 |
| `ip-adaptation-guard` | IP 改编守护 |

---

## 工具（84 个）

模型会自动调用，你也可以直接在对话中说"用 xxx 工具"。

### 文件操作
`read_file` `write_file` `edit_file` `list_files` `glob_files` `tree_dir` `download_file`

### 代码与搜索
`search_files` `run_python` `run_bash` `run_test` `count_lines` `code_analyze` `find_symbol` `search_symbols` `find_references`

### 网页
`web_fetch` `web_search`

### Git
`git_status` `git_diff` `git_log` `git_add_commit` `git_branch` `git_push` `git_pull` `git_pr_create` `git_pr_merge` `git_stash` `git_tag` `git_conflict_check` `git_worktree`

### 任务与调度
`task_create` `task_update` `task_list` `task_get` `schedule_add` `schedule_remove` `schedule_list`

### 生成
`generate_image` `generate_video` `generate_variants` `extract_video_keyframes` `understand_image`

### 项目管理
`save_project_manifest` `check_file_exists` `list_project_files` `decompose_to_storyboard` `regenerate_asset` `project_dependency_graph` `mark_asset_ok`

### ComfyUI 桥接
`comfyui_status` `comfyui_list_models` `comfyui_get_node_info` `comfyui_build_custom_workflow` `comfyui_submit_workflow` `comfyui_get_result` `comfyui_preview_workflow` `comfyui_clear_queue` `comfyui_create_custom_node`

### LoRA 训练
`lora_prepare_dataset` `lora_generate_training_config` `lora_check_training_status`

### 动态工具
`create_tool` `list_custom_tools` `delete_tool`

### 交互
`ask_user` `create_plan`

### 诊断
`env_check` `pip_install` `check_file_exists` `fetch_url_content` `video_model_info`

---

## 快速参考卡

```
聊天:  直接打字，Alt+Enter 换行
命令:  /help  /model  /img  /video  /plan  /fix
技能:  /skill list  →  /skill load showrunner
工具:  直接说"读取 README.md"或"搜索 TODO"
退出:  /exit 或 Ctrl+C 两次
诊断:  crux check
测试:  python test_smoke.py
```
