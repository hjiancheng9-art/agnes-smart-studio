"""scripts/update_tool_count.py 单测 — 漂移检测 + AGENTS.md 更新逻辑。

只测纯函数逻辑（正则匹配/替换），不触发 registry 加载（那需要完整依赖）。
覆盖:
    - find_stale_counts: 精确匹配工具总数，排除 "(N tools)" 等描述性数字
    - update_agents_md: 替换漂移数字，无漂移时不动文件
    - 子串陷阱: "line 280" / "1809 tests" 不应误判为工具数
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# update_tool_count 不是包内模块（在 scripts/ 下），用 importlib 按文件加载
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "update_tool_count", SCRIPTS / "update_tool_count.py"
)
assert _spec is not None and _spec.loader is not None
ucm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ucm)


# ── find_stale_counts 精确匹配 ──────────────────────────────────

class TestFindStaleCounts:
    def test_no_tools_mention_returns_empty(self):
        assert ucm.find_stale_counts("no tools count here", expected=80) == []

    def test_matching_count_no_drift(self):
        content = "- 80 Tools: code editing, git\n- 33 commands, 80 tools\n"
        assert ucm.find_stale_counts(content, expected=80) == []

    def test_detects_drift_tools_uppercase(self):
        content = "- 84 Tools: code editing"
        stale = ucm.find_stale_counts(content, expected=80)
        assert len(stale) == 1
        assert stale[0] == ("84 Tools", 84)

    def test_detects_drift_tools_lowercase(self):
        content = "- 33 commands, 84 tools, 45 skills"
        stale = ucm.find_stale_counts(content, expected=80)
        assert len(stale) == 1
        assert stale[0] == ("84 tools", 84)

    def test_detects_tools_colon_format(self):
        content = "Tools: 84"
        stale = ucm.find_stale_counts(content, expected=80)
        assert len(stale) == 1

    def test_multiple_drifts(self):
        content = "- 84 Tools: ...\n- 33 commands, 90 tools, ...\n"
        stale = ucm.find_stale_counts(content, expected=80)
        assert len(stale) == 2
        old_vals = [s[1] for s in stale]
        assert 84 in old_vals and 90 in old_vals


# ── 排除描述性数字（核心反例）──────────────────────────────────

class TestExcludesDescriptiveNumbers:
    """"(4 tools)" 这类括号内描述性数字不应被当成工具总数。"""

    def test_parenthesized_count_not_matched(self):
        content = "MCP bridge (4 tools), patch, execute_plan"
        # 4 tools 在括号内，期望 80，不应报漂移
        assert ucm.find_stale_counts(content, expected=80) == []

    def test_parenthesized_even_if_mismatch(self):
        """即使括号内数字与期望不同，也不算漂移（那是子系统计数）。"""
        content = "ComfyUI (12 tools), LoRA (3)"
        assert ucm.find_stale_counts(content, expected=80) == []

    def test_substring_in_line_number(self):
        """"line 280" 不应被 "80" 子串误判（旧版 in 操作符的 bug）。"""
        content = "SkillManager (line 280)"
        assert ucm.find_stale_counts(content, expected=80) == []

    def test_substring_in_test_count(self):
        """"1809 tests passing" 不应误判。"""
        content = "Test baseline: 1809 tests passing"
        assert ucm.find_stale_counts(content, expected=80) == []


# ── update_agents_md 文件写入 ───────────────────────────────────

class TestUpdateAgentsMd:
    def test_no_drift_no_write(self, tmp_path, monkeypatch):
        """无漂移时不应写文件（mtime 不变）。"""
        agents = tmp_path / "AGENTS.md"
        agents.write_text("- 80 Tools: ok\n", encoding="utf-8")
        monkeypatch.setattr(ucm, "AGENTS_MD", agents)

        changed = ucm.update_agents_md(80)
        assert changed is False
        assert agents.read_text(encoding="utf-8") == "- 80 Tools: ok\n"

    def test_drift_replaces_count(self, tmp_path, monkeypatch):
        agents = tmp_path / "AGENTS.md"
        agents.write_text(
            "- 84 Tools: code editing\n- 33 commands, 84 tools\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(ucm, "AGENTS_MD", agents)

        changed = ucm.update_agents_md(80)
        assert changed is True
        content = agents.read_text(encoding="utf-8")
        assert "80 Tools" in content
        assert "80 tools" in content
        assert "84" not in content  # 旧值彻底消失

    def test_preserves_parenthesized_counts(self, tmp_path, monkeypatch):
        """更新总数时应保留 "(4 tools)" 这种子系统计数。"""
        agents = tmp_path / "AGENTS.md"
        agents.write_text(
            "- 84 Tools: ..., MCP bridge (4 tools), audio\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(ucm, "AGENTS_MD", agents)

        ucm.update_agents_md(80)
        content = agents.read_text(encoding="utf-8")
        assert "80 Tools" in content
        assert "(4 tools)" in content  # 子系统计数保留

    def test_only_replaces_target_context(self, tmp_path, monkeypatch):
        """不应误改 "line 280" 中的 80 子串。"""
        agents = tmp_path / "AGENTS.md"
        agents.write_text(
            "- 84 Tools: ...\n- SkillManager (line 280)\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(ucm, "AGENTS_MD", agents)

        ucm.update_agents_md(80)
        content = agents.read_text(encoding="utf-8")
        assert "line 280" in content  # 保持不变
        assert "80 Tools" in content


# ── 模式定义自检 ───────────────────────────────────────────────

class TestPatternSanity:
    def test_patterns_are_compiled(self):
        for p in ucm._TOOL_COUNT_PATTERNS:
            assert hasattr(p, "pattern")

    def test_patterns_have_capture_group(self):
        """每个模式必须有捕获组（用于提取数字）。"""
        for p in ucm._TOOL_COUNT_PATTERNS:
            m = p.search("84 Tools: test")
            if m:
                assert m.group(1) == "84"
