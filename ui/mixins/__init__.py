"""AgnesCLI Mixin 包 — 按职责拆分的命令处理器。

AgnesCLI 通过多重继承组合这些 Mixin。每个 Mixin 定义一组 _chat_*/_inline_*
方法，self 始终是 AgnesCLI 实例（getattr 反射依赖此不变量）。

Mixin 层次（MRO 顺序，从基础到具体）:
    SharedMixin           — 基础设施：输入/渲染/选择/分发（被所有 Mixin 依赖）
    InlineCommandsMixin   — /clear /thinking /code /agent /tools /browser /help /img /video
    CreativeCommandsMixin — /showrun /vision /skill + _chat_generate
    EngineeringCommandsMixin — /plan /sub /compress /project /team /deploy /todo /refactor
    GitCommandsMixin      — /commit /changelog
    DiagCommandsMixin     — /self /audit /rules /automate /provider /evolve /know /model
    GeneratorsMenuMixin   — 菜单生成组 _t2i/_i2i/_t2v/_i2v/_pipeline/_hist/_tmpl
"""

from ui.mixins.shared import SharedMixin
from ui.mixins.inline import InlineCommandsMixin
from ui.mixins.creative import CreativeCommandsMixin
from ui.mixins.engineering import EngineeringCommandsMixin
from ui.mixins.git_cmds import GitCommandsMixin
from ui.mixins.diag import DiagCommandsMixin
from ui.mixins.generators_menu import GeneratorsMenuMixin

__all__ = [
    "SharedMixin",
    "InlineCommandsMixin",
    "CreativeCommandsMixin",
    "EngineeringCommandsMixin",
    "GitCommandsMixin",
    "DiagCommandsMixin",
    "GeneratorsMenuMixin",
]
