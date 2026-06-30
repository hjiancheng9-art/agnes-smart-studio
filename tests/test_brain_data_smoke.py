"""Smoke tests for core/brain_data/*.py — knowledge base integrity."""

import ast
from pathlib import Path


BRAIN_DATA_DIR = Path(__file__).parent.parent / "core" / "brain_data"
BRAIN_FILES = ["__init__.py", "combat.py", "creative.py", "entities.py", "prompts.py", "sweet_spots.py"]


class TestBrainDataSyntax:
    """All brain_data files pass AST parsing."""

    def test_all_files_syntax(self):
        for fname in BRAIN_FILES:
            path = BRAIN_DATA_DIR / fname
            assert path.exists(), f"Missing: {fname}"
            with open(path, encoding="utf-8") as f:
                ast.parse(f.read())

    def test_all_files_utf8(self):
        for fname in BRAIN_FILES:
            path = BRAIN_DATA_DIR / fname
            try:
                with open(path, encoding="utf-8") as f:
                    f.read()
            except UnicodeDecodeError:
                assert False, f"{fname} is not UTF-8"


class TestBrainDataImports:
    """brain_data module can be imported."""

    def test_package_imports(self):
        import core.brain_data
        assert core.brain_data is not None

    def test_combat_imports(self):
        from core.brain_data import combat
        assert combat is not None

    def test_creative_imports(self):
        from core.brain_data import creative
        assert creative is not None

    def test_entities_imports(self):
        from core.brain_data import entities
        assert entities is not None

    def test_prompts_imports(self):
        from core.brain_data import prompts
        assert prompts is not None

    def test_sweet_spots_imports(self):
        from core.brain_data import sweet_spots
        assert sweet_spots is not None


class TestBrainDataKeys:
    """Key knowledge base structures have expected shape."""

    def test_entities_has_type_map(self):
        from core.brain_data.entities import ENTITY_TYPE_MAP
        assert isinstance(ENTITY_TYPE_MAP, dict), "ENTITY_TYPE_MAP must be a dict"
        for entity_type, config in ENTITY_TYPE_MAP.items():
            assert "name_cn" in config, f"{entity_type} missing name_cn"
            assert "keywords" in config, f"{entity_type} missing keywords"
            assert isinstance(config["keywords"], list), f"{entity_type} keywords not a list"

    def test_combat_motif_keys(self):
        from core.brain_data.combat import NONHUMAN_COMBAT_MOTIF
        assert isinstance(NONHUMAN_COMBAT_MOTIF, dict)
        # 至少应该有 contrast 和 combat_style 等顶级 key
        assert len(NONHUMAN_COMBAT_MOTIF) >= 2, \
            f"NONHUMAN_COMBAT_MOTIF too small: {len(NONHUMAN_COMBAT_MOTIF)} keys"

    def test_prompts_has_intent(self):
        from core.brain_data.prompts import INTENT_PROMPT
        assert isinstance(INTENT_PROMPT, str)
        assert len(INTENT_PROMPT) > 100, f"INTENT_PROMPT too short: {len(INTENT_PROMPT)} chars"

    def test_init_has_negatives(self):
        from core.brain_data import NEGATIVE_REPAIR_MAP
        assert isinstance(NEGATIVE_REPAIR_MAP, dict)


class TestBrainDataSizes:
    """Knowledge bases are non-trivial (not accidentally emptied)."""

    def test_combat_is_sizable(self):
        with open(BRAIN_DATA_DIR / "combat.py", encoding="utf-8") as f:
            size = len(f.read())
        assert size > 5000, f"combat.py too small: {size} bytes"

    def test_entities_is_sizable(self):
        with open(BRAIN_DATA_DIR / "entities.py", encoding="utf-8") as f:
            size = len(f.read())
        assert size > 3000, f"entities.py too small: {size} bytes"

    def test_all_files_non_empty(self):
        for fname in BRAIN_FILES:
            path = BRAIN_DATA_DIR / fname
            assert path.stat().st_size > 10, f"{fname} is empty or too small"
