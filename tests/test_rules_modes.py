"""Tests for core/rules.py — activation modes & globs matching."""

import os
import tempfile
from pathlib import Path

from core.rules import (
    MODE_ALWAYS,
    MODE_GLOBS,
    MODE_MANUAL,
    MODE_SMART,
    Rule,
    RulesManager,
    get_rules,
    reset_rules,
)

# ── Rule class ────────────────────────────────────────────────────────────


class TestRule:
    def test_default_mode_is_always(self):
        r = Rule("test", "content")
        assert r.mode == MODE_ALWAYS
        assert r.globs == []

    def test_mode_globs(self):
        r = Rule("test", "content", mode=MODE_GLOBS, globs=["*.py", "src/**/*.ts"])
        assert r.mode == MODE_GLOBS
        assert len(r.globs) == 2

    def test_invalid_mode_falls_to_always(self):
        r = Rule("test", "content", mode="invalid")
        assert r.mode == MODE_ALWAYS

    def test_matches_files_python(self):
        r = Rule("test", "content", mode=MODE_GLOBS, globs=["*.py"])
        assert r.matches_files(["main.py"])
        assert r.matches_files(["src/utils/helper.py"])

    def test_matches_files_no_match(self):
        r = Rule("test", "content", mode=MODE_GLOBS, globs=["*.py"])
        assert not r.matches_files(["README.md"])
        assert not r.matches_files(["src/main.js"])

    def test_matches_files_wrong_mode(self):
        r = Rule("test", "content", mode=MODE_ALWAYS, globs=["*.py"])
        assert not r.matches_files(["main.py"])  # Mode is always, not globs

    def test_matches_files_empty_globs(self):
        r = Rule("test", "content", mode=MODE_GLOBS, globs=[])
        assert not r.matches_files(["main.py"])

    def test_matches_files_multiple_patterns(self):
        r = Rule("test", "content", mode=MODE_GLOBS, globs=["*.py", "*.ts", "*.tsx"])
        assert r.matches_files(["main.tsx"])
        assert r.matches_files(["utils.ts"])
        assert not r.matches_files(["README.md"])

    def test_scene_field(self):
        r = Rule("test", "content", scene="git_message")
        assert r.scene == "git_message"


# ── Rule.from_file ────────────────────────────────────────────────────────


class TestRuleFromFile:
    def test_basic_md_file(self):
        # Use a directory we control so the filename is predictable
        d = tempfile.mkdtemp()
        fname = os.path.join(d, "my-test.rules.md")
        try:
            with open(fname, "w", encoding="utf-8") as f:
                f.write("# Test rule\n\nThis is the rule content.")
            r = Rule.from_file(Path(fname))
            assert r.name == "my-test"
            assert r.description == "Test rule"
            assert "This is the rule content" in r.content
            assert r.mode == MODE_ALWAYS
        finally:
            import shutil

            shutil.rmtree(d, ignore_errors=True)

    def test_globs_frontmatter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rules.md", delete=False, encoding="utf-8") as f:
            f.write('---\nmode: globs\nglobs: ["*.py", "src/**/*.ts"]\n---\n\n# Py rule\n\nUse type hints.')
            fname = f.name
        try:
            r = Rule.from_file(Path(fname))
            assert r.mode == MODE_GLOBS
            assert r.globs == ["*.py", "src/**/*.ts"]
            assert r.description == "Py rule"
        finally:
            os.unlink(fname)

    def test_default_active_frontmatter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rules.md", delete=False, encoding="utf-8") as f:
            f.write("---\ndefault-active: true\n---\n\n# Always on\n\nTest.")
            fname = f.name
        try:
            r = Rule.from_file(Path(fname))
            assert r.default_active is True
        finally:
            os.unlink(fname)


# ── RulesManager activation modes ─────────────────────────────────────────


class TestRulesManagerModes:
    def setup_method(self):
        reset_rules()
        self.rm = RulesManager()
        self.rm._dir = Path(tempfile.mkdtemp())
        self.rm.discover()

    def teardown_method(self):
        import shutil

        if self.rm._dir.exists():
            shutil.rmtree(self.rm._dir, ignore_errors=True)

    def _add_rule(self, name, mode=MODE_ALWAYS, globs=None, desc=""):
        self.rm.create_rule(name, f"{name} content", description=desc or name, mode=mode, globs=globs)
        self.rm.discover()
        self.rm.enable(name)

    def test_always_mode_included(self):
        self._add_rule("always-rule", MODE_ALWAYS)
        active = self.rm.get_active_for_context("", [])
        assert any(r.name == "always-rule" for r in active)

    def test_globs_mode_with_matching_file(self):
        self._add_rule("py-rule", MODE_GLOBS, globs=["*.py"])
        active = self.rm.get_active_for_context("", ["main.py"])
        assert any(r.name == "py-rule" for r in active)

    def test_globs_mode_without_matching_file(self):
        self._add_rule("py-rule", MODE_GLOBS, globs=["*.py"])
        active = self.rm.get_active_for_context("", ["README.md"])
        assert not any(r.name == "py-rule" for r in active)

    def test_globs_mode_no_context_files(self):
        self._add_rule("py-rule", MODE_GLOBS, globs=["*.py"])
        active = self.rm.get_active_for_context("", [])
        assert not any(r.name == "py-rule" for r in active)

    def test_smart_mode_with_matching_task(self):
        self._add_rule("react-rule", MODE_SMART, desc="React component testing conventions")
        active = self.rm.get_active_for_context("write tests for React component", [])
        assert any(r.name == "react-rule" for r in active)

    def test_smart_mode_no_match(self):
        self._add_rule("react-rule", MODE_SMART, desc="React component testing conventions")
        active = self.rm.get_active_for_context("deploy to production", [])
        assert not any(r.name == "react-rule" for r in active)

    def test_manual_mode_not_auto_included(self):
        self._add_rule("manual-rule", MODE_MANUAL)
        active = self.rm.get_active_for_context("any task", [])
        assert not any(r.name == "manual-rule" for r in active)

    def test_manual_mode_activated_by_mention(self):
        self._add_rule("manual-rule", MODE_MANUAL)
        self.rm.mention("manual-rule")
        active = self.rm.get_active_for_context("any task", [])
        assert any(r.name == "manual-rule" for r in active)

    def test_set_context_files(self):
        self._add_rule("py-rule", MODE_GLOBS, globs=["*.py"])
        self.rm.set_context_files(["hello.py"])
        active = self.rm.get_active_for_context("", [])
        assert any(r.name == "py-rule" for r in active)

    def test_inject_prompt_with_context(self):
        self._add_rule("always-rule", MODE_ALWAYS, desc="Always active rule")
        self._add_rule("py-rule", MODE_GLOBS, globs=["*.py"], desc="Python rule")
        prompt = self.rm.inject_prompt(task_text="", files=["main.py"])
        assert "Always active rule" in prompt
        assert "Python rule" in prompt

    def test_inject_prompt_empty_when_nothing_active(self):
        # Clear all active rules
        self.rm._active.clear()
        prompt = self.rm.inject_prompt()
        assert prompt == ""


# ── RulesManager basics ──────────────────────────────────────────────────


class TestRulesManagerBasics:
    def setup_method(self):
        reset_rules()

    def test_get_rules_singleton(self):
        rm1 = get_rules()
        rm2 = get_rules()
        assert rm1 is rm2

    def test_discover_creates_dir(self):
        rm = RulesManager(Path(tempfile.mkdtemp()))
        rm.discover()
        assert rm._dir.exists()

    def test_create_and_load_rule(self):
        rm = RulesManager(Path(tempfile.mkdtemp()))
        rm.discover()
        path = rm.create_rule("test-rule", "content", description="A test rule")
        assert path.exists()
        rm.discover()
        rule = rm.load("test-rule")
        assert rule is not None
        assert rule.description == "A test rule"
