import core.cdp_browser as cb

prompt = """你是 CRUX Studio TUI 审计专家。以下是完整 TUI 子系统状态，请给出分阶段可执行修复计划。

## TUI 全貌
- 38个.py文件, 9200行, 347KB
- 核心: tui_v2.py(2197行)/widgets_v2.py(926行)/tui_app.py(531行)/theme_v2.py(515行)/message_pane.py(478行)
- 子模块: animation_gov.py/completer.py/terminal_splash.py/clipboard_image.py/panels/screens
- 现有测试: 仅3文件 77tests, 覆盖率7.9%
- 缺失测试: widgets_v2, tui_app, theme_v2, message_pane, animation_gov, completer等核心模块

## 要求
4阶段: 1.债务清单 2.测试计划 3.修复顺序 4.每阶段TASK/CMD格式
注意: TUI用Textual/rich, 测试用mock/fake terminal, 不依赖真实终端。
直接开始审计。"""

print(f"Sending ({len(prompt)} chars)...")
resp = cb.ask_chatgpt(prompt, wait=True)
with open('.crux/auto_fix/tui_gpt_plan.txt', 'w', encoding='utf-8') as f:
    f.write(resp)
print("PLAN SAVED")
print(f"Length: {len(resp)} chars")
