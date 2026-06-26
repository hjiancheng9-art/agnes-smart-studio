"""CRUX Intimate Slots — 贴身七件。
护符 talisman  · 熔断保护
内甲 inner_armor · 密钥加密
行囊 backpack  · 配置快照/回滚
腰带 belt      · 流式数据管线
左戒 left_ring · 遥测日志
右戒 right_ring · 自愈升级
披风 cloak     · 隐私隐身
Usage: from core.intimate_slots import talisman
talisman.circuit.check()
"""

from __future__ import annotations

__all__ = [
    "talisman",
    "inner_armor",
    "backpack",
    "belt",
    "left_ring",
    "right_ring",
    "cloak",
]


def __getattr__(name: str):
    """Lazy-load submodules on first access."""
    if name in __all__:
        import importlib

        return importlib.import_module(f"core.intimate_slots.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


INTIMATE_SLOTS_PROMPT = """
[贴身七件 — 激活规则]
## 护符 · 熔断保护
  连续 N 次 API 失败自动熔断，cool-down 后探针恢复。阻止级联故障烧穿资源。
  circuit.check(provider) → (ok, reason)
  circuit.record_failure/success(provider)
## 内甲 · 密钥加密
  API Key 落盘加密存储，支持从环境变量一键迁移。Windows DPAPI / Linux keyring fallback。
  vault.get/set/delete(key) → 密钥永不落明文
## 行囊 · 配置快照/回滚
  一键快照（models.json / tools.json / sessions / memory），支持任意时间点回滚。
  最多保留10个快照，自动裁剪。回滚前自动生成安全快照。
  backpack.snapshot(label) → backpack.rollback(name)
## 腰带 · 流式数据管线
  统一流式管道：source → transform → filter → buffer → sink。
  所有工具输出经过此管线，支持实时 Rich 终端流式渲染 + 批量落盘。
  pipeline.push(data, event) → pipeline.flush()
## 左戒 · 遥测日志
  全量工具调用结构化遥测：事件/工具名/延迟/错误/供应商/tokens。
  滚动 JSONL 日志，实时错误率/平均延迟统计。遥测数据用于性能诊断。
  telemetry.log(event, tool, latency, error, provider, tokens)
## 右戒 · 自愈升级
  系统健康评分（0-100）：供应商可达性 + 磁盘空间 + 熔断状态。
  自动版本检查、热补丁应用。评分 < 70 触发降级模式。
  healer.check() → {version, health, cached}
## 披风 · 隐私隐身
  敏感信息自动脱敏：API Key / 邮箱 / 手机号 / IP / JWT Token。
  递归清理 dict/list 中所有字符串值。输出前自动包裹隐私标记。
  cloak.sanitize(text) → cloak.sanitize_dict(dict)
"""


def get_intimate_prompt() -> str:
    """Return the intimate slots behavioral prompt for system injection."""
    return INTIMATE_SLOTS_PROMPT
