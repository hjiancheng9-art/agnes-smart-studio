# TUI 第 5 轮（最终轮）— Dashboard + 详情 + 扫尾

## 本轮改动

### 新文件
| 文件 | 说明 |
|------|------|
| `ui/panels/run_detail_panel.py` | `/run last` 和 `/run <id>` 详情面板 |
| `ui/panels/incident_detail_panel.py` | `/incident <id>` 完整详情+操作链接 |
| `ui/panels/system_status_panel.py` | Provider 健康状态 (+circuit breaker) |
| `ui/screens/dashboard_screen.py` | DashboardScreen 聚合屏框架 |

### tui_v2.py 改动
| 改动 | 说明 |
|------|------|
| `/dashboard` | 聚合 RunSummary + Incidents 显示 |
| `/run [id]` | 单条运行详情 |
| `/incident [id]` | 单条告警详情 |
| `/providers` | Provider 健康状态 |
| `Ctrl+C` | streaming 时=中断, idle时=提示Ctrl+Q |
| `Ctrl+Q` | 退出程序 |
| `_cancel_current_response()` | 中断当前响应 |

### theme_v2.py 改动
| 样式 | 说明 |
|------|------|
| provider-ok / provider-warn / provider-open / provider-half-open | Provider 健康色标 |

## TUI vs 后端匹配总表

| 维度 | 后端 | TUI | 状态 |
|------|------|-----|------|
| Chat/Streaming | ✅ | 流式输出+自动滚底+pinned | ✅ |
| Commands | ✅ | 全命令路由 | ✅ |
| RunSummary | ✅ | `/runs` 列表 + `/run` 详情 | ✅ |
| Incident | ✅ | `/incidents` 列表 + `/incident` 详情 | ✅ |
| ProviderRoute | ✅ | `/route last` | ✅ |
| ProviderHealth | ✅ | `/providers` | ✅ |
| ActivityLog | ✅ | 500条+F3行+F8展开 | ✅ |
| Dashboard | ✅ | `/dashboard` 聚合 | ✅ |
| Input queuing | ✅ | streaming 期间 Enter 暂存 | ✅ |
| Ctrl+C semantics | ✅ | streaming=中断, idle=提示 | ✅ |
| Scroll/Keyboard | ✅ | 鼠标滚轮+PgUp/PgDn+F8 | ✅ |
| Theme/Style | ✅ | 面板色标 | ✅ |
| **ReplayPanel** | CLI可用 | 富交互暂缓 (Textual) | ⏸ |
| **Textual迁移** | 预研 | 单独分支 | 📋 |

## 结论
**TUI 和后端已全匹配。** 还剩 ReplayPanel 富交互和 Textual 迁移是中期规划，不阻塞日常使用。
