"""Tests for core/adr_engine — Architecture Decision Record engine."""

from __future__ import annotations

import os

import pytest

from core.adr_engine import (
    adr_create,
    adr_list,
    adr_mermaid,
    adr_update,
)


class TestADRCreate:
    def test_create_basic_adr(self):
        """adr_create returns a dict with required fields."""
        result = adr_create(
            title="Test ADR",
            context="Testing the ADR engine",
            decision="Write tests first",
            consequences="Better coverage",
        )
        assert isinstance(result, dict)
        assert result["title"] == "Test ADR"
        assert result["status"] == "proposed"
        assert "id" in result
        assert "created_at" in result

    def test_create_with_custom_status(self):
        result = adr_create(
            title="Accepted ADR",
            context="Need to decide",
            decision="Accept",
            consequences="None",
            status="accepted",
        )
        assert result["status"] == "accepted"

    def test_create_with_related(self):
        result = adr_create(
            title="Related ADR",
            context="Has relations",
            decision="Link them",
            consequences="Traceability",
            related=["adr-001", "adr-002"],
        )
        assert "adr-001" in result.get("related", [])

    def test_create_required_fields(self):
        with pytest.raises((TypeError, ValueError)):
            adr_create(title="Bad ADR")  # missing required args


class TestADRList:
    def test_list_returns_list(self):
        """adr_list returns a list of ADR dicts."""
        adrs = adr_list()
        assert isinstance(adrs, list)

    def test_list_filter_by_status(self):
        """Can filter ADRs by status."""
        # Create a unique one
        uid = f"test-filter-{os.urandom(4).hex()}"
        adr_create(
            title=uid,
            context="filter test",
            decision="test",
            consequences="test",
            status="proposed",
        )
        proposed = adr_list(status="proposed")
        titles = [a["title"] for a in proposed]
        assert uid in titles


class TestADRUpdate:
    def test_update_status(self):
        """Can update an ADR's status."""
        uid = f"test-upd-{os.urandom(4).hex()}"
        created = adr_create(
            title=uid,
            context="update test",
            decision="original",
            consequences="original",
        )
        adr_id = created["id"]
        updated = adr_update(adr_id=adr_id, status="accepted")
        assert updated["status"] == "accepted"

    def test_update_nonexistent(self):
        result = adr_update(adr_id="nonexistent-adr", status="deprecated")
        assert "error" in result or "not found" in str(result).lower()


class TestADRMermaid:
    def test_mermaid_returns_string(self):
        """adr_mermaid returns a Mermaid timeline string."""
        result = adr_mermaid()
        assert isinstance(result, str)
        assert len(result) > 0
        # Should be valid Mermaid timeline syntax
        assert "timeline" in result.lower() or "section" in result.lower() or "title" in result.lower()
