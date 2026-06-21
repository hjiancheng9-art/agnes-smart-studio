"""Tests for core.marketplace — skill marketplace with local/remote adapters."""

import json
import pytest


class TestSkillPackage:
    """SkillPackage dataclass serialization."""

    def test_default_construction(self):
        from core.marketplace import SkillPackage
        pkg = SkillPackage(name="test")
        assert pkg.name == "test"
        assert pkg.version == "1.0.0"
        assert pkg.source == "local"
        assert pkg.installed is False
        assert pkg.tags == []

    def test_to_dict_roundtrip(self):
        from core.marketplace import SkillPackage
        pkg = SkillPackage(name="x", description="d", tags=["a", "b"])
        d = pkg.to_dict()
        assert d["name"] == "x"
        assert d["tags"] == ["a", "b"]

    def test_from_dict_ignores_unknown_keys(self):
        from core.marketplace import SkillPackage
        d = {"name": "y", "unknown_field": "ignored", "version": "2.0.0"}
        pkg = SkillPackage.from_dict(d)
        assert pkg.name == "y"
        assert pkg.version == "2.0.0"
        assert not hasattr(pkg, "unknown_field")

    def test_from_dict_to_dict_roundtrip(self):
        from core.marketplace import SkillPackage
        original = SkillPackage(name="z", description="desc", author="me",
                                category="video", rating=4.5)
        d = original.to_dict()
        restored = SkillPackage.from_dict(d)
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.author == original.author
        assert restored.rating == original.rating


class TestLocalRegistry:
    """LocalRegistry reads from skills/ directory."""

    def test_name_is_local(self):
        from core.marketplace import LocalRegistry
        reg = LocalRegistry()
        assert reg.name == "local"

    def test_search_finds_skills(self, monkeypatch, tmp_path):
        from core.marketplace import LocalRegistry
        import core.marketplace as mp
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "video-maker.skill.json").write_text(json.dumps({
            "name": "video-maker", "description": "makes videos",
            "category": "video", "version": "1.0.0",
        }), encoding="utf-8")
        monkeypatch.setattr(mp, "SKILLS_DIR", skills_dir)
        reg = LocalRegistry()
        reg._md_dir = tmp_path / "skills_md"  # avoid real md dir
        results = reg.search("video")
        assert len(results) >= 1
        assert any(p.name == "video-maker" for p in results)

    def test_fetch_returns_package(self, monkeypatch, tmp_path):
        from core.marketplace import LocalRegistry
        import core.marketplace as mp
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "my-skill.skill.json").write_text(json.dumps({
            "name": "my-skill", "description": "test skill",
        }), encoding="utf-8")
        monkeypatch.setattr(mp, "SKILLS_DIR", skills_dir)
        reg = LocalRegistry()
        reg._md_dir = tmp_path / "skills_md"
        pkg = reg.fetch("my-skill")
        assert pkg is not None
        assert pkg.name == "my-skill"

    def test_fetch_missing_returns_none(self, monkeypatch, tmp_path):
        from core.marketplace import LocalRegistry
        import core.marketplace as mp
        monkeypatch.setattr(mp, "SKILLS_DIR", tmp_path / "skills")
        reg = LocalRegistry()
        reg._md_dir = tmp_path / "skills_md"
        assert reg.fetch("nonexistent") is None

    def test_category_inference_video(self, monkeypatch, tmp_path):
        from core.marketplace import LocalRegistry
        import core.marketplace as mp
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # No explicit category — should infer "video" from description
        (skills_dir / "showrunner.skill.json").write_text(json.dumps({
            "name": "showrunner", "description": "video production pipeline",
        }), encoding="utf-8")
        monkeypatch.setattr(mp, "SKILLS_DIR", skills_dir)
        reg = LocalRegistry()
        reg._md_dir = tmp_path / "skills_md"
        pkg = reg.fetch("showrunner")
        assert pkg is not None
        assert pkg.category == "video"

    def test_download_existing_skill_json(self, monkeypatch, tmp_path):
        from core.marketplace import LocalRegistry
        import core.marketplace as mp
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "existing.skill.json"
        target.write_text(json.dumps({"name": "existing"}), encoding="utf-8")
        monkeypatch.setattr(mp, "SKILLS_DIR", skills_dir)
        reg = LocalRegistry()
        reg._md_dir = tmp_path / "skills_md"
        result = reg.download("existing")
        assert result == target

    def test_download_missing_raises(self, monkeypatch, tmp_path):
        from core.marketplace import LocalRegistry
        import core.marketplace as mp
        monkeypatch.setattr(mp, "SKILLS_DIR", tmp_path / "skills")
        reg = LocalRegistry()
        reg._md_dir = tmp_path / "skills_md"
        with pytest.raises(FileNotFoundError):
            reg.download("nonexistent")


class TestCodeBuddyAdapter:
    """CodeBuddyAdapter parses SKILL.md frontmatter."""

    def test_name_property(self):
        from core.marketplace import CodeBuddyAdapter
        adapter = CodeBuddyAdapter(name="test-cb", market_dir="/nonexistent")
        assert adapter.name == "test-cb"

    def test_disabled_when_dir_missing(self):
        from core.marketplace import CodeBuddyAdapter
        adapter = CodeBuddyAdapter(market_dir="/definitely/not/here")
        assert adapter.enabled is False

    def test_parse_skill_md_frontmatter(self, tmp_path):
        from core.marketplace import CodeBuddyAdapter
        adapter = CodeBuddyAdapter(market_dir=str(tmp_path))
        md = tmp_path / "SKILL.md"
        md.write_text(
            "---\nname: my-plugin\ndescription: A test plugin\ncategory: Dev\nversion: 1.2.0\n---\n# My Plugin\nbody",
            encoding="utf-8"
        )
        parsed = adapter._parse_skill_md(md)
        assert parsed is not None
        assert parsed["name"] == "my-plugin"
        assert parsed["description"] == "A test plugin"
        assert parsed["category"] == "Dev"

    def test_parse_skill_md_missing_frontmatter(self, tmp_path):
        from core.marketplace import CodeBuddyAdapter
        adapter = CodeBuddyAdapter(market_dir=str(tmp_path))
        md = tmp_path / "SKILL.md"
        md.write_text("# Title only\nno frontmatter", encoding="utf-8")
        assert adapter._parse_skill_md(md) is None

    def test_category_map_dev_to_tool(self):
        from core.marketplace import CodeBuddyAdapter
        assert CodeBuddyAdapter.CATEGORY_MAP["Dev"] == "tool"
        assert CodeBuddyAdapter.CATEGORY_MAP["Education"] == "creative"


class TestMarketplaceClientInit:
    """MarketplaceClient initializes adapters."""

    def test_has_local_adapter(self):
        from core.marketplace import MarketplaceClient, LocalRegistry
        client = MarketplaceClient()
        assert isinstance(client.local, LocalRegistry)

    def test_has_codebuddy_adapter(self):
        from core.marketplace import MarketplaceClient, CodeBuddyAdapter
        client = MarketplaceClient()
        assert isinstance(client.codebuddy, CodeBuddyAdapter)

    def test_adapters_property_returns_list(self):
        from core.marketplace import MarketplaceClient
        client = MarketplaceClient()
        adapters = client.adapters
        assert isinstance(adapters, list)
        assert len(adapters) >= 1  # at least local


class TestMarketplaceClientOperations:
    """MarketplaceClient search/install/uninstall."""

    def test_uninstall_missing_returns_false(self, monkeypatch, tmp_path):
        from core.marketplace import MarketplaceClient
        import core.marketplace as mp
        monkeypatch.setattr(mp, "SKILLS_DIR", tmp_path / "skills")
        client = MarketplaceClient()
        assert client.uninstall("nonexistent") is False

    def test_uninstall_existing(self, monkeypatch, tmp_path):
        from core.marketplace import MarketplaceClient
        import core.marketplace as mp
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "remove-me.skill.json"
        target.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(mp, "SKILLS_DIR", skills_dir)
        client = MarketplaceClient()
        assert client.uninstall("remove-me") is True
        assert not target.exists()

    def test_categories_returns_sorted_list(self, monkeypatch, tmp_path):
        from core.marketplace import MarketplaceClient
        import core.marketplace as mp
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "a.skill.json").write_text(json.dumps({
            "name": "a", "description": "video tool", "category": "video"}), encoding="utf-8")
        (skills_dir / "b.skill.json").write_text(json.dumps({
            "name": "b", "description": "coding tool", "category": "tool"}), encoding="utf-8")
        monkeypatch.setattr(mp, "SKILLS_DIR", skills_dir)
        client = MarketplaceClient()
        client.local._md_dir = tmp_path / "skills_md"
        cats = client.categories()
        assert isinstance(cats, list)
        assert cats == sorted(cats)

    def test_summary_contains_status_info(self, monkeypatch, tmp_path):
        from core.marketplace import MarketplaceClient
        import core.marketplace as mp
        monkeypatch.setattr(mp, "SKILLS_DIR", tmp_path / "skills")
        client = MarketplaceClient()
        client.local._md_dir = tmp_path / "skills_md"
        s = client.summary()
        assert "技能市场" in s
        assert "已安装" in s


class TestGetMarketplaceSingleton:
    """get_marketplace() returns shared instance."""

    def test_returns_same_instance(self):
        from core.marketplace import get_marketplace
        m1 = get_marketplace()
        m2 = get_marketplace()
        assert m1 is m2
