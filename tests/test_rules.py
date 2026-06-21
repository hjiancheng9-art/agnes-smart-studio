"""Tests for core.rules — persistent coding rules system."""



class TestRule:
    def test_basic_rule(self):
        from core.rules import Rule
        r = Rule("test", "Always use type hints", "Type hints rule")
        assert r.name == "test"
        assert r.content == "Always use type hints"
        assert r.description == "Type hints rule"
        assert r.enabled is True
        assert r.category == "general"

    def test_rule_disabled(self):
        from core.rules import Rule
        r = Rule("test", "content", enabled=False)
        assert r.enabled is False

    def test_from_file_with_header(self, tmp_path):
        from core.rules import Rule
        # Use a name that doesn't have multiple dots
        f = tmp_path / "myrule.rules.md"
        f.write_text("# My Rule Title\n\nThe rule content here\n", encoding="utf-8")
        r = Rule.from_file(f)
        # .rules.md 后缀被剥两层 → 纯名 myrule
        assert r.name == "myrule"
        assert r.description == "My Rule Title"
        assert "The rule content here" in r.content
        assert "# My Rule Title" not in r.content

    def test_from_file_without_header(self, tmp_path):
        from core.rules import Rule
        f = tmp_path / "norule.rules.md"
        f.write_text("Just some content\nline 2\n", encoding="utf-8")
        r = Rule.from_file(f)
        assert r.description == ""
        assert "Just some content" in r.content

    def test_from_file_missing(self, tmp_path):
        from core.rules import Rule
        f = tmp_path / "missing.rules.md"
        r = Rule.from_file(f)
        assert r.content == ""
        assert r.name == "missing"


class TestRulesManager:
    def test_init_default_dir(self):
        from core.rules import RulesManager, RULES_DIR
        mgr = RulesManager()
        assert mgr._dir == RULES_DIR

    def test_init_custom_dir(self, tmp_path):
        from core.rules import RulesManager
        custom = tmp_path / "rules"
        mgr = RulesManager(rules_dir=custom)
        assert mgr._dir == custom

    def test_discover_empty_dir(self, tmp_path):
        from core.rules import RulesManager
        custom = tmp_path / "rules"
        custom.mkdir()
        mgr = RulesManager(rules_dir=custom)
        rules = mgr.discover()
        assert rules == {}

    def test_discover_creates_missing_dir(self, tmp_path):
        from core.rules import RulesManager
        custom = tmp_path / "newrules"
        mgr = RulesManager(rules_dir=custom)
        rules = mgr.discover()
        assert rules == {}
        assert custom.exists()

    def test_discover_finds_rules(self, tmp_path):
        from core.rules import RulesManager
        d = tmp_path / "rules"
        d.mkdir()
        (d / "style.rules.md").write_text("# Style\n\nUse type hints\n", encoding="utf-8")
        (d / "security.rules.md").write_text("# Security\n\nNo hardcoded keys\n", encoding="utf-8")
        mgr = RulesManager(rules_dir=d)
        rules = mgr.discover()
        # .rules.md 后缀被剥两层 → 纯名 style / security
        assert "style" in rules
        assert "security" in rules

    def test_load_single(self, tmp_path):
        from core.rules import RulesManager
        d = tmp_path / "rules"
        d.mkdir()
        (d / "myrule.rules.md").write_text("# Test\n\nContent\n", encoding="utf-8")
        mgr = RulesManager(rules_dir=d)
        rule = mgr.load("myrule")
        assert rule is not None
        assert rule.description == "Test"

    def test_load_nonexistent(self, tmp_path):
        from core.rules import RulesManager
        d = tmp_path / "rules"
        d.mkdir()
        mgr = RulesManager(rules_dir=d)
        rule = mgr.load("nope")
        assert rule is None

    def test_enable_disable(self, tmp_path):
        from core.rules import RulesManager
        d = tmp_path / "rules"
        d.mkdir()
        (d / "myrule.rules.md").write_text("# Test\n\nContent\n", encoding="utf-8")
        mgr = RulesManager(rules_dir=d)
        mgr.load("myrule")
        assert mgr.enable("myrule") is True
        assert len(mgr.active_rules) == 1
        mgr.disable("myrule")
        assert len(mgr.active_rules) == 0

    def test_enable_nonexistent(self, tmp_path):
        from core.rules import RulesManager
        mgr = RulesManager(rules_dir=tmp_path / "rules")
        assert mgr.enable("nonexistent") is False

    def test_available_names(self, tmp_path):
        from core.rules import RulesManager
        d = tmp_path / "rules"
        d.mkdir()
        (d / "a.rules.md").write_text("# A\n\nA\n", encoding="utf-8")
        (d / "b.rules.md").write_text("# B\n\nB\n", encoding="utf-8")
        mgr = RulesManager(rules_dir=d)
        mgr.discover()
        names = mgr.available_names
        assert "a" in names
        assert "b" in names

    def test_inject_prompt_empty(self, tmp_path):
        from core.rules import RulesManager
        mgr = RulesManager(rules_dir=tmp_path / "rules")
        assert mgr.inject_prompt() == ""

    def test_inject_prompt_with_active(self, tmp_path):
        from core.rules import RulesManager
        d = tmp_path / "rules"
        d.mkdir()
        (d / "myrule.rules.md").write_text("# Test Rule\n\nAlways use type hints\n", encoding="utf-8")
        mgr = RulesManager(rules_dir=d)
        mgr.load("myrule")
        mgr.enable("myrule")
        prompt = mgr.inject_prompt()
        assert "Test Rule" in prompt
        assert "Always use type hints" in prompt

    def test_create_rule(self, tmp_path):
        from core.rules import RulesManager
        mgr = RulesManager(rules_dir=tmp_path / "rules")
        path = mgr.create_rule("new", "content here", "description", "custom")
        assert path.exists()
        assert "new.rules.md" in str(path)
        text = path.read_text(encoding="utf-8")
        assert "description" in text
        assert "content here" in text

    def test_create_examples(self, tmp_path):
        from core.rules import RulesManager
        d = tmp_path / "rules"
        mgr = RulesManager(rules_dir=d)
        # discover() creates the dir first (matches production usage in get_rules)
        mgr.discover()
        mgr.create_examples()
        names = mgr.discover().keys()
        assert "encoding-i18n" in names
        assert "python-style" in names
        assert "secret-security" in names

    def test_discover_nested_category(self, tmp_path):
        from core.rules import RulesManager
        d = tmp_path / "rules"
        d.mkdir()
        cat_dir = d / "custom"
        cat_dir.mkdir()
        (cat_dir / "nested.rules.md").write_text("# Nested\n\nContent\n", encoding="utf-8")
        mgr = RulesManager(rules_dir=d)
        rules = mgr.discover()
        assert "nested" in rules
        assert rules["nested"].category == "custom"
