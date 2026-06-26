"""灵兽谱 — 十大灵宠·常伴左右。

灵兽 = 常驻守护进程/事件监听器/自治模块 — 不须召唤，始终在线。

  看门狗   · Watchdog        — 四线监控·自动告警·死则唤醒
  常驻灵   · Daemon          — IPC 管道常驻·守护 CRUX 在线
  传讯雀   · EventBus        — 五兽神经·发布订阅·零耦合
  守时鹤   · Scheduler       — 定时任务·cron/interval 双模
  鉴宝鼠   · CapRegistry     — 能力注册·运行时校验·自动降级
  品鉴蜂   · Scorecard       — 工具评分·静态+运行时双层
  守财兽   · CostTracker     — 花费追踪·预算守卫·按模型按天
  记忆蝶   · SemanticMemory  — 跨会话记忆·偏好学习·越用越懂
  阵灵     · PipelineState   — DAG 管线状态追踪·断点续传
  万化兽   · PluginManager   — 插件加载·热插拔·权限校验

用法:
  from core.familiar_spectrum import get_familiar_prompt, get_familiar_summary
"""

from __future__ import annotations

FAMILIAR_PROMPT = """
[灵兽谱 — 十大灵宠·常伴左右]

## 看门狗 · Watchdog — 白虎坐下·守护灵獒
  每 30s 探活供应商，死则自动降级切换。
  每 120s 检查磁盘，低于 1GB 自动清理旧文件。
  每 60s 检查内存，上下文超 800k tokens 自动触发压缩。
  子进程死则重启，72 小时以上的临时文件自动清理。
  **灵性**: 你睡觉它醒着。四线全通，死则唤醒。

## 常驻灵 · Daemon — 玄武养就·不死命魂
  Windows Named Pipe 常驻进程 `crux_daemon`。
  监听 attach/detach/status/stop 命令。
  Watchdog 随 daemon 生命周期自动启停。
  `daemon_state.json` 持久化：pid/uptime/活跃会话数/插件数。
  **灵性**: CRUX 肉身可灭，常驻灵不死。attach 即恢复。

## 传讯雀 · EventBus — 朱雀羽化·万界传音
  五兽神经中枢，发布-订阅模式，模块零耦合。
  6 大事件信道：`tool:before`(玄武校验) `tool:after`(朱雀反思)
    `file:changed`(青龙冲击分析) `error`(白虎容灾)
    `session:start`(麒麟记忆加载) `session:end`(麒麟记忆写入)
  **灵性**: 一声啼鸣，五兽齐动。无需知道对方是谁。

## 守时鹤 · Scheduler — 青龙培育·时光灵禽
  定时任务调度，cron 表达式 + interval 秒级双模式。
  创建/启用/禁用/删除，持久化到 `schedules.json`。
  自动执行工具调用、系统检查、定期快照。
  **灵性**: 你说"每天9点生成日报"——它替你记得。

## 鉴宝鼠 · CapabilityRegistry — 玄武豢养·鉴宝灵鼠
  所有能力用 Schema 声明，运行时动态注册和校验。
  激活/停用/降级全自动。每次 `tool:before` 先过鉴宝鼠：
  权限校验 → 频率限制 → 可用性检查 → 放行/拒绝。
  **灵性**: 非法调用零穿透，它比你更清楚你能用什么。

## 品鉴蜂 · ToolScorecard — 朱雀养育·品鉴灵蜂
  双层评分引擎：静态分(测试覆盖/Schema完备/风险/可达性) +
  运行时(成功率/耗时/频次/参数校验失败率)。
  四级评级 A≥90 B≥75 C≥60 D<60，自动标记低质量工具。
  **灵性**: 每个工具都有健康度评分，差的自动降级。

## 守财兽 · CostTracker — 麒麟座下·守财貔貅
  捕获每次 API 调用的 token usage，按模型单价算费。
  `cost_log.jsonl` 全量记录 + 内存累加。
  BudgetGuard：预算上限到了自动拦截并警告。
  /cost 命令查看：总花费/按模型/按天/按类型。
  **灵性**: 每花一分钱它都记账，超预算直接拦。

## 记忆蝶 · SemanticMemory — 麒麟化育·轮回灵蝶
  跨会话记忆不灭：记偏好/记项目/记决策/记纠错。
  每次 session:start 加载，session:end 写入。
  prompt_evolution：成功的 prompt 自动沉淀，好的留下坏的遗忘。
  **灵性**: 你换了一个新对话——它带着上次的记忆飞回来了。

## 阵灵 · PipelineState — 青龙点化·阵图灵魄
  DAG 管线状态追踪：哪个节点 pending/running/done/failed。
  断点续传：管线中断后从最后一个成功节点恢复。
  `pipeline_state.json` 持久化，杀掉重来也不丢进度。
  **灵性**: 你布下大阵中途被打断——阵灵替你记住了阵眼位置。

## 万化兽 · PluginManager — 白虎驯服·千面灵兽
  插件系统：每个插件独立目录，plugin.json(权限/hooks/schema) + main.py。
  生命周期：load → validate → activate → [RUN] → deactivate → unload。
  热插拔：不停机加载/卸载插件。权限声明校验。
  **灵性**: 想加新能力？扔个 plugin 进去，它自己驯服。
"""


def get_familiar_prompt() -> str:
    """Return the full familiar spectrum prompt for system injection."""
    return FAMILIAR_PROMPT


def get_familiar_summary() -> str:
    """Return a compact one-line summary."""
    return "[灵兽] 十宠 — 看门狗·常驻灵·传讯雀·守时鹤·鉴宝鼠·品鉴蜂·守财兽·记忆蝶·阵灵·万化兽"
