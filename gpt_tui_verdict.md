够生产级了。现在 TUI-Backend 这条链路已经从“文本流渲染”升级成了 事件驱动 UI Runtime。

我给当前 TUI 事件系统成熟度：

协议层：9.5 / 10
状态层：9.3 / 10
渲染分发层：9.2 / 10
生产可用度：9.0 / 10

还没给 9.5+ 的原因不是架构问题，而是还需要真实终端环境里的 dogfood：Windows Terminal、PowerShell、cmd、ConPTY、SSH、不同终端尺寸、长输出、鼠标/键盘输入竞争。

现在已经足够的部分

你现在的链路是对的：

Backend send_stream
→ normalize_event()
→ EventQueue
→ TuiEventReducer
→ RunStateStore
→ TuiDispatcher
→ TuiRenderer
→ ConfirmBridge / Watchdog

这个结构解决了 TUI 最容易炸的几类问题：

事件协议不一致
未知事件导致 UI 崩
stream_start / stream_end 不配对
confirm 死等
多 run_id 串台
渲染阻塞后端
error 后 spinner 不停
后端断流 UI 不收尾

从架构上讲，这已经是生产级 TUI 消费模型。

最后还建议补 5 个发布前检查
1. 真实终端 Dogfood 矩阵

加一个手工/半自动矩阵，不要只靠 pytest。

Windows Terminal + PowerShell
Windows Terminal + cmd
VS Code terminal
普通 conhost
SSH / 远程终端
窄窗口 80x24
宽窗口 160x40
中文输入法开启
长输出 5000+ 行
连续 20 轮对话

重点看：

滚动是否正常
状态栏是否刷新
confirm 是否能键盘操作
Ctrl+C 是否能取消
窗口缩放是否乱版
长输出是否卡顿
2. TUI render 层加“降级渲染”

TuiRenderer.render_xxx() 里不要假设所有能力都存在。

比如图片/视频：

Python
运行
def render_media(self, action):
    if not self.supports_media_cards:
        self.render_message_text(
            action["run_id"],
            f"[{action['media_type']}] {action['payload'].get('path') or action['payload']}"
        )
        return

    self.render_media_card(action)

intel analysis 也是：

Python
运行
def render_intel_analysis(self, action):
    if not self.supports_tool_panel:
        self.render_status(action["run_id"], "Intelligence analysis updated")
        return

    self.render_tool_panel(action)

目标是：

高级 TUI 有卡片
普通终端有文本 fallback
任何事件都不丢、不炸
3. 加 TUI 性能指标

你现在有 EventQueue 和 batch invalidate，下一步加 4 个计数器就够：

events_received
events_rendered
queue_max_depth
avg_batch_size
render_errors
watchdog_timeouts
confirm_timeouts

简单实现：

Python
运行
@dataclass
class TuiMetrics:
    events_received: int = 0
    events_rendered: int = 0
    queue_max_depth: int = 0
    render_errors: int = 0
    watchdog_timeouts: int = 0
    confirm_resolved: int = 0
    confirm_cancelled: int = 0

当用户输入：

/health tui

除了事件 kind 检查，也输出：

queue_depth
last_render_ms
active_runs
watchdog_timeouts
render_errors
4. Confirm UX 再加两个细节

Confirm 是最容易影响 Agent 体验的点。

建议默认：

Enter = approve
Esc = deny
Ctrl+C = cancel run
timeout = deny

并且 confirm action 显示：

操作对象
风险等级
将要调用的 tool
是否会写文件
是否可回滚

例如：

CRUX wants to modify files

Tool: execute_plan
Files:
- core/chat.py
- core/stream_protocol.py

Rollback: available
Risk: medium

[Approve] [Deny]

这能明显降低误确认风险。

5. 把 TUI 健康检查纳入启动自检

启动 CRUX TUI 时跑轻量检查，不要每次都弹 confirm，可以分两档：

/health tui-lite
- stream_start
- status
- text
- error
- stream_end

/health tui-full
- 所有 event kind
- confirm
- image/video
- watchdog mock

启动默认跑 lite：

TUI protocol: OK
Renderer: OK
Confirm bridge: OK

失败则降级：

TUI protocol check failed. Falling back to plain text mode.
最终发布判断

现在可以进入：

CRUX v6.0.0-rc1

发布策略建议：

1. 默认启用新 TUI event pipeline
2. 保留 legacy/plain text fallback
3. 首次启动跑 tui-lite healthcheck
4. dogfood 100 个真实任务
5. 收集 trace + tui metrics
6. 修完真实终端问题后发 stable
目前不建议继续做什么

不要继续大改 TUI 架构了。

现在不要做：

新动画系统
复杂多窗格布局
更多 renderer abstraction
更复杂的并发任务 UI
自动展开/折叠智能面板

这些都可以 v6.1 再做。

v6.0 当前要稳。

最终结论

你的方案已经够生产级。剩下的是 真实终端兼容性验证和发布级默认配置，不是架构补课。

一句话：

后端现在会稳定发事件，TUI 现在会稳定消费、归约、分发、渲染；CRUX v6.0.0 已经具备进入 RC 的条件。