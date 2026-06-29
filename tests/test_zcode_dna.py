"""Tests for core/lore/zcode_dna.py — ZCode 基因吸收校验。

覆盖:
- 6 个基因全部存在且非空
- 15 种 Zod 校验模式 (ZCODE_VALIDATION_PATTERNS dict)
- validate_boundary 边界检查
- get_zcode_dna_prompt 完整输出
"""

import re
from core.lore.zcode_dna import (
    SCHEMA_VERSION,
    ZCODE_VALIDATION_PATTERNS,
    validate_boundary,
    get_zcode_dna_prompt,
)


class TestSchemaVersion:
    """Gene 1: Schema-versioned。"""

    def test_schema_version_exists(self):
        assert SCHEMA_VERSION == "crux.zcode-dna.v1"

    def test_version_is_string(self):
        assert isinstance(SCHEMA_VERSION, str)


class TestZCodeGenePresence:
    """六基因在 prompt 中完整。"""

    def test_gene_1_schema_versioned_present(self):
        prompt = get_zcode_dna_prompt()
        assert "Gene 1" in prompt
        assert "Schema" in prompt or "version" in prompt.lower()

    def test_gene_2_dual_protocol_present(self):
        prompt = get_zcode_dna_prompt()
        assert "Gene 2" in prompt
        assert "protocol" in prompt.lower()

    def test_gene_3_runtime_guards_present(self):
        prompt = get_zcode_dna_prompt()
        assert "Gene 3" in prompt
        assert "Validation" in prompt or "valid" in prompt.lower()

    def test_gene_4_self_extending_present(self):
        prompt = get_zcode_dna_prompt()
        assert "Gene 4" in prompt

    def test_gene_5_preservative_present(self):
        prompt = get_zcode_dna_prompt()
        assert "Gene 5" in prompt

    def test_gene_6_event_lifecycle_present(self):
        prompt = get_zcode_dna_prompt()
        assert "Gene 6" in prompt

    def test_prompt_long_enough(self):
        prompt = get_zcode_dna_prompt()
        assert len(prompt) > 2000


class TestValidationPatterns:
    """15 种 Zod 校验模式。"""

    def test_patterns_count_at_least_15(self):
        assert len(ZCODE_VALIDATION_PATTERNS) >= 15

    def test_each_pattern_has_name_and_regex(self):
        for name, regex in ZCODE_VALIDATION_PATTERNS.items():
            assert isinstance(name, str)
            assert isinstance(regex, str)
            assert len(name) > 0
            assert len(regex) > 0

    def test_email_pattern_works(self):
        assert re.match(ZCODE_VALIDATION_PATTERNS["email"], "test@example.com")
        assert not re.match(ZCODE_VALIDATION_PATTERNS["email"], "not-an-email")

    def test_url_pattern_works(self):
        assert re.match(ZCODE_VALIDATION_PATTERNS["url"], "https://example.com")
        assert not re.match(ZCODE_VALIDATION_PATTERNS["url"], "ftp://bad")

    def test_uuid_pattern_works(self):
        assert re.match(ZCODE_VALIDATION_PATTERNS["uuid"], "550e8400-e29b-41d4-a716-446655440000")

    def test_semver_pattern_works(self):
        assert re.match(ZCODE_VALIDATION_PATTERNS["semver"], "1.2.3")
        assert not re.match(ZCODE_VALIDATION_PATTERNS["semver"], "1.2")

    def test_ipv4_pattern_works(self):
        assert re.match(ZCODE_VALIDATION_PATTERNS["ipv4"], "192.168.1.1")
        assert not re.match(ZCODE_VALIDATION_PATTERNS["ipv4"], "999.999.999.999")

    def test_all_patterns_compilable(self):
        for name, regex in ZCODE_VALIDATION_PATTERNS.items():
            try:
                re.compile(regex)
            except re.error as e:
                assert False, f"Pattern '{name}' invalid regex: {e}"

    def test_common_patterns_exist(self):
        required = {"email", "url", "uuid", "ipv4", "semver", "base64", "mac"}
        assert required.issubset(ZCODE_VALIDATION_PATTERNS.keys())

    def test_all_pattern_names_are_strings(self):
        for name in ZCODE_VALIDATION_PATTERNS:
            assert isinstance(name, str), f"non-string key: {name}"


class TestValidateBoundary:
    """Gene 3 边界校验函数。"""

    def test_valid_email(self):
        assert validate_boundary("test@example.com", "email") is True

    def test_invalid_email(self):
        assert validate_boundary("not-email", "email") is False

    def test_valid_url(self):
        assert validate_boundary("https://example.com", "url") is True

    def test_invalid_url(self):
        assert validate_boundary("ftp://bad", "url") is False

    def test_valid_uuid(self):
        assert validate_boundary("550e8400-e29b-41d4-a716-446655440000", "uuid") is True

    def test_valid_semver(self):
        assert validate_boundary("1.2.3", "semver") is True

    def test_invalid_semver(self):
        assert validate_boundary("1.2", "semver") is False

    def test_valid_ipv4(self):
        assert validate_boundary("192.168.1.1", "ipv4") is True

    def test_valid_ipv6(self):
        assert validate_boundary("2001:0db8:85a3:0000:0000:8a2e:0370:7334", "ipv6") is True

    def test_empty_string_is_invalid(self):
        assert validate_boundary("", "email") is False

    def test_unknown_pattern_passes_by_design(self):
        """未知 pattern 不阻断（非严格拒绝模式）。"""
        assert validate_boundary("anything", "nonexistent_field") is True


class TestZcodeDnaPrompt:
    """系统提示词完整性。"""

    def test_prompt_has_capability_info(self):
        prompt = get_zcode_dna_prompt()
        assert "commit" in prompt.lower() or "gene" in prompt.lower()

    def test_prompt_has_six_principles(self):
        prompt = get_zcode_dna_prompt()
        # Six principles/commandments
        assert "1." in prompt or "1." in prompt
        assert "6." in prompt

    def test_prompt_mentions_zcode(self):
        prompt = get_zcode_dna_prompt()
        assert "ZCode" in prompt

    def test_prompt_no_truncation(self):
        prompt = get_zcode_dna_prompt()
        assert len(prompt) >= 2000  # 实际 4647 chars

    def test_prompt_has_plugin_info(self):
        prompt = get_zcode_dna_prompt()
        assert "plugin" in prompt.lower()

    def test_prompt_has_validation_info(self):
        prompt = get_zcode_dna_prompt()
        assert "valid" in prompt.lower() or "pattern" in prompt.lower()
