"""Tests for core/skill_pack.py — pack, install, list."""

import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.skill_pack import PACK_EXT, SKILLS_DIR, install, list_packs, pack


class TestPack:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        # Create a test skill file
        self.skill_name = "test-pack-skill"
        self.skill_file = SKILLS_DIR / f"{self.skill_name}.skill.json"
        self.skill_file.write_text(
            json.dumps(
                {
                    "name": self.skill_name,
                    "description": "Test skill for packaging",
                    "version": "1.0.0",
                    "author": "test",
                    "category": "test",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def teardown_method(self):
        self.skill_file.unlink(missing_ok=True)
        # Clean up any generated .crux-skill files
        for f in Path(".").glob(f"{self.skill_name}*"):
            f.unlink(missing_ok=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pack_creates_file(self):
        out = pack(self.skill_name, output_dir=self.tmp)
        assert out.exists()
        assert out.suffix == PACK_EXT

    def test_pack_contains_json(self):
        out = pack(self.skill_name, output_dir=self.tmp)
        with zipfile.ZipFile(out) as zf:
            assert "skill.json" in zf.namelist()
            assert "metadata.json" in zf.namelist()

    def test_pack_nonexistent_skill_raises(self):
        with pytest.raises(FileNotFoundError):
            pack("this-skill-does-not-exist-xyz", output_dir=self.tmp)


class TestInstall:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.skill_name = "test-install-skill"
        # Create and pack
        skill_file = SKILLS_DIR / f"{self.skill_name}.skill.json"
        skill_file.write_text(
            json.dumps({"name": self.skill_name, "description": "test"}, ensure_ascii=False), encoding="utf-8"
        )
        self.pack_path = pack(self.skill_name, output_dir=self.tmp)

    def teardown_method(self):
        p = SKILLS_DIR / f"{self.skill_name}.skill.json"
        p.unlink(missing_ok=True)
        (SKILLS_DIR / f"{self.skill_name}.meta.json").unlink(missing_ok=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_install_from_file(self):
        result = install(str(self.pack_path))
        assert result["status"] == "installed"
        assert result["name"] == self.skill_name

    def test_install_nonexistent_file(self):
        result = install("/nonexistent/path.crux-skill")
        assert result["status"] == "error"

    def test_install_invalid_zip(self):
        bad = Path(self.tmp) / "bad.crux-skill"
        bad.write_text("not a zip file")
        result = install(str(bad))
        assert result["status"] == "error"


class TestListPacks:
    def test_list_returns_list(self):
        packs = list_packs(directory=".")
        assert isinstance(packs, list)

    def test_list_empty_directory(self):
        with tempfile.TemporaryDirectory() as d:
            packs = list_packs(directory=d)
            assert packs == []
