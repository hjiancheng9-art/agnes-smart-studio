"""Tests for core/docs_engine.py — 文档引擎"""

from pathlib import Path

from core.docs_engine import (
    generate_all,
    generate_help_md,
    render_help_md,
    sync_agents_md,
    sync_manifest,
)

ROOT = Path(__file__).resolve().parent.parent


def _command_section(text: str) -> str:
    """Return the command-reference portion (everything before the stats footer).

    The footer line counts tools/skills/modules/tests, which legitimately change
    as files are added; the command section is driven purely by COMMANDS and must
    stay byte-stable.
    """
    marker = "\n---\n"
    idx = text.find(marker)
    return text[:idx] if idx != -1 else text


class TestDocsEngine:
    def test_generate_all(self):
        result = generate_all()
        assert isinstance(result, dict)

    def test_generate_help_md(self):
        result = generate_help_md()
        assert isinstance(result, str)

    def test_render_help_md_is_pure(self):
        # render_help_md must not touch disk; two calls must be identical.
        assert render_help_md() == render_help_md()

    def test_help_md_in_sync_with_commands(self):
        """Committed HELP.md command section must match render_help_md() output.

        Reads the git-committed HELP.md (not the working copy) so that other
        tests which write HELP.md during the run cannot mask real drift.
        Guards against HELP.md drifting out of sync with the COMMANDS registry.
        If this fails, run:
            python -c "from core.docs_engine import generate_help_md; generate_help_md()"
        then commit the updated HELP.md.
        """
        import subprocess

        try:
            committed = subprocess.run(
                ["git", "show", "HEAD:HELP.md"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            import pytest

            pytest.skip("git not available")
            return

        if committed.returncode != 0:
            import pytest

            pytest.skip("HEAD:HELP.md not available (uncommitted or no git repo)")
            return

        rendered = render_help_md()
        assert _command_section(committed.stdout) == _command_section(rendered), (
            "Committed HELP.md is out of sync with COMMANDS. Regenerate with "
            "generate_help_md() and commit HELP.md."
        )

    def test_sync_agents_md(self):
        result = sync_agents_md()
        assert isinstance(result, str)

    def test_sync_manifest(self):
        result = sync_manifest()
        assert isinstance(result, dict)
